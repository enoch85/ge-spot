"""API handler for EPEX SPOT."""
import logging
import datetime
from datetime import timezone, timedelta, time
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List

from .base.api_client import ApiClient
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from .parsers.epex_parser import EpexParser
from ..utils.date_range import generate_date_ranges
from .base.base_price_api import BasePriceAPI
from .utils import fetch_with_retry
from ..const.time import TimezoneName

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.epexspot.com/en/market-results"

class EpexAPI(BasePriceAPI):
    """API client for EPEX SPOT."""

    def _get_source_type(self) -> str:
        """Get the source type identifier.
        
        Returns:
            Source type identifier
        """
        return Source.EPEX
    
    def _get_base_url(self) -> str:
        """Get the base URL for the API.
        
        Returns:
            Base URL as string
        """
        return BASE_URL
        
    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Dict[str, Any]:
        """Fetch raw data from EPEX SPOT API.
        
        Args:
            area: Area code
            session: Optional aiohttp session
            
        Returns:
            Dictionary with raw data
        """
        client = ApiClient(session=session or self.session)
        try:
            # Use UTC for all reference times
            now_utc = datetime.datetime.now(timezone.utc)
            
            # Always compute today and tomorrow
            today = now_utc.strftime("%Y-%m-%d")
            tomorrow = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")
            
            # Fetch today's data
            raw_today = await self._fetch_data(client, area, today)
            
            # Fetch tomorrow's data after 13:00 CET, with retry logic
            now_cet = now_utc.astimezone(timezone(timedelta(hours=1)))
            raw_tomorrow = None
            
            if now_cet.hour >= 13:
                async def fetch_tomorrow():
                    return await self._fetch_data(client, area, tomorrow)
                
                def is_data_available(data):
                    parser = self.get_parser_for_area(area)
                    parsed = parser.parse(data) if data else None
                    return parsed and parsed.get("hourly_prices")
                
                raw_tomorrow = await fetch_with_retry(
                    fetch_tomorrow,
                    is_data_available,
                    retry_interval=1800,
                    end_time=time(23, 50),
                    local_tz_name=TimezoneName.EUROPE_BERLIN
                )
                
                if not raw_tomorrow:
                    _LOGGER.warning(f"Failed to fetch EPEX tomorrow's data. Proceeding without it.")
            
            # Parse data using appropriate parser
            parser = self.get_parser_for_area(area)
            hourly_raw = {}
            
            if raw_today:
                parsed_today = parser.parse(raw_today)
                if parsed_today and "hourly_prices" in parsed_today:
                    hourly_raw.update(parsed_today["hourly_prices"])
            
            if raw_tomorrow:
                parsed_tomorrow = parser.parse(raw_tomorrow)
                if parsed_tomorrow and "hourly_prices" in parsed_tomorrow:
                    hourly_raw.update(parsed_tomorrow["hourly_prices"])
            
            # Extract metadata
            metadata = parser.extract_metadata(raw_today if raw_today else raw_tomorrow)
            
            return {
                "hourly_raw": hourly_raw,
                "timezone": metadata.get("timezone", "Europe/Berlin"),
                "currency": metadata.get("currency", "EUR"),
                "source_name": "epex",
                "raw_data": {
                    "today": raw_today,
                    "tomorrow": raw_tomorrow,
                    "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
                    "area": area
                },
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
        return "Europe/Berlin"
    
    def get_parser_for_area(self, area: str) -> Any:
        """Get parser for the area.
        
        Args:
            area: Area code
            
        Returns:
            Parser instance
        """
        return EpexParser()

    async def _fetch_data(self, client, area, date_str):
        """Fetch data from EPEX SPOT.
        
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
        date_ranges = generate_date_ranges(date_obj, Source.EPEX)
        
        # EPEX uses trading_date and delivery_date
        # We'll use the first range (today to tomorrow) as our primary range
        today_start, tomorrow_end = date_ranges[0]
        
        # Format dates for the query
        trading_date = today_start.strftime("%Y-%m-%d")
        delivery_date = tomorrow_end.strftime("%Y-%m-%d")
        
        params = {
            "market_area": area,
            "auction": "MRC",
            "trading_date": trading_date,
            "delivery_date": delivery_date,
            "modality": "Auction",
            "sub_modality": "DayAhead",
            "data_mode": "table"
        }
        
        _LOGGER.debug(f"Fetching EPEX with params: {params}")
        
        response = await client.fetch(BASE_URL, params=params)

        # Add detailed logging to inspect the response
        _LOGGER.debug(f"ApiClient.fetch returned: type={type(response)}, value={repr(response)}")

        # Check response status (where the error occurred previously)
        if response and hasattr(response, 'status') and response.status == 200: # Added hasattr check for safety
            try:
                text_content = await response.text()
                _LOGGER.debug(f"EPEX API request successful (Status {response.status}). Response text length: {len(text_content)}")
                return text_content
            except Exception as e:
                _LOGGER.error(f"Error reading EPEX response text: {e}")
                return None
        elif response and hasattr(response, 'status'): # Added hasattr check
            error_text = "N/A"
            try:
                error_text = await response.text()
            except Exception:
                pass
            _LOGGER.warning(
                f"EPEX API request failed: Status {response.status}, Response: {error_text[:200]}..."
            )
            return None
        elif isinstance(response, str): # Handle case where response IS a string
             _LOGGER.warning(f"EPEX API request returned a string directly: {response[:200]}...")
             # Return None as it's unexpected and likely an error page.
             return None
        else: # Handle None or other unexpected types
            _LOGGER.warning(f"EPEX API request failed: No valid response received (type: {type(response)}).")
            return None
