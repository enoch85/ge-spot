"""Currency exchange rate service for GE-Spot."""
import logging
import aiohttp
import aiofiles
import xml.etree.ElementTree as ET
import datetime
import json
import os
import time
from homeassistant.helpers.event import async_track_time_change

from ..const.currencies import Currency
from ..const.network import Network
from ..const.api import ECB
from ..const.attributes import Attributes
from ..api.base.error_handler import retry_with_backoff

_LOGGER = logging.getLogger(__name__)

class ExchangeRateService:
    """Service to fetch and cache currency exchange rates."""

    def __init__(self, session=None, cache_file=None):
        """Initialize the exchange rate service."""
        self.session = session
        self.cache_file = cache_file or self._get_default_cache_path()
        self.rates = {}
        self.last_update = 0
        self.hass = None
        self._update_listeners = []
        self._handlers_registered = False
        self._last_scheduled_update = 0
        self._min_update_interval = 600  # 10 minutes

    def _get_default_cache_path(self):
        """Get default path for cache file."""
        try:
            home_dir = os.path.expanduser("~")
            return os.path.join(home_dir, ".ge_spot_exchange_rates.json")
        except Exception:
            return "/tmp/ge_spot_exchange_rates.json"

    async def _ensure_session(self):
        """Ensure we have an aiohttp session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """Close the session."""
        if self.session:
            await self.session.close()
            self.session = None

    @retry_with_backoff(max_retries=Network.Defaults.RETRY_COUNT)
    async def _fetch_ecb_rates(self):
        """Fetch exchange rates from European Central Bank API."""
        await self._ensure_session()

        try:
            async with self.session.get(Network.URLs.ECB,
                                      timeout=Network.Defaults.HTTP_TIMEOUT) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to fetch exchange rates: HTTP %s", response.status)
                    return None

                xml_data = await response.text()
                return self._parse_ecb_xml(xml_data)
        except Exception as e:
            _LOGGER.error("Error fetching exchange rates: %s", e)
            return None

    def _parse_ecb_xml(self, xml_data):
        """Parse ECB exchange rate XML data."""
        try:
            root = ET.fromstring(xml_data)
            ns = {
                "gesmes": ECB.XML_NAMESPACE_GESMES,
                "ecb": ECB.XML_NAMESPACE_ECB
            }

            # ECB always uses EUR as the base currency
            rates = {Currency.EUR: 1.0, Currency.CENTS: 100.0}  # Add cents with fixed rate to EUR

            # Find exchange rates in the XML
            for cube in root.findall(".//ecb:Cube[@currency]", ns):
                currency = cube.attrib.get("currency")
                rate = float(cube.attrib.get("rate"))
                rates[currency] = rate

            _LOGGER.info("Fetched %d exchange rates", len(rates)-1)
            return rates
        except Exception as e:
            _LOGGER.error("Error parsing ECB XML: %s", e)
            return None

    async def _load_cache(self):
        """Load exchange rates from cache file asynchronously."""
        if not os.path.exists(self.cache_file):
            return False

        try:
            modified_time = os.path.getmtime(self.cache_file)

            async with aiofiles.open(self.cache_file, "r") as f:
                content = await f.read()
                data = json.loads(content)

            if not data or "rates" not in data:
                return False

            self.rates = data["rates"]

            # Ensure cents currency is always available
            if Currency.CENTS not in self.rates:
                self.rates[Currency.CENTS] = 100.0

            self.last_update = data.get("timestamp", modified_time)

            age = time.time() - self.last_update
            _LOGGER.info(
                "Loaded exchange rates from cache (age: %.1fs, currencies: %d)",
                age, len(self.rates)
            )
            return True
        except Exception as e:
            _LOGGER.error("Error loading exchange rate cache: %s", e)
            return False

    async def _save_cache(self):
        """Save exchange rates to cache file asynchronously."""
        if not self.rates:
            return False

        try:
            data = {
                "rates": self.rates,
                "timestamp": time.time(),
                "date": datetime.datetime.now().isoformat()
            }

            async with aiofiles.open(self.cache_file, "w") as f:
                await f.write(json.dumps(data))

            _LOGGER.debug("Saved exchange rates to %s", self.cache_file)
            return True
        except Exception as e:
            _LOGGER.error("Error saving exchange rate cache: %s", e)
            return False

    async def get_rates(self, force_refresh=False):
        """Get exchange rates (from cache or fresh fetch)."""
        now = time.time()
        cache_loaded = False
        if not self.rates: # If no rates in memory
            cache_loaded = await self._load_cache()

        # Decide if fetch is needed
        needs_fetch = force_refresh or not self.rates # Fetch if forced or no rates in memory/cache

        if needs_fetch:
            fresh_rates = None
            fetch_exception = None
            try:
                _LOGGER.debug("Attempting to fetch fresh exchange rates from ECB.")
                fresh_rates = await self._fetch_ecb_rates() # Decorated with retry
            except Exception as e:
                fetch_exception = e # Store exception
                _LOGGER.warning("Fetching fresh ECB rates failed after retries: %s", e)

            if fresh_rates:
                _LOGGER.info("Successfully fetched fresh exchange rates.")
                self.rates = fresh_rates
                self.last_update = now
                await self._save_cache()
                # Fall through to return self.rates
            elif self.rates: # Fetch failed, but we have rates (from memory or loaded cache)
                _LOGGER.warning("Using existing rates as fresh fetch failed.")
                # Fall through to return self.rates
            else: # Fetch failed AND we still have no rates
                _LOGGER.error("Failed to fetch exchange rates and no cache available.")
                # Raise the original exception if it exists, otherwise a generic one
                if fetch_exception:
                    raise fetch_exception # Raise the original error (e.g., ClientConnectorError)
                else:
                    # Should not happen if fetch was attempted, but as a fallback
                    raise ValueError("Could not retrieve exchange rates (fetch attempt failed silently)")

        # Return rates (either fresh, loaded from cache, or from memory)
        if not self.rates:
             # This case should only be hit if fetch wasn't needed but rates are somehow empty.
             _LOGGER.error("Exchange rates are unexpectedly empty after processing.")
             raise ValueError("Exchange rates unavailable.")

        return self.rates

    async def convert(self, amount, from_currency, to_currency):
        """Convert an amount from one currency to another."""
        if from_currency == to_currency or amount is None:
            return amount

        rates = await self.get_rates()

        # Special handling for cents currency
        if from_currency == Currency.CENTS and to_currency == Currency.USD:
            # Convert from cents to USD (divide by 100)
            result = amount / 100.0
            _LOGGER.debug(
                "Currency conversion: %s %s → %s %s (cents to USD)",
                amount, from_currency, result, to_currency
            )
            return result

        if from_currency == Currency.USD and to_currency == Currency.CENTS:
            # Convert from USD to cents (multiply by 100)
            result = amount * 100.0
            _LOGGER.debug(
                "Currency conversion: %s %s → %s %s (USD to cents)",
                amount, from_currency, result, to_currency
            )
            return result

        # Check if we have the rates
        if from_currency not in rates or to_currency not in rates:
            _LOGGER.error(
                "Missing exchange rates for %s → %s",
                from_currency, to_currency
            )
            raise ValueError(f"Missing exchange rates for {from_currency} → {to_currency}")

        # EUR-based conversion: amount / from_rate * to_rate
        from_rate = rates[from_currency]
        to_rate = rates[to_currency]

        result = amount / from_rate * to_rate
        _LOGGER.debug(
            "Currency conversion: %s %s → %s %s (rates: %s, %s)",
            amount, from_currency, result, to_currency, from_rate, to_rate
        )

        return result

    def get_exchange_rate_info(self, from_currency=Currency.EUR, to_currency=None):
        """Get exchange rate information between two currencies.

        Centralized implementation that returns consistently formatted exchange rate info.

        Args:
            from_currency: Source currency
            to_currency: Target currency

        Returns:
            Dict with timestamp, rate, and formatted rate information
        """
        # Format timestamp
        last_updated_iso = datetime.datetime.fromtimestamp(
            self.last_update, datetime.timezone.utc).isoformat() if self.last_update else None

        # If no rates available or missing currencies
        if not self.rates or from_currency not in self.rates:
            return {
                Attributes.EXCHANGE_RATE_TIMESTAMP: last_updated_iso,
                "rates": None
            }

        if to_currency and to_currency not in self.rates:
            _LOGGER.warning("Currency %s not found in exchange rates", to_currency)
            return {
                Attributes.EXCHANGE_RATE_TIMESTAMP: last_updated_iso,
                "rates": None,
                "error": f"Currency {to_currency} not found"
            }

        # Calculate exchange rate
        if to_currency:
            from_rate = self.rates[from_currency]
            to_rate = self.rates[to_currency]
            exchange_rate = to_rate / from_rate

            # Return using keys that will be directly used in attributes
            return {
                "timestamp": last_updated_iso,
                "rate": exchange_rate,
                "formatted": f"1 {from_currency} = {exchange_rate:.4f} {to_currency}"
            }
        else:
            # Return all rates relative to from_currency
            result = {
                Attributes.EXCHANGE_RATE_TIMESTAMP: last_updated_iso,
                "base": from_currency,
                "rates": {}
            }

            for currency, rate in self.rates.items():
                if currency != from_currency:
                    converted_rate = rate / self.rates[from_currency]
                    result["rates"][currency] = converted_rate

            return result

    def register_update_handlers(self, hass):
        """Register update handlers with Home Assistant.

        This sets up scheduled updates at specific times and on restart.

        Args:
            hass: Home Assistant instance
        """
        if not hass:
            _LOGGER.warning("Cannot register update handlers: no Home Assistant instance")
            return

        # Only register handlers once
        if self._handlers_registered:
            _LOGGER.debug("Exchange rate update handlers already registered")
            return

        self.hass = hass

        # Update on startup
        self.hass.bus.async_listen_once("homeassistant_started", self._handle_startup_update)

        # Set up scheduled updates at specific times
        update_times = [
            {"hour": 0, "minute": 0},  # Midnight (00:00)
            {"hour": 6, "minute": 0},  # 06:00
            {"hour": 12, "minute": 0}, # 12:00
            {"hour": 18, "minute": 0}  # 18:00
        ]

        for update_time in update_times:
            listener = async_track_time_change(
                self.hass,
                self._handle_scheduled_update,
                hour=update_time["hour"],
                minute=update_time["minute"]
            )
            self._update_listeners.append(listener)

        self._handlers_registered = True
        _LOGGER.info("Registered exchange rate update handlers")

    async def _handle_startup_update(self, _event):
        """Handle exchange rate update on HA startup."""
        _LOGGER.info("Updating exchange rates on Home Assistant startup")
        try:
            await self.get_rates(force_refresh=True)
            self._last_scheduled_update = time.time()
        except Exception as e:
            _LOGGER.error(f"Error updating exchange rates on startup: {e}")

    async def _handle_scheduled_update(self, _now):
        """Handle scheduled exchange rate update."""
        # Check if enough time has passed since last update to prevent duplicate rapid updates
        current_time = time.time()
        time_since_last = current_time - self._last_scheduled_update

        if time_since_last < self._min_update_interval:
            _LOGGER.debug(
                f"Skipping duplicate exchange rate update at {_now.strftime('%H:%M')} "
                f"(last update was {time_since_last:.1f}s ago)"
            )
            return

        _LOGGER.info(f"Running scheduled exchange rate update at {_now.strftime('%H:%M')}")
        try:
            await self.get_rates(force_refresh=True)
            self._last_scheduled_update = current_time
        except Exception as e:
            _LOGGER.error(f"Error in scheduled exchange rate update: {e}")

# Global instance for reuse
_EXCHANGE_SERVICE = None

async def get_exchange_service(session=None):
    """Get the exchange service singleton."""
    global _EXCHANGE_SERVICE

    if _EXCHANGE_SERVICE is None:
        _EXCHANGE_SERVICE = ExchangeRateService(session)
        await _EXCHANGE_SERVICE.get_rates()  # Initialize rates

    return _EXCHANGE_SERVICE
