"""API handler for Energi Data Service."""
import logging
from datetime import datetime, timezone, timedelta, time
import json
from typing import Dict, Any, Optional, List

from ..timezone import TimezoneService
from ..utils.api_client import ApiClient
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from .parsers.energi_data_parser import EnergiDataParser
from ..utils.date_range import generate_date_ranges
from .base.base_price_api import BasePriceAPI

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.energidataservice.dk/dataset/Elspotprices"

class EnergiDataAPI(BasePriceAPI):
    """API client for Energi Data Service."""

    def _get_source_type(self) -> str:
        """Get the source type identifier.
        
        Returns:
            Source type identifier
        """
        return Source.ENERGI_DATA_SERVICE
    
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
        parser = EnergiDataParser()
        parsed = parser.parse(data)
        metadata = parser.extract_metadata(data)

        # Build standardized result
        result = {
            "hourly_prices": parsed.get("hourly_prices", {}),  # keys: HH:00 or ISO, values: price in DKK
            "currency": metadata.get("currency", "DKK"),
            "timezone": metadata.get("timezone", "Europe/Copenhagen"),
            "area": metadata.get("area", "DK1"),
            "raw_data": data,  # keep original for debugging/fallback
            "source": Source.ENERGI_DATA_SERVICE,
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
        return "Europe/Copenhagen"
    
    def get_parser_for_area(self, area: str) -> Any:
        """Get parser for the area.
        
        Args:
            area: Area code
            
        Returns:
            Parser instance
        """
        return EnergiDataParser()

    async def _fetch_data(self, client, area, reference_time):
        """Fetch data from Energi Data Service."""
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Generate date ranges to try
        date_ranges = generate_date_ranges(reference_time, Source.ENERGI_DATA_SERVICE)

        # Use area from config or passed parameter
        area_code = area if area else "DK1"  # Default to Western Denmark

        # Try each date range until we get a valid response
        for start_date, end_date in date_ranges:
            # Format dates for Energi Data Service API
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")

            params = {
                "start": f"{start_str}T00:00",
                "end": f"{end_str}T00:00",
                "filter": json.dumps({"PriceArea": area_code}),
                "sort": "HourDK",
                "timezone": "dk",
            }

            _LOGGER.debug(f"Fetching Energi Data Service with params: {params}")

            response = await client.fetch(BASE_URL, params=params)

            # Check if we got a valid response with records
            if response and isinstance(response, dict) and "records" in response and response["records"]:
                _LOGGER.info(f"Successfully fetched Energi Data Service data for {start_str} to {end_str}")
                return response
            else:
                _LOGGER.debug(f"No valid data from Energi Data Service for {start_str} to {end_str}, trying next range")

        # If we've tried all date ranges and still have no data, log a warning
        _LOGGER.warning("No valid data found from Energi Data Service after trying multiple date ranges")
        return None
