"""API handler for Nordpool."""
import logging
from datetime import datetime, timezone, timedelta, time
from typing import Dict, Any, Optional

from .base.api_client import ApiClient
from ..const.sources import Source
from ..const.currencies import Currency
from ..const.areas import AreaMapping
from ..const.time import TimeFormat
from ..const.network import Network
from ..const.config import Config
from .parsers.nordpool_parser import NordpoolPriceParser
from ..utils.date_range import generate_date_ranges
from .base.base_price_api import BasePriceAPI
from .base.error_handler import ErrorHandler
from .utils import fetch_with_retry
from ..const.time import TimezoneName

_LOGGER = logging.getLogger(__name__)

class NordpoolAPI(BasePriceAPI):
    """Nordpool API implementation."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, session=None, timezone_service=None):
        """Initialize the API.
        
        Args:
            config: Configuration dictionary
            session: Optional session for API requests
            timezone_service: Optional timezone service
        """
        super().__init__(config, session, timezone_service=timezone_service)
        self.error_handler = ErrorHandler(self.source_type)
        self.parser = NordpoolPriceParser()
    
    def _get_source_type(self) -> str:
        """Get the source type identifier.
        
        Returns:
            Source type identifier
        """
        return Source.NORDPOOL
    
    def _get_base_url(self) -> str:
        """Get the base URL for the API.
        
        Returns:
            Base URL as string
        """
        return Network.URLs.NORDPOOL
    
    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Dict[str, Any]:
        """Fetch raw price data for the given area.
        
        Args:
            area: Area code
            session: Optional session for API requests
            **kwargs: Additional parameters
            
        Returns:
            Raw data from API
        """
        client = ApiClient(session=session or self.session)
        try:
            # Run the fetch with retry logic
            data = await self.error_handler.run_with_retry(
                self._fetch_data,
                client=client,
                area=area,
                reference_time=kwargs.get('reference_time')
            )
            # Check if 'today' data exists within 'raw_data'
            if not data or not isinstance(data, dict) or not data.get('raw_data', {}).get('today'):
                _LOGGER.error(f"Nordpool API returned empty or invalid data for area {area}: {data}")
            return data
        finally:
            if session is None:
                await client.close()
    
    async def _fetch_data(self, client: ApiClient, area: str, reference_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Fetch data from Nordpool.
        
        Args:
            client: API client
            area: Area code
            reference_time: Optional reference time
            
        Returns:
            Dictionary containing raw data and metadata for the parser.
        """
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Map from area code to delivery area
        delivery_area = AreaMapping.NORDPOOL_DELIVERY.get(area, area)

        _LOGGER.debug(f"Fetching Nordpool data for area: {area}, delivery area: {delivery_area}")

        # Generate date ranges to try
        # For Nordpool, we need to handle today and tomorrow separately
        date_ranges = generate_date_ranges(reference_time, Source.NORDPOOL)

        # Fetch today's data (first range is today to tomorrow)
        today_start, today_end = date_ranges[0]
        today = today_start.strftime(TimeFormat.DATE_ONLY)

        params_today = {
            "currency": Currency.EUR,
            "date": today,
            "market": "DayAhead",
            "deliveryArea": delivery_area
        }

        today_data = await client.fetch(self.base_url, params=params_today)

        # Try to fetch tomorrow's data if it's after 13:00 CET (when typically available)
        tomorrow_data = None
        now_utc = datetime.now(timezone.utc)
        now_cet = now_utc.astimezone(timezone(timedelta(hours=1)))

        if now_cet.hour >= 13:
            # Always compute tomorrow as reference_time + 1 day
            tomorrow = (reference_time + timedelta(days=1)).strftime(TimeFormat.DATE_ONLY)
            params_tomorrow = {
                "currency": Currency.EUR,
                "date": tomorrow,
                "market": "DayAhead",
                "deliveryArea": delivery_area
            }
            async def fetch_tomorrow():
                return await client.fetch(self.base_url, params=params_tomorrow)
            def is_data_available(data):
                return data and isinstance(data, dict) and data.get("multiAreaEntries")
            tomorrow_data = await fetch_with_retry(
                fetch_tomorrow,
                is_data_available,
                retry_interval=1800,
                end_time=time(23, 50),
                local_tz_name=TimezoneName.EUROPE_OSLO
            )

        # Construct the dictionary to be returned to FallbackManager/DataProcessor
        # This dictionary should contain everything the parser needs.
        return {
            # No pre-parsing here, just pass the raw responses
            "raw_data": {
                "today": today_data,
                "tomorrow": tomorrow_data,
            },
            "timezone": "Europe/Oslo", # Nordpool API timezone
            "currency": "EUR", # Nordpool API currency
            "area": area, # Pass the area to the parser via this dict
            "source": self.source_type, # Let the parser know the source
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            # Add any other metadata the parser might need from the API adapter context
        }
