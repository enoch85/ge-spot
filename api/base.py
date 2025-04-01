import logging
import datetime
import aiohttp
import asyncio
from abc import ABC, abstractmethod

_LOGGER = logging.getLogger(__name__)

class BaseEnergyAPI(ABC):
    """Base class for energy price APIs."""
    
    def __init__(self, config):
        """Initialize the API."""
        self.config = config
        self.session = None
        self.vat = config.get("vat", 0.0)
        
    async def _ensure_session(self):
        """Ensure that we have an aiohttp session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
            
    async def close(self):
        """Close the session."""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def async_get_data(self):
        """Get data from the API."""
        await self._ensure_session()
        try:
            data = await self._fetch_data()
            if data:
                return self._process_data(data)
            return None
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout while fetching data from %s", self.__class__.__name__)
            raise
        except Exception as e:
            _LOGGER.error("Error fetching data from %s: %s", self.__class__.__name__, e, exc_info=True)
            raise
            
    @abstractmethod
    async def _fetch_data(self):
        """Fetch data from the API. To be implemented by subclasses."""
        raise NotImplementedError
        
    def _process_data(self, data):
        """Process the data. Can be overridden by subclasses."""
        return data
        
    def _apply_vat(self, price):
        """Apply VAT to price."""
        if price is None:
            return None
        return price * (1 + self.vat)
        
    def _get_now(self):
        """Get current datetime with timezone awareness."""
        return datetime.datetime.now(datetime.timezone.utc)
