"""API handler for AEMO (Australian Energy Market Operator)."""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import aiohttp

from .base.api_client import ApiClient
from ..const.sources import Source
from ..const.api import Aemo
from .parsers.aemo_parser import AemoParser
from .base.base_price_api import BasePriceAPI
from ..const.currencies import Currency
from ..const.network import Network

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

class AemoAPI(BasePriceAPI):
    """API client for AEMO (Australian Energy Market Operator)."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, session: Optional[aiohttp.ClientSession] = None, timezone_service=None):
        """Initialize the API client.

        Args:
            config: Configuration dictionary
            session: aiohttp client session
            timezone_service: Timezone service instance
        """
        super().__init__(config, session, timezone_service)

    def _get_source_type(self) -> str:
        """Get the source type identifier.

        Returns:
            Source type identifier
        """
        return Source.AEMO

    def _get_base_url(self) -> str:
        """Get the base URL for the API.

        Returns:
            Base URL as string
        """
        # Use constant defined in const/api.py if available, otherwise fallback
        return getattr(Aemo, 'SUMMARY_URL', "https://visualisations.aemo.com.au/aemo/apps/api/report/ELEC_NEM_SUMMARY")

    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Optional[Dict[str, Any]]:
        """Fetch raw price data for the given area.

        Args:
            area: Area code (e.g., NSW1, QLD1, etc.)
            session: Optional session for API requests
            **kwargs: Additional parameters

        Returns:
            Raw API response data as a dictionary, or None if fetch fails.
        """
        # Use current UTC time as reference - AEMO provides real-time spot prices
        # so we don't need a specific reference date
        now_utc = datetime.now(timezone.utc)

        client = ApiClient(session=session or self.session)
        try:
            # Validate the area code
            if area not in Aemo.REGIONS:
                _LOGGER.error(f"Invalid AEMO region: {area}. Must be one of {Aemo.REGIONS}")
                raise ValueError(f"Invalid AEMO region: {area}")

            # Fetch data from the AEMO API
            response = await client.fetch(
                self._get_base_url(),
                timeout=Network.Defaults.TIMEOUT,
                response_format='json'
            )

            # Process the response if valid
            if response and isinstance(response, dict) and Aemo.SUMMARY_ARRAY in response:
                # Parse the response using the appropriate parser
                parser = self.get_parser_for_area(area)
                parsed = parser.parse(response, area=area) # Pass area to the parser
                hourly_raw = parsed.get("hourly_raw", {}) # Correct key

                # Return standardized data structure with ISO timestamps
                return {
                    "hourly_raw": hourly_raw,
                    "timezone": self.get_timezone_for_area(area),
                    "currency": Currency.AUD,
                    "source_name": "aemo",
                    "raw_data": {
                        "data": response,
                        "timestamp": now_utc.isoformat(),
                        "area": area
                    },
                }
            else:
                _LOGGER.warning(f"Invalid or empty response from AEMO for area {area}. Response: {response}")
                return None
        finally:
            if session is None and client:
                await client.close()

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

    def get_parser_for_area(self, area: str) -> Any:
        """Get parser for the area.

        Args:
            area: Area code

        Returns:
            Parser instance
        """
        # AEMO uses the same parser structure, but parsing logic might differ based on area
        return AemoParser()
