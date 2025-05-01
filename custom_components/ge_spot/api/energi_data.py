"""API handler for Energi Data Service."""
import logging
import datetime
from datetime import timezone, timedelta, time
import json
from typing import Dict, Any, Optional

from .base.api_client import ApiClient
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from .parsers.energi_data_parser import EnergiDataParser
from ..utils.date_range import generate_date_ranges
from .base.base_price_api import BasePriceAPI
from .utils import fetch_with_retry
from ..const.time import TimezoneName

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
        
    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Dict[str, Any]:
        """Fetch raw data from Energi Data Service API.
        
        Args:
            area: Area code
            session: Optional aiohttp session
            **kwargs: Additional keyword arguments (e.g., reference_time)
            
        Returns:
            Dictionary containing raw data and metadata for the parser.
        """
        client = ApiClient(session=session or self.session)
        try:
            # Use UTC for all reference times
            reference_time = kwargs.get('reference_time', datetime.datetime.now(timezone.utc))
            
            # Always compute today and tomorrow based on reference time
            today = reference_time.strftime("%Y-%m-%d")
            tomorrow = (reference_time + timedelta(days=1)).strftime("%Y-%m-%d")
            
            # Fetch today's data
            raw_today = await self._fetch_data(client, area, today)
            
            # Fetch tomorrow's data after 13:00 CET, with retry logic
            now_utc = datetime.datetime.now(timezone.utc)
            now_cet = now_utc.astimezone(timezone(timedelta(hours=1))) # CET is UTC+1
            raw_tomorrow = None
            
            if now_cet.hour >= 13:
                async def fetch_tomorrow_task(): # Renamed to avoid conflict
                    return await self._fetch_data(client, area, tomorrow)
                
                # The is_data_available check should ideally happen *after* parsing,
                # but for retry logic, we might need a basic check on raw data.
                # Let's check if records exist and are not empty.
                def is_tomorrow_data_present(data):
                    return data and isinstance(data, dict) and data.get("records")
                
                raw_tomorrow = await fetch_with_retry(
                    fetch_tomorrow_task,
                    is_tomorrow_data_present, # Basic check on raw data presence
                    retry_interval=1800,
                    end_time=time(23, 50),
                    local_tz_name=TimezoneName.EUROPE_COPENHAGEN
                )
            
            # --- No Parsing Here --- 
            # The parser will be called later by DataProcessor
            
            # Return the raw data along with necessary metadata for the parser
            return {
                "raw_data": {
                    "today": raw_today,
                    "tomorrow": raw_tomorrow,
                },
                "timezone": "Europe/Copenhagen", # EnergiDataService API timezone context
                "currency": "DKK", # Default currency, parser might override
                "area": area,
                "source": self.source_type,
                "fetched_at": datetime.datetime.now(timezone.utc).isoformat(),
            }
        finally:
            if session is None and client:
                await client.close()
    
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

    async def _fetch_data(self, client, area, date_str):
        """Fetch data from Energi Data Service.
        
        Args:
            client: API client
            area: Area code
            date_str: Date string in YYYY-MM-DD format
            
        Returns:
            Raw response
        """
        # Parse the provided date string
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        
        # Generate date ranges to try
        date_ranges = generate_date_ranges(date_obj, Source.ENERGI_DATA_SERVICE)

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
