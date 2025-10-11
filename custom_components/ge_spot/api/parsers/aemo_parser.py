"""Parser for AEMO NEMWEB Pre-dispatch API responses."""

import csv
import logging
from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo
from typing import Dict, Any, Optional, List

from ..base.price_parser import BasePriceParser
from ..interval_expander import convert_to_target_intervals
from ...const.sources import Source
from ...const.currencies import Currency
from ...const.energy import EnergyUnit

_LOGGER = logging.getLogger(__name__)


class AemoParser(BasePriceParser):
    """Parser for AEMO NEMWEB Pre-dispatch CSV data.

    AEMO operates on 30-minute trading intervals. The Pre-dispatch reports contain
    forecasts for ~55 trading intervals (40+ hour horizon), which are provided as
    30-minute interval data.

    The parser automatically expands 30-minute trading intervals to 15-minute
    intervals using the interval_expander, which duplicates each 30-min price
    into two 15-min intervals.
    """

    def __init__(self, source: str = Source.AEMO, timezone_service=None):
        """Initialize the parser.

        Args:
            source: Source identifier (defaults to Source.AEMO)
            timezone_service: Optional timezone service
        """
        super().__init__(source, timezone_service)

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse AEMO NEMWEB Pre-dispatch data.

        Expected input structure (from AemoAPI.fetch_raw_data):
        {
            'csv_content': str,  # CSV file content
            'area': str,         # Region code (NSW1, QLD1, etc.)
            'timezone': str,     # Australia/Sydney
            'currency': str,     # AUD
            'raw_data': dict     # Metadata
        }

        Returns:
            Dict with interval_raw (ISO timestamps), currency, timezone, source, etc.
        """
        _LOGGER.debug(f"[AemoParser] Starting parse. Input data keys: {list(data.keys())}")

        # Extract the CSV content from raw_data
        csv_content = data.get("csv_content")
        if not csv_content:
            _LOGGER.warning("[AemoParser] 'csv_content' missing in input data")
            return self._create_empty_result(data)

        # Extract metadata
        area = data.get("area")
        if not area:
            _LOGGER.warning("[AemoParser] 'area' not specified")
            return self._create_empty_result(data)

        source_timezone = data.get("timezone", "Australia/Sydney")
        source_currency = data.get("currency", Currency.AUD)

        _LOGGER.debug(f"[AemoParser] Parsing NEMWEB CSV for area: {area}, timezone: {source_timezone}")

        # Parse the CSV content
        try:
            prices_30min = self._parse_predispatch_csv(csv_content, area)

            if not prices_30min:
                _LOGGER.warning(f"[AemoParser] No price data found for {area}")
                return self._create_empty_result(data, source_timezone, source_currency)

            _LOGGER.debug(f"[AemoParser] Parsed {len(prices_30min)} 30-minute trading intervals")

            # Convert to interval_raw format (ISO timestamps)
            interval_raw = {}
            for record in prices_30min:
                timestamp = record["timestamp"]

                # Ensure timezone-aware datetime
                if timestamp.tzinfo is None:
                    tz = ZoneInfo(source_timezone)
                    timestamp = timestamp.replace(tzinfo=tz)

                # Convert to UTC and use ISO format as key
                timestamp_utc = timestamp.astimezone(ZoneInfo("UTC"))
                interval_key = timestamp_utc.isoformat()
                interval_raw[interval_key] = record["price"]

            _LOGGER.debug(f"[AemoParser] Created {len(interval_raw)} 30-minute interval_raw entries (UTC keys)")

            # Expand 30-minute trading intervals to 15-minute intervals
            _LOGGER.debug(f"[AemoParser] Expanding {len(interval_raw)} 30-min prices to 15-min intervals")
            interval_raw = convert_to_target_intervals(
                source_prices=interval_raw,
                source_interval_minutes=30  # AEMO uses 30-min trading intervals
            )
            _LOGGER.debug(f"[AemoParser] After expansion: {len(interval_raw)} 15-minute intervals")

            # Construct result
            result = {
                "interval_raw": interval_raw,
                "currency": source_currency,
                "area": area,
                "timezone": source_timezone,
                "source": Source.AEMO,
                "source_unit": EnergyUnit.MWH,
                "source_interval_minutes": 30  # AEMO uses 30-min trading intervals
            }

            # Validate before returning
            if not self.validate_parsed_data(result):
                _LOGGER.warning(f"[AemoParser] Validation failed for parsed data")
                return self._create_empty_result(data, source_timezone, source_currency)

            return result

        except Exception as e:
            _LOGGER.error(f"[AemoParser] Error parsing NEMWEB CSV: {e}", exc_info=True)
            return self._create_empty_result(data, source_timezone, source_currency)

    def _parse_predispatch_csv(self, csv_content: str, target_region: str) -> List[Dict[str, Any]]:
        """Parse AEMO NEMWEB Pre-dispatch CSV format.

        AEMO CSV format uses line type indicators:
        - C: Comment lines
        - I: Header lines (column definitions)
        - D: Data lines

        We're looking for:
        - Header: I,PREDISPATCH,REGION_PRICES,...
        - Data: D,PREDISPATCH,REGION_PRICES,1,{REGIONID},...

        Args:
            csv_content: CSV file content as string
            target_region: Region code (NSW1, QLD1, SA1, TAS1, VIC1)

        Returns:
            List of dicts with 'timestamp' and 'price' keys
        """
        # Extract header to get field names
        header = self._extract_header(csv_content)
        if not header:
            raise ValueError("Could not find PREDISPATCH,REGION_PRICES header in CSV")

        # Parse data rows for target region
        prices = []
        reader = csv.reader(StringIO(csv_content))

        for row in reader:
            if len(row) < 2:
                continue

            # Look for data rows: D,PREDISPATCH,REGION_PRICES,1,{REGIONID},...
            if (row[0] == 'D' and
                len(row) >= 3 and
                row[1] == 'PREDISPATCH' and
                row[2] == 'REGION_PRICES'):

                try:
                    # Create dict from header and row
                    row_dict = dict(zip(header, row))

                    # Check if this row is for our target region
                    if row_dict.get('REGIONID') != target_region:
                        continue

                    # Extract timestamp and price
                    datetime_str = row_dict.get('DATETIME')
                    rrp_str = row_dict.get('RRP')  # Regional Reference Price

                    if not datetime_str or not rrp_str:
                        continue

                    # Parse datetime (format: "YYYY/MM/DD HH:MM:SS")
                    timestamp = self._parse_datetime(datetime_str)

                    # Parse price
                    price = float(rrp_str)

                    prices.append({
                        "timestamp": timestamp,
                        "price": price
                    })

                except (ValueError, KeyError) as e:
                    _LOGGER.debug(f"Skipping row due to parse error: {e}")
                    continue

        return prices

    def _extract_header(self, csv_content: str) -> Optional[List[str]]:
        """Extract column names from CSV header.

        Looks for line: I,PREDISPATCH,REGION_PRICES,{version},{field1},{field2},...

        Args:
            csv_content: CSV file content

        Returns:
            List of field names, or None if not found
        """
        reader = csv.reader(StringIO(csv_content))

        for row in reader:
            if len(row) >= 3 and row[0] == 'I' and row[1] == 'PREDISPATCH' and row[2] == 'REGION_PRICES':
                # Return all columns from position 0 onwards (includes line type)
                return row

        return None

    def _parse_datetime(self, datetime_str: str) -> datetime:
        """Parse AEMO datetime format.

        Format: "YYYY/MM/DD HH:MM:SS"
        Example: "2025/10/07 01:30:00"

        Args:
            datetime_str: Datetime string from CSV

        Returns:
            Naive datetime object (timezone added by caller)
        """
        try:
            return datetime.strptime(datetime_str, "%Y/%m/%d %H:%M:%S")
        except ValueError as e:
            raise ValueError(f"Invalid AEMO datetime format: {datetime_str}") from e

    def _create_empty_result(
        self,
        original_data: Dict[str, Any],
        timezone: str = "Australia/Sydney",
        currency: str = Currency.AUD
    ) -> Dict[str, Any]:
        """Helper to create a standard empty result structure."""
        return {
            "interval_raw": {},
            "currency": original_data.get("currency", currency),
            "timezone": original_data.get("timezone", timezone),
            "area": original_data.get("area"),
            "source": Source.AEMO,
            "source_unit": EnergyUnit.MWH,
            "source_interval_minutes": 30
        }
