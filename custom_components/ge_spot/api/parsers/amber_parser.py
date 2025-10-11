"""Parser for Amber Energy API data."""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from ..base.price_parser import BasePriceParser
from ...const.currencies import Currency
from ...const.sources import Source

_LOGGER = logging.getLogger(__name__)

class AmberParser(BasePriceParser):
    """Parser for Amber API responses."""

    def __init__(self, source: str = Source.AMBER, timezone_service=None):
        """Initialize the parser.
        
        Args:
            source: Source identifier (defaults to Source.AMBER)
            timezone_service: Optional timezone service
        """
        super().__init__(source, timezone_service)

    def parse(self, raw_data: Any) -> Dict[str, Any]:
        """Parse Amber Energy API data.

        Args:
            raw_data: Raw API data (expected to be a list of price entries or a dict containing it)

        Returns:
            Standardized price data dictionary
        """
        result = {
            "interval_raw": {},
            "currency": Currency.AUD,
            "timezone": "Australia/Sydney" # Default timezone for Amber
        }

        price_list = None
        if isinstance(raw_data, list):
            price_list = raw_data
        elif isinstance(raw_data, dict):
            # Check common keys where the list might be nested
            if "data" in raw_data and isinstance(raw_data["data"], list):
                price_list = raw_data["data"]
            elif "prices" in raw_data and isinstance(raw_data["prices"], list):
                price_list = raw_data["prices"]
            # Add more checks if Amber API structure varies

        if not price_list:
            _LOGGER.warning("No valid price list found in Amber data to parse")
            return result # Return default empty structure

        interval_raw = self._parse_price_list(price_list)
        result["interval_raw"] = interval_raw

        # Add area if available in the input dict (though Amber usually doesn't provide it)
        if isinstance(raw_data, dict) and "area" in raw_data:
             result["area"] = raw_data["area"]

        _LOGGER.debug(f"Amber parser found {len(result['interval_raw'])} interval prices")
        return result

    def _parse_price_list(self, price_list: List[Dict[str, Any]]) -> Dict[str, float]:
        """Helper to parse the list of price entries."""
        interval_raw = {}
        for entry in price_list:
            try:
                # Amber timestamps are usually ISO format UTC
                timestamp_str = entry.get('startTime') or entry.get('nemTime') or entry.get('created_at') # Try common timestamp keys
                if not timestamp_str:
                    _LOGGER.debug(f"Skipping Amber entry, missing timestamp: {entry}")
                    continue

                # Parse timestamp, assuming UTC
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                interval_key = dt.isoformat() # Use ISO format UTC key

                # Amber price is usually in cents per kWh ('perKwh')
                price_cents = entry.get('perKwh')
                if price_cents is None:
                     # Fallback: check for 'rrp' (Regional Reference Price) which might be $/MWh
                     price_dollars_mwh = entry.get('rrp')
                     if price_dollars_mwh is not None:
                         try:
                             # Convert $/MWh to Cents/kWh: ($/MWh / 1000) * 100 = $/kWh * 100 = Cents/kWh
                             price_cents = float(price_dollars_mwh) / 10.0
                             _LOGGER.debug(f"Using Amber 'rrp' {price_dollars_mwh} $/MWh, converted to {price_cents} Cents/kWh for {interval_key}")
                         except (ValueError, TypeError):
                             _LOGGER.debug(f"Could not parse Amber 'rrp' value: {price_dollars_mwh}")
                             continue
                     else:
                        _LOGGER.debug(f"Skipping Amber entry, missing price ('perKwh' or 'rrp'): {entry}")
                        continue

                # Ensure price is float
                try:
                    price = float(price_cents)
                except (ValueError, TypeError):
                    _LOGGER.debug(f"Could not parse Amber price value: {price_cents}")
                    continue

                interval_raw[interval_key] = price # Store price in Cents/kWh
                _LOGGER.debug(f"Storing raw Amber price for {interval_key}: {price} Cents/kWh")

            except (ValueError, TypeError, KeyError) as e:
                _LOGGER.warning(f"Failed to parse Amber entry: {entry}. Error: {e}")
                continue
        return interval_raw

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract metadata from Amber API response.

        Args:
            data: Raw API response data (list or dict)

        Returns:
            Metadata dictionary
        """
        metadata = super().extract_metadata(data) # Gets basic structure
        metadata.update({
            "currency": Currency.AUD, # Amber usually uses AUD
            "timezone": "Australia/Sydney", # Default Amber timezone
            "area": "unknown", # Amber doesn't typically specify area in price data
            "source_unit": "Cents/kWh" # Amber 'perKwh' is usually Cents/kWh
        })

        # Extract area if provided in a wrapping dict
        if isinstance(data, dict) and "area" in data:
            metadata["area"] = data["area"]

        # Add specific Amber metadata if available (e.g., from headers or wrapper dict)
        if isinstance(data, dict):
            if "channelType" in data: # Example field
                 metadata["channel_type"] = data["channelType"]

        # Update parser version and parsed time
        metadata["parser_version"] = "2.1" # Updated version
        metadata["parsed_at"] = datetime.now(timezone.utc).isoformat()
        # Price count will be calculated by the base class or DataProcessor later
        # based on the returned 'interval_raw'

        return metadata
