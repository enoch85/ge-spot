"""API handler for AEMO (Australian Energy Market Operator)."""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List # Added List
import aiohttp

# Updated imports for BaseAPIAdapter, PriceData, register_adapter, and constants
from .base_api import BaseAPI, PriceData # PriceEntry is implicitly handled by List[PriceEntry]
from .registry import register_adapter
from ..const.sources import SOURCE_AEMO
from ..const.api import Aemo # For Aemo.REGIONS and Aemo.SUMMARY_URL
from ..const.currencies import Currency # For Currency.AUD
from ..const.network import Network # For Network.Defaults.TIMEOUT

from .parsers.aemo_parser import AemoParser
from .base.api_client import ApiClient # Assuming this is the intended ApiClient

_LOGGER = logging.getLogger(__name__)

# Documentation about AEMO's API structure
"""
AEMO (Australian Energy Market Operator) API Details:
-------------------------------------------------------
Unlike European markets, AEMO provides real-time spot prices at 5-minute intervals
rather than daily ahead auctions. The integration works with a consolidated endpoint:

1. ELEC_NEM_SUMMARY - A comprehensive endpoint that contains:
   - Current spot prices for all regions
   - Detailed price information including regulation and contingency prices
   - Market notices

The API provides data for five regions across Australia:
- NSW1 - New South Wales
- QLD1 - Queensland
- SA1  - South Australia
- TAS1 - Tasmania
- VIC1 - Victoria

For more information, see: https://visualisations.aemo.com.au/
"""

@register_adapter(
    name=SOURCE_AEMO,
    regions=Aemo.REGIONS, # Ensure Aemo.REGIONS is a list of strings like ["NSW1", "QLD1", ...]
    default_priority=60
)
class AemoAPI(BaseAPI): # Changed base class and class name
    """API client for AEMO (Australian Energy Market Operator)."""

    # Updated constructor to match BaseAPIAdapter
    def __init__(self, config: Optional[Dict[str, Any]] = None, session: Optional[aiohttp.ClientSession] = None):
        """Initialize the API client.

        Args:
            config: Configuration dictionary
            session: aiohttp client session
        """
        super().__init__(config, session)
        # timezone_service removed from super() call and as an instance variable

    # _get_source_type method removed

    # _get_base_url logic will be inlined in fetch_data

    # Renamed from fetch_raw_data, signature and return type changed
    async def fetch_data(self, area: str) -> PriceData:
        """Fetch raw price data for the given area.

        Args:
            area: Area code (e.g., NSW1, QLD1, etc.)

        Returns:
            PriceData object containing pricing data or error information.
        """
        now_utc = datetime.now(timezone.utc) # For metadata timestamp

        # ApiClient uses self.session which is passed during adapter instantiation
        client = ApiClient(session=self.session)

        try:
            # Validate the area code
            if area not in Aemo.REGIONS:
                _LOGGER.error(f"Invalid AEMO region: {area}. Must be one of {Aemo.REGIONS}")
                raise ValueError(f"Invalid AEMO region: {area}")

            # Inlined _get_base_url logic
            base_url = getattr(Aemo, 'SUMMARY_URL', "https://visualisations.aemo.com.au/aemo/apps/api/report/ELEC_NEM_SUMMARY")
            
            response = await client.fetch(
                base_url,
                timeout=Network.Defaults.TIMEOUT,
                response_format='json'
            )

            if response and isinstance(response, dict) and Aemo.SUMMARY_ARRAY in response:
                parser = self.get_parser_for_area(area) # This method is kept
                parsed_content = parser.parse(response, area=area)
                hourly_raw_dict = parsed_content.get("hourly_raw", {})

                price_entries: List[Dict[str, Any]] = [] # To match PriceEntry structure
                if isinstance(hourly_raw_dict, dict):
                    for ts_str, price_val in hourly_raw_dict.items():
                        try:
                            # Assuming AemoParser returns ISO string timestamps as keys.
                            # These need to be converted to datetime objects.
                            dt_object = datetime.fromisoformat(ts_str)
                            price_entries.append({"start_time": dt_object, "price": float(price_val)})
                        except (ValueError, TypeError) as e:
                            _LOGGER.warning(f"AEMO: Could not parse timestamp or price: '{ts_str}', '{price_val}' - {e}")
                
                # Sort by start_time if parser doesn't guarantee order
                price_entries.sort(key=lambda x: x['start_time'])

                return PriceData(
                    hourly_raw=price_entries,
                    timezone=self.get_timezone_for_area(area), # This method is kept
                    currency=Currency.AUD,
                    source=self.api_name, # Use api_name from BaseAPI
                    meta={
                        "raw_data_preview": str(response)[:200], # Store a preview
                        "fetch_timestamp_utc": now_utc.isoformat(),
                        "area": area
                    }
                )
            else:
                _LOGGER.warning(f"Invalid or empty response from AEMO for area {area}. Response preview: {str(response)[:200]}")
                # Raise an exception or return PriceData with error for consistency
                raise ValueError(f"Invalid or empty API response from AEMO for area {area}")
        except aiohttp.ClientError as e:
            _LOGGER.error(f"AEMO API request failed for area {area}: {e}")
            raise # Re-raise for FallbackManager/UnifiedPriceManager to handle
        except Exception as e:
            _LOGGER.error(f"AEMO data processing failed for area {area}: {e}")
            raise # Re-raise other critical errors

    # get_timezone_for_area method is kept
    def get_timezone_for_area(self, area: str) -> str:
        """Get timezone for the specific AEMO area.

        Args:
            area: Area code (NSW1, QLD1, SA1, TAS1, VIC1)

        Returns:
            Timezone string based on the state.
        """
        # Map AEMO regions to Australian timezones
        timezone_map = {
            "NSW1": "Australia/Sydney", # New South Wales
            "QLD1": "Australia/Brisbane", # Queensland
            "SA1": "Australia/Adelaide", # South Australia
            "TAS1": "Australia/Hobart", # Tasmania
            "VIC1": "Australia/Melbourne" # Victoria
        }
        # Default to Sydney if area is unknown or not provided
        return timezone_map.get(area, "Australia/Sydney")

    # get_parser_for_area method is kept
    def get_parser_for_area(self, area: str) -> Any:
        """Get parser for the area.

        Args:
            area: Area code

        Returns:
            Parser instance
        """
        # AEMO uses the same parser structure, but parsing logic might differ based on area
        return AemoParser()
