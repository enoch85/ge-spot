"""Parser for Energi Data Service API responses."""
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from zoneinfo import ZoneInfo

from ...const.sources import Source
from ...const.currencies import Currency
from ...utils.validation import validate_data
from ...timezone.timezone_utils import normalize_hour_value
from ..base.price_parser import BasePriceParser
from ...const.energy import EnergyUnit

_LOGGER = logging.getLogger(__name__)

class EnergiDataParser(BasePriceParser):
    """Parser for Energi Data Service API responses."""

    def __init__(self, source: str = Source.ENERGI_DATA_SERVICE, timezone_service=None):
        """Initialize the parser.

        Args:
            source: Source identifier (defaults to Source.ENERGI_DATA_SERVICE)
            timezone_service: Optional timezone service
        """
        super().__init__(source, timezone_service)

    def parse(self, raw_data: Any) -> Dict[str, Any]:
        """Parse Energi Data Service API response.

        Args:
            raw_data: Raw API response data (potentially nested)

        Returns:
            Parsed data with interval prices
        """
        result = {
            "interval_raw": {},
            "currency": Currency.DKK,
            "timezone": "Europe/Copenhagen", # Default for EDS
            "source_unit": EnergyUnit.MWH # Default for EDS
        }

        # Check for valid data
        if not raw_data or not isinstance(raw_data, dict):
            _LOGGER.warning("Empty or invalid Energi Data Service data received")
            return result

        # --- Extract records ---
        records = []
        # Check for the nested structure from EnergiDataAPI adapter
        if "raw_data" in raw_data and isinstance(raw_data["raw_data"], dict):
            _LOGGER.debug("Found nested 'raw_data' key, attempting to extract today/tomorrow records.")
            api_content = raw_data["raw_data"]
            # Add check for api_content being None
            if api_content is not None:
                # Safely get today's records
                today_data = api_content.get("today")
                today_records = today_data.get("records", []) if isinstance(today_data, dict) else []

                # Safely get tomorrow's records
                tomorrow_data = api_content.get("tomorrow")
                tomorrow_records = tomorrow_data.get("records", []) if isinstance(tomorrow_data, dict) else []

                records = today_records + tomorrow_records
                if records:
                    _LOGGER.debug(f"Extracted {len(today_records)} today and {len(tomorrow_records)} tomorrow records from nested structure.")
                else:
                    _LOGGER.debug("Nested 'raw_data' found, but no 'records' within today/tomorrow.")
            else:
                _LOGGER.warning("Nested 'raw_data' key found, but its value is None.")

        # Fallback: Check for top-level 'records' key (e.g., from direct test data)
        if not records and "records" in raw_data and isinstance(raw_data["records"], list):
             _LOGGER.debug("Using top-level 'records' key.")
             records = raw_data["records"]

        # --- Validate extracted records ---
        if not records:
            _LOGGER.warning("No valid records found in Energi Data Service data after checking nested and top-level structures.")
            _LOGGER.debug(f"Data received by parser: {raw_data}") # Log the structure received
            return result

        # --- Parse interval prices from records ---
        # DayAheadPrices dataset provides native 15-minute intervals (since Sept 30, 2025)
        # No expansion needed - data is already in correct interval format
        interval_prices_iso = {}
        
        # Get Copenhagen timezone for localizing naive timestamps (cached at module import)
        copenhagen_tz = ZoneInfo('Europe/Copenhagen')

        for record in records:
            try:
                # DayAheadPrices format: TimeDK and DayAheadPriceDKK
                if "TimeDK" in record and "DayAheadPriceDKK" in record:
                    timestamp_str = record["TimeDK"]
                    # Parse timestamp and ensure it's timezone-aware
                    dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    
                    # If datetime is naive (no timezone), localize it to Copenhagen time
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=copenhagen_tz)
                    
                    # Convert to UTC for consistent storage
                    dt_utc = dt.astimezone(timezone.utc)
                    
                    # Create ISO format key with timezone (matches validation expectations)
                    interval_key = dt_utc.isoformat()
                    price = float(record["DayAheadPriceDKK"])
                    interval_prices_iso[interval_key] = price
                    _LOGGER.debug(f"Parsed interval price for {interval_key}: {price} DKK/MWh")
                else:
                    _LOGGER.warning(f"Record missing TimeDK or DayAheadPriceDKK: {record}")
            except (ValueError, TypeError) as e:
                _LOGGER.debug(f"Failed to parse Energi Data Service record: {e}")

        # Use interval prices directly - already in correct 15-minute format
        if interval_prices_iso:
            result["interval_raw"] = interval_prices_iso
            _LOGGER.debug(f"Final interval_raw has {len(result['interval_raw'])} interval prices")
        else:
            _LOGGER.warning("[energi_data_service] interval_raw is EMPTY after parsing!")

        return result

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract metadata from Energi Data Service API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = super().extract_metadata(data)
        metadata.update({
            "currency": Currency.DKK,  # Default currency for Energi Data Service
            "timezone": "Europe/Copenhagen",
            "area": "DK1",  # Default area
        })

        # Extract additional metadata
        if isinstance(data, dict):
            # Check for area information
            if "area" in data:
                metadata["area"] = data["area"]

            # Check for records information
            if "records" in data and isinstance(data["records"], list):
                metadata["record_count"] = len(data["records"])

                # Extract area from the first record if available
                if data["records"] and "PriceArea" in data["records"][0]:
                    metadata["area"] = data["records"][0]["PriceArea"]

        return metadata

    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse timestamp from Energi Data Service format.

        Args:
            timestamp_str: Timestamp string

        Returns:
            Parsed datetime or None if parsing fails
        """
        try:
            # Try ISO format
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            try:
                # Try Energi Data Service specific format (YYYY-MM-DD HH:MM)
                return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                _LOGGER.warning(f"Failed to parse timestamp: {timestamp_str}")
                return None
