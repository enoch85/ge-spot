import logging
import datetime
import aiohttp
import asyncio
from abc import ABC, abstractmethod
from ..utils.currency_utils import get_default_currency

_LOGGER = logging.getLogger(__name__)

class BaseEnergyAPI(ABC):
    """Base class for energy price APIs with robust error handling."""
    
    def __init__(self, config):
        """Initialize the API."""
        self.config = config
        self.session = None
        self.vat = config.get("vat", 0.0)
        self._currency = config.get("currency", get_default_currency(config.get("area")))
        
    async def _ensure_session(self):
        """Ensure that we have an aiohttp session."""
        try:
            if self.session is None:
                _LOGGER.debug(f"Creating new aiohttp session for {self.__class__.__name__}")
                self.session = aiohttp.ClientSession()
        except Exception as e:
            _LOGGER.error(f"Error creating session in {self.__class__.__name__}: {str(e)}")
            # Try to create a new session one more time
            try:
                self.session = aiohttp.ClientSession()
            except Exception as e2:
                _LOGGER.error(f"Failed to create session on second attempt: {str(e2)}")
            
    async def close(self):
        """Close the session."""
        if self.session:
            try:
                await self.session.close()
            except Exception as e:
                _LOGGER.error(f"Error closing session: {str(e)}")
            finally:
                self.session = None
    
    async def async_get_data(self):
        """Get data from the API with comprehensive error handling."""
        try:
            # Ensure we have a session
            await self._ensure_session()
            
            if self.session is None:
                _LOGGER.error(f"Could not create session for {self.__class__.__name__}")
                return self._generate_simulated_data()
            
            # Try to get real data
            try:
                data = await self._fetch_data()
                if data:
                    try:
                        processed_data = self._process_data(data)
                        if processed_data:
                            return processed_data
                    except AttributeError as e:
                        _LOGGER.error(f"AttributeError processing data from {self.__class__.__name__}: {str(e)}")
                    except Exception as e:
                        _LOGGER.error(f"Error processing data from {self.__class__.__name__}: {str(e)}")
            except asyncio.TimeoutError:
                _LOGGER.error(f"Timeout while fetching data from {self.__class__.__name__}")
            except AttributeError as e:
                _LOGGER.error(f"AttributeError in {self.__class__.__name__} request: {str(e)}")
                # Try to recreate the session
                try:
                    await self.close()
                    self.session = None
                    await self._ensure_session()
                except Exception as session_error:
                    _LOGGER.error(f"Error recreating session: {str(session_error)}")
            except Exception as e:
                _LOGGER.error(f"Error fetching data from {self.__class__.__name__}: {str(e)}")
            
            # If we get here, we failed to get valid data
            _LOGGER.warning(f"Failed to get valid data from {self.__class__.__name__}, using simulated data")
            return self._generate_simulated_data()
                
        except Exception as e:
            _LOGGER.error(f"Unexpected error in {self.__class__.__name__}: {str(e)}")
            return self._generate_simulated_data()
            
    async def _fetch_with_retry(self, url, params=None, headers=None, timeout=30, retry_count=3):
        """Fetch data from API with retry mechanism."""
        if self.session is None:
            await self._ensure_session()
            if self.session is None:
                _LOGGER.error("Cannot fetch data: session is None")
                return None
                
        for attempt in range(retry_count):
            try:
                _LOGGER.debug(f"Sending request to {url} (attempt {attempt+1}/{retry_count})")
                async with self.session.get(url, params=params, headers=headers, timeout=timeout) as response:
                    if response.status != 200:
                        _LOGGER.error(f"Error response (attempt {attempt+1}/{retry_count}): Status {response.status}")
                        
                        # Try to get the error response body for better debugging
                        try:
                            error_text = await response.text()
                            _LOGGER.error(f"Error response body: {error_text[:500]}...")
                        except Exception as e:
                            _LOGGER.error(f"Could not read error response: {str(e)}")
                            
                        if attempt < retry_count - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        return None
                    
                    try:
                        if response.content_type == 'application/json':
                            return await response.json()
                        else:
                            return await response.text()
                    except Exception as e:
                        _LOGGER.error(f"Error parsing response: {str(e)}")
                        if attempt < retry_count - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return None
                        
            except asyncio.TimeoutError:
                _LOGGER.error(f"Timeout (attempt {attempt+1}/{retry_count})")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except AttributeError as e:
                _LOGGER.error(f"AttributeError in request (attempt {attempt+1}/{retry_count}): {str(e)}")
                # Try to recreate the session
                try:
                    await self.close()
                    self.session = None
                    await self._ensure_session()
                except Exception as session_error:
                    _LOGGER.error(f"Error recreating session: {str(session_error)}")
                
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except Exception as e:
                _LOGGER.error(f"Error in request (attempt {attempt+1}/{retry_count}): {str(e)}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
                
        return None
    
    @abstractmethod
    async def _fetch_data(self):
        """Fetch data from the API. To be implemented by subclasses."""
        raise NotImplementedError
        
    def _process_data(self, data):
        """Process the data. To be implemented by subclasses."""
        return data
        
    def _generate_simulated_data(self):
        """Generate simulated data. Should be implemented by subclasses."""
        _LOGGER.warning(f"{self.__class__.__name__} does not implement _generate_simulated_data")
        now = self._get_now()
        return {
            "current_price": 0.15,  # Default simulated price
            "next_hour_price": 0.16,
            "day_average_price": 0.15,
            "peak_price": 0.20,
            "off_peak_price": 0.10,
            "hourly_prices": {f"{hour:02d}:00:00": 0.15 for hour in range(24)},
            "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "simulated": True,
        }
        
    def _apply_vat(self, price):
        """Apply VAT to price."""
        if price is None:
            return None
        return price * (1 + self.vat)
        
    def _get_now(self):
        """Get current datetime with timezone awareness."""
        return datetime.datetime.now(datetime.timezone.utc)
        
    def _validate_field(self, data, field, expected_type=None):
        """Validate that a field exists in the data and optionally check its type."""
        if data is None:
            return False
            
        if field not in data:
            return False
            
        if expected_type is not None and not isinstance(data[field], expected_type):
            return False
            
        return True
