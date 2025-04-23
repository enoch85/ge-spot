"""API handler for EPEX SPOT."""
import logging
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List

from ..utils.api_client import ApiClient
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from .parsers.epex_parser import EpexParser
from ..utils.date_range import generate_date_ranges
from .base.base_price_api import BasePriceAPI

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
        parser = EpexParser()
        parsed = parser.parse(data)
        metadata = parser.extract_metadata(data)

        # Build standardized result
        result = {
            "hourly_prices": parsed.get("hourly_prices", {}),  # keys: HH:00 or ISO, values: price in EUR
            "currency": metadata.get("currency", "EUR"),
            "timezone": metadata.get("timezone", "Europe/Berlin"),
            "area": metadata.get("area", "DE"),
            "raw_data": data,  # keep original for debugging/fallback
            "source": Source.EPEX,
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
        return "Europe/Berlin"
    
    def get_parser_for_area(self, area: str) -> Any:
        """Get parser for the area.
        
        Args:
            area: Area code
            
        Returns:
            Parser instance
        """
        return EpexParser()

    async def _fetch_data(self, client, area, reference_time):
        """Fetch data from EPEX SPOT."""
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Generate date ranges to try
        date_ranges = generate_date_ranges(reference_time, Source.EPEX)

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

        # If the first attempt fails, try with other date ranges
        if not response and len(date_ranges) > 1:
            for start_date, end_date in date_ranges[1:]:
                trading_date = start_date.strftime("%Y-%m-%d")
                delivery_date = end_date.strftime("%Y-%m-%d")

                params.update({
                    "trading_date": trading_date,
                    "delivery_date": delivery_date
                })

                _LOGGER.debug(f"Retrying EPEX with alternate dates - trading: {trading_date}, delivery: {delivery_date}")

                response = await client.fetch(BASE_URL, params=params)
                if response:
                    _LOGGER.info(f"Successfully fetched EPEX data with alternate dates")
                    break

        return response
