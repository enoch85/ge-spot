"""API implementation for Amber Energy."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from aiohttp import ClientSession

from .base.api import PriceAPIBase
from .base.error_handler import retry_with_backoff
from .base.data_structure import StandardizedPriceData
from .parsers.amber_parser import AmberParser
from ..const.sources import Source
from ..const.currencies import Currency
from ..const.network import Network
from ..const.api import Amber

_LOGGER = logging.getLogger(__name__)

class AmberAPI(PriceAPIBase):
    """API client for Amber Energy."""

    def __init__(self, session: Optional[ClientSession] = None):
        """Initialize the Amber API client."""
        super().__init__(session)
        self.parser = AmberParser()
        self.base_url = Network.URLs.AMBER

    @retry_with_backoff(max_attempts=Network.Defaults.RETRY_COUNT,
                       base_delay=Network.Defaults.RETRY_BASE_DELAY)
    async def fetch_raw_data(self, area: str, reference_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Fetch raw data from Amber API.
        
        Args:
            area: The area code (postcode in Australia)
            reference_time: Optional reference time
            
        Returns:
            Raw API response data
        """
        if not reference_time:
            reference_time = datetime.now(timezone.utc)
        
        # Calculate dates for the query (we want past 24h and next 24h if available)
        today = reference_time.date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        
        start_date = yesterday.isoformat()
        end_date = tomorrow.isoformat()
        
        # Construct the API URL
        api_key = self.config.get('api_key')
        if not api_key:
            _LOGGER.error("No API key provided for Amber API")
            return []
        
        url = f"{self.base_url}/prices?site_id={area}&start_date={start_date}&end_date={end_date}"
        
        # Make the API request
        async with self.session.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=Network.Defaults.TIMEOUT
        ) as response:
            if response.status != 200:
                _LOGGER.error(f"Error fetching Amber data: HTTP {response.status}")
                return []
            
            try:
                data = await response.json()
                if not data or not isinstance(data, list):
                    _LOGGER.error(f"Unexpected Amber data format: {data}")
                    return []
                
                return data
            except Exception as e:
                _LOGGER.error(f"Error parsing Amber response: {e}")
                return []
    
    async def parse_raw_data(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse raw Amber data into StandardizedPriceData format.
        
        Args:
            data: Raw API response data
            
        Returns:
            Standardized price data
        """
        try:
            return self.parser.parse(data, area=None)
        except Exception as e:
            _LOGGER.error(f"Error parsing Amber data: {e}")
            return {}
    
    async def fetch_day_ahead_prices(self, area: str, currency: str = Currency.AUD, 
                                    reference_time: Optional[datetime] = None,
                                    vat: Optional[float] = None,
                                    include_vat: bool = False,
                                    session: Optional[ClientSession] = None) -> Dict[str, Any]:
        """Fetch day-ahead prices from Amber.
        
        Args:
            area: The NEM region code (postcode in Australia)
            currency: Currency code (defaults to AUD)
            reference_time: Optional reference time
            vat: Optional VAT rate
            include_vat: Whether to include VAT
            session: Optional session
            
        Returns:
            Standardized price data
        """
        if session:
            self.session = session
        
        try:
            raw_data = await self.fetch_raw_data(area, reference_time)
            if not raw_data:
                _LOGGER.warning(f"No Amber data received for area {area}")
                return {
                    "source": Source.AMBER,
                    "area": area,
                    "currency": Currency.AUD,
                    "hourly_prices": {},
                    "api_timezone": "Australia/Sydney"  # Default timezone for Australia
                }
            
            parsed_data = await self.parse_raw_data(raw_data)
            if not parsed_data:
                return {
                    "source": Source.AMBER,
                    "area": area,
                    "currency": Currency.AUD,
                    "hourly_prices": {},
                    "api_timezone": "Australia/Sydney"
                }
            
            # Set area and source
            parsed_data["area"] = area
            parsed_data["source"] = Source.AMBER
            
            return parsed_data
            
        except Exception as e:
            _LOGGER.error(f"Error fetching Amber prices for {area}: {e}")
            return {
                "source": Source.AMBER,
                "area": area,
                "currency": Currency.AUD,
                "hourly_prices": {},
                "api_timezone": "Australia/Sydney",
                "error": str(e)
            }