"""Base API implementation for energy prices."""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ...const import (
    CONF_API_KEY,
    REGION_TO_CURRENCY,
    ENERGY_UNIT_CONVERSION,
    CONF_DISPLAY_UNIT,
    DISPLAY_UNIT_CENTS,
)
from .session_manager import register_shutdown_task, close_all_sessions
from .price_converter import PriceConverter
from .data_processor import DataProcessor
from ...utils.timezone_utils import localize_datetime

_LOGGER = logging.getLogger(__name__)

class BaseEnergyAPI(ABC):
    """Base class for energy price APIs with robust error handling."""

    def __init__(self, config):
        """Initialize the API."""
        self.config = config
        self.session = None
        self.vat = config.get("vat", 0.0)
        self._currency = config.get("currency", "EUR")
        self._area = config.get("area")
        self._date_str = None
        self._last_fetched = None
        self._last_successful_fetch = None
        self._cache = {}  # Cache to store API responses
        self._cache_ttl = config.get("cache_ttl", 60)  # Cache TTL in minutes
        self.hass = None  # Will be set when used with Home Assistant
        self._owns_session = False  # Track if we created the session
        
        # Create price converter instance
        self.price_converter = PriceConverter(self)
        
        # Create data processor instance
        self.data_processor = DataProcessor(self)
        
    async def validate_api_key(self, api_key=None):
        """Validate an API key."""
        # Use provided key or get from config
        key_to_validate = api_key or self.config.get(CONF_API_KEY) or self.config.get("api_key")

        if not key_to_validate:
            _LOGGER.warning("No API key to validate")
            return False

        try:
            # Implementation depends on the specific API
            _LOGGER.debug(f"Validating API key (starting with {key_to_validate[:5]}...)")

            # Default implementation - will be overridden by subclasses
            # Simply try to fetch data with the key
            test_config = dict(self.config)
            test_config[CONF_API_KEY] = key_to_validate

            # Create a temporary instance with the test config
            temp_instance = self.__class__(test_config)
            temp_owns_session = False

            # Use existing session if available to avoid creating too many
            if hasattr(self, "session") and self.session and not self.session.closed:
                temp_instance.session = self.session
            else:
                # Create a session for validation if needed
                await temp_instance.data_processor._ensure_session()
                temp_owns_session = True

            # Try to fetch data
            result = await temp_instance._fetch_data()

            # Close the temporary instance session if we created it
            if temp_owns_session and hasattr(temp_instance, 'close'):
                await temp_instance.close()

            # Check if we got a valid response
            if result:
                _LOGGER.info("API key validation successful")
                return True
            else:
                _LOGGER.warning("API key validation failed: No data returned")
                return False

        except Exception as e:
            _LOGGER.error(f"API key validation error: {e}")
            return False

    async def fetch_day_ahead_prices(self, area, currency, date, hass=None):
        """Fetch day-ahead prices for a specific area and date."""
        return await self.data_processor.fetch_day_ahead_prices(area, currency, date, hass)

    async def _convert_price(self, price, from_currency="EUR", from_unit="MWh", to_subunit=None, exchange_rate=None):
        """Convert price using centralized conversion logic."""
        return await self.price_converter.convert_price(price, from_currency, from_unit, to_subunit, exchange_rate)

    async def close(self):
        """Close the session if we own it."""
        if self.session and self._owns_session and not self.session.closed:
            try:
                await self.session.close()
                _LOGGER.debug(f"Closed session for {self.__class__.__name__}")
            except Exception as e:
                _LOGGER.error(f"Error closing session: {str(e)}")
            finally:
                self.session = None
                self._owns_session = False

    def _get_now(self):
        """Get current datetime in Home Assistant's timezone if available."""
        if hasattr(self, 'hass') and self.hass:
            now_utc = dt_util.utcnow()
            return localize_datetime(now_utc, self.hass)
        return dt_util.now()

    @abstractmethod
    async def _fetch_data(self):
        """Fetch raw price data from the API. To be implemented by subclasses."""
        pass

    @abstractmethod
    async def _process_data(self, raw_data):
        """Process raw price data into a consistent format.

        The expected output format is a dictionary with keys like:
        - current_price: price for current hour
        - next_hour_price: price for next hour
        - day_average_price: average price for the day
        - peak_price: highest price of the day
        - off_peak_price: lowest price of the day
        - hourly_prices: dict mapping hour strings to prices
        - raw_values: dict mapping keys to raw values before conversion
        """
        pass
