"""Base API implementation for energy prices."""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .session_manager import ensure_session, close_session
from .data_fetch import DataFetcher
from .price_conversion import PriceConverter
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
        
        # Create utilities
        self.data_fetcher = DataFetcher(self)
        self.price_converter = PriceConverter(self)

    async def validate_api_key(self, api_key=None):
        """Validate an API key."""
        return await self.data_fetcher.validate_api_key(api_key)

    async def fetch_day_ahead_prices(self, area, currency, date, hass=None):
        """Fetch day-ahead prices for a specific area and date."""
        return await self.data_fetcher.fetch_day_ahead_prices(area, currency, date, hass)

    async def _convert_price(self, price, from_currency="EUR", from_unit="MWh", to_subunit=None, exchange_rate=None):
        """Convert price using centralized conversion logic."""
        return await self.price_converter.convert_price(
            price, from_currency, from_unit, to_subunit, exchange_rate
        )

    async def close(self):
        """Close the session if we own it."""
        await close_session(self)

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
