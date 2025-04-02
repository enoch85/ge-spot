"""Base API implementation for energy prices."""
import logging
import datetime
import aiohttp
import asyncio
from abc import ABC, abstractmethod

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

class BaseEnergyAPI(ABC):
    """Base class for energy price APIs with robust error handling."""
    
    def __init__(self, config):
        """Initialize the API."""
        self.config = config
        self.session = None
        self.vat = config.get("vat", 0.0)
        
    async def _ensure_session(self):
        """Ensure that we have an aiohttp session."""
        try:
            if self.session is None:
                _LOGGER.debug(f"Creating new aiohttp session for {self.__class__.__name__}")
                self.session = aiohttp.ClientSession()
        except Exception as e:
            _LOGGER.error(f"Error creating session in {self.__class__.__name__}: {str(e)}")
            
    async def close(self):
        """Close the session."""
        if self.session:
            try:
                await self.session.close()
            except Exception as e:
                _LOGGER.error(f"Error closing session: {str(e)}")
            finally:
                self.session = None
    
    async def fetch_day_ahead_prices(self, area, currency, date):
        """Fetch day-ahead prices for a specific area and date."""
        try:
            # Ensure we have a session
            await self._ensure_session()
            
            if not self.session:
                _LOGGER.error(f"Could not create session for {self.__class__.__name__}")
                return None
            
            # Format the date consistently
            if isinstance(date, datetime.datetime):
                date_str = date.strftime("%Y-%m-%d")
            else:
                date_str = date
                
            # This will be implemented by subclasses to fetch actual data
            raw_data = await self._fetch_prices(area, currency, date_str)
            
            if not raw_data:
                return None
                
            # Process the data into a consistent format for the adapter
            processed_data = self._process_prices(raw_data, area, currency, date_str)
            
            return processed_data
            
        except Exception as e:
            _LOGGER.error(f"Error fetching day-ahead prices: {str(e)}")
            return None
    
    @abstractmethod
    async def _fetch_prices(self, area, currency, date_str):
        """Fetch raw price data from the API. To be implemented by subclasses."""
        pass
        
    def _process_prices(self, raw_data, area, currency, date_str):
        """Process raw price data into a consistent format.
        
        The expected output format is a list of dictionaries with:
        - start: datetime for the start of the period (timezone-aware)
        - end: datetime for the end of the period (timezone-aware)
        - value: price value
        """
        # Default implementation - subclasses should override if needed
        return raw_data
    
    def _apply_vat(self, price):
        """Apply VAT to price."""
        if price is None:
            return None
        return price * (1 + self.vat)
