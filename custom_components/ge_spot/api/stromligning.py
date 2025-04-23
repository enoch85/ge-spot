"""API handler for Stromligning.dk."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from ..utils.api_client import ApiClient
from ..const.sources import Source
from ..const.config import Config
from ..const.currencies import Currency
from .parsers.stromligning_parser import StromligningParser
from ..utils.date_range import generate_date_ranges
from .base.base_price_api import BasePriceAPI

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://stromligning.dk/api/prices"

class StromligningAPI(BasePriceAPI):
    """API client for Stromligning.dk."""

    def _get_source_type(self) -> str:
        """Get the source type identifier.
        
        Returns:
            Source type identifier
        """
        return Source.STROMLIGNING
    
    def _get_base_url(self) -> str:
        """Get the base URL for the API.
        
        Returns:
            Base URL as string
        """
        return BASE_URL
        
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
            # Fetch raw data
            raw_data = await self._fetch_data(client, area, reference_time)
            if not raw_data:
                _LOGGER.warning(f"No data received from Stromligning API for area {area}")
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
        parser = StromligningParser()
        parsed = parser.parse(data)
        metadata = parser.extract_metadata(data)

        # Extract price components if available
        price_components = parser.get_price_components()

        # Build standardized result
        result = {
            "hourly_prices": parsed.get("hourly_prices", {}),  # keys: ISO timestamps, values: prices
            "currency": metadata.get("currency", Currency.DKK),
            "timezone": metadata.get("timezone", "Europe/Copenhagen"),
            "area": metadata.get("area", "DK1"),
            "raw_data": data,  # keep original for debugging/fallback
            "source": Source.STROMLIGNING,
            "metadata": metadata,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        
        # Add current and next hour prices if available
        if "current_price" in parsed:
            result["current_price"] = parsed["current_price"]
            
        if "next_hour_price" in parsed:
            result["next_hour_price"] = parsed["next_hour_price"]
            
        # Add price components if available
        if price_components:
            result["price_components"] = price_components
        
        return result
    
    def get_timezone_for_area(self, area: str) -> str:
        """Get timezone for the area.
        
        Args:
            area: Area code
            
        Returns:
            Timezone string
        """
        return "Europe/Copenhagen"
    
    def get_parser_for_area(self, area: str) -> Any:
        """Get parser for the area.
        
        Args:
            area: Area code
            
        Returns:
            Parser instance
        """
        return StromligningParser()

    async def _fetch_data(self, client, area: str, reference_time):
        """Fetch data from Stromligning.dk API.
        
        Args:
            client: API client
            area: Area code
            reference_time: Reference time
            
        Returns:
            Raw data from API
        """
        try:
            if reference_time is None:
                reference_time = datetime.now(timezone.utc)

            # Generate date ranges to try
            date_ranges = generate_date_ranges(reference_time, Source.STROMLIGNING)

            # Use the provided area or default to DK1
            area_code = area or "DK1"

            # Try each date range until we get a valid response
            for start_date, end_date in date_ranges:
                # Stromligning API expects a wider range than just the start/end dates
                # We'll use the start date as "from" and add 2 days to the end date as "to"
                from_date = start_date.date().isoformat() + "T00:00:00"
                to_date = (end_date.date() + timedelta(days=1)).isoformat() + "T23:59:59"

                params = {
                    "from": from_date,
                    "to": to_date,
                    "priceArea": area_code,
                    "lean": "false"  # We want the detailed response with components
                }

                _LOGGER.debug(f"Fetching Stromligning with params: {params}")

                response = await client.fetch(BASE_URL, params=params)

                # Check if we got a valid response with prices
                if response and isinstance(response, dict) and "prices" in response and response["prices"]:
                    _LOGGER.info(f"Successfully fetched Stromligning data for {from_date} to {to_date}")
                    # Add area to response for parser
                    response["priceArea"] = area_code
                    return response
                else:
                    _LOGGER.debug(f"No valid data from Stromligning for {from_date} to {to_date}, trying next range")

            # If we've tried all date ranges and still have no data, log a warning
            _LOGGER.warning("No valid data found from Stromligning after trying multiple date ranges")
            return None
        except Exception as e:
            _LOGGER.error(f"Error fetching Stromligning data: {e}")
            return None
