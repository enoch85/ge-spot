"""OMIE API client."""
import logging
from datetime import datetime, timezone, timedelta, time
import aiohttp
from typing import Dict, Any, Optional

from .base.base_price_api import BasePriceAPI
from .parsers.omie_parser import OmieParser
from ..const.sources import Source
from ..const.api import Omie
from .base.api_client import ApiClient
from ..const.network import Network
from ..const.currencies import Currency
from ..const.time import TimezoneName
from .utils import fetch_with_retry

_LOGGER = logging.getLogger(__name__)

class OmieAPI(BasePriceAPI):
    """OMIE API client."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, session: Optional[aiohttp.ClientSession] = None, timezone_service=None):
        """Initialize the API client.

        Args:
            config: Configuration dictionary
            session: aiohttp client session
            timezone_service: Timezone service instance
        """
        super().__init__(config, session, timezone_service)

    def _get_source_type(self) -> str:
        """Get the source type for this API.

        Returns:
            Source type string
        """
        return Source.OMIE

    def _get_base_url(self) -> str:
        """Get the base URL for API requests.

        Returns:
            Base URL string
        """
        # Use constant defined in const/api.py if available, otherwise fallback
        return getattr(Omie, 'BASE_URL', "https://api.esios.ree.es/archives/70/download?date=")

    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Dict[str, Any]:
        """Fetch raw price data for the given area.
        
        Args:
            area: Area code (e.g., ES or PT)
            session: Optional session for API requests
            **kwargs: Additional parameters
            
        Returns:
            Raw data from API
        """
        # Use current UTC time as reference
        now_utc = datetime.now(timezone.utc)
        
        client = ApiClient(session=session or self.session)
        try:
            # Always compute today and tomorrow
            today = now_utc.strftime("%Y-%m-%d")
            tomorrow = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")
            
            # Fetch today's data
            url_today = f"{self._get_base_url()}{today}"
            csv_today = await client.fetch(url_today, timeout=Network.Defaults.TIMEOUT, response_format='text')
            
            # Fetch tomorrow's data after 13:00 CET, with retry logic
            now_cet = now_utc.astimezone(timezone(timedelta(hours=1)))
            csv_tomorrow = None
            
            if now_cet.hour >= 13:
                url_tomorrow = f"{self._get_base_url()}{tomorrow}"
                
                async def fetch_tomorrow():
                    return await client.fetch(url_tomorrow, timeout=Network.Defaults.TIMEOUT, response_format='text')
                
                def is_data_available(data):
                    return data and isinstance(data, str) and data.strip()
                
                local_tz = TimezoneName.EUROPE_LISBON if area and area.upper() == "PT" else TimezoneName.EUROPE_MADRID
                
                csv_tomorrow = await fetch_with_retry(
                    fetch_tomorrow,
                    is_data_available,
                    retry_interval=1800,
                    end_time=time(23, 50),
                    local_tz_name=local_tz
                )
            
            # Parse the data from both today and tomorrow
            parser = self.get_parser_for_area(area)
            combined_hourly_prices = {}
            
            if csv_today and isinstance(csv_today, str) and csv_today.strip():
                parsed_today = parser.parse({"raw_data": csv_today, "target_date": today, "area": area}) # Pass area
                # Use 'hourly_raw' key from parser result
                if parsed_today and "hourly_raw" in parsed_today:
                    combined_hourly_prices.update(parsed_today["hourly_raw"])
            
            if csv_tomorrow and isinstance(csv_tomorrow, str) and csv_tomorrow.strip():
                parsed_tomorrow = parser.parse({"raw_data": csv_tomorrow, "target_date": tomorrow, "area": area}) # Pass area
                # Use 'hourly_raw' key from parser result
                if parsed_tomorrow and "hourly_raw" in parsed_tomorrow:
                    combined_hourly_prices.update(parsed_tomorrow["hourly_raw"])
            
            # Return standardized data structure with ISO timestamps
            return {
                "hourly_raw": combined_hourly_prices,
                "timezone": self.get_timezone_for_area(area),
                "currency": Currency.EUR,
                "source_name": "omie",
                "raw_data": {
                    "today": csv_today,
                    "tomorrow": csv_tomorrow,
                    "timestamp": now_utc.isoformat(),
                    "area": area
                },
            }
        finally:
            if session is None and client:
                await client.close()

    def get_timezone_for_area(self, area: str) -> str:
        """Get the timezone for a specific area.

        Args:
            area: Area code

        Returns:
            Timezone string
        """
        if area and area.upper() == "PT": # Check area explicitly
            return "Europe/Lisbon"
        else:
            # Default to Madrid timezone for ES or unspecified
            return "Europe/Madrid"

    def get_parser_for_area(self, area: str) -> Any:
        """Get the appropriate parser for the area.

        Args:
            area: Area code

        Returns:
            Parser instance
        """
        # OMIE parser might be generic, or could potentially adapt based on area if needed
        return OmieParser()
