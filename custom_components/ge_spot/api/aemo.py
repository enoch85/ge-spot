"""API handler for AEMO (Australian Energy Market Operator)."""
import logging
from datetime import datetime, timezone
import asyncio
from typing import Dict, Any, Optional, List

from ..utils.api_client import ApiClient
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.api import Aemo
from .parsers.aemo_parser import AemoParser
from ..utils.date_range import generate_date_ranges
from .base.base_price_api import BasePriceAPI
from ..timezone import TimezoneService

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
        return Aemo.SUMMARY_URL
    
    async def fetch_raw_data(self, area: str, reference_time: Optional[datetime] = None, session=None, **kwargs) -> List[Dict[str, Any]]:
        """Fetch raw price data for the given area.
        
        Args:
            area: Area code
            reference_time: Optional reference time
            session: Optional session for API requests
            **kwargs: Additional parameters
            
        Returns:
            List of standardized price data dictionaries
        """
        client = ApiClient(session=session or self.session)
        try:
            # Validate area
            if area not in Aemo.REGIONS:
                _LOGGER.error(f"Invalid AEMO region: {area}. Must be one of {Aemo.REGIONS}")
                return []

            # Fetch raw data from the consolidated ELEC_NEM_SUMMARY endpoint
            raw_data = await self._fetch_summary_data(client, area, reference_time)
            if not raw_data:
                _LOGGER.error("Failed to fetch AEMO data")
                return []

            return [raw_data]
        finally:
            if session is None and client:
                await client.close()

    async def parse_raw_data(self, raw_data: Any) -> Dict[str, Any]:
        """Parse raw data into standardized format.
        
        Args:
            raw_data: Raw data from API
            
        Returns:
            Parsed data in standardized format
        """
        if not raw_data or not isinstance(raw_data, list) or len(raw_data) == 0:
            return {}
            
        data = raw_data[0]  # Get first item from list
        
        # Use the parser to extract standardized data
        parser = AemoParser()
        parsed = parser.parse(data)
        metadata = parser.extract_metadata(data)

        # Build standardized result
        result = {
            "hourly_prices": parsed.get("hourly_prices", {}),  # keys: HH:00 or ISO, values: price in AUD
            "currency": metadata.get("currency", "AUD"),
            "timezone": metadata.get("timezone", "Australia/Sydney"),
            "area": metadata.get("area", "NSW1"),
            "raw_data": data,  # keep original for debugging/fallback
            "source": Source.AEMO,
            "metadata": metadata,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        
        return result
    
    def get_timezone_for_area(self, area: str) -> str:
        """Get timezone for the area.
        
        Args:
            area: Area code
            
        Returns:
            Timezone string
        """
        return "Australia/Sydney"
    
    def get_parser_for_area(self, area: str) -> Any:
        """Get parser for the area.
        
        Args:
            area: Area code
            
        Returns:
            Parser instance
        """
        return AemoParser()

    async def _fetch_summary_data(self, client, area, reference_time):
        """Fetch data from the consolidated AEMO endpoint."""
        try:
            # Generate date ranges to try - AEMO uses 5-minute intervals
            date_ranges = generate_date_ranges(reference_time, Source.AEMO)

            # Try each date range until we get a valid response
            for start_date, end_date in date_ranges:
                # Format the time for AEMO API - use start_date which is rounded to 5-minute intervals
                formatted_time = start_date.strftime("%Y%m%dT%H%M%S")

                params = {
                    "time": formatted_time,
                }

                _LOGGER.debug(f"Fetching AEMO data with params: {params}")
                response = await client.fetch(Aemo.SUMMARY_URL, params=params)

                # If we got a valid response, return it
                if response and Aemo.SUMMARY_ARRAY in response:
                    _LOGGER.info(f"Successfully fetched AEMO data with time: {formatted_time}")
                    return response
                else:
                    _LOGGER.debug(f"No valid data from AEMO for time: {formatted_time}, trying next range")

            # If we've tried all ranges and still have no data, log a warning
            _LOGGER.warning("No valid data found from AEMO after trying multiple date ranges")
            return None
        except Exception as e:
            _LOGGER.error(f"Error fetching AEMO data: {e}")
            return None
