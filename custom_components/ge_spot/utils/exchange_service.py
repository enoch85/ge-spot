"""Currency exchange rate service for GE-Spot."""
import logging
import aiohttp
import xml.etree.ElementTree as ET
import datetime
import json
import os
import time
from typing import Dict, Optional

_LOGGER = logging.getLogger(__name__)

# European Central Bank (ECB) exchange rates API
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

# Fallback exchange rates if API fails
FALLBACK_RATES = {
    "EUR": 1.0,
    "SEK": 11.3,  # 1 EUR = 11.3 SEK
    "NOK": 11.7,  # 1 EUR = 11.7 NOK
    "DKK": 7.46,  # 1 EUR = 7.46 DKK
    "GBP": 0.85,  # 1 EUR = 0.85 GBP
    "AUD": 1.64,  # 1 EUR = 1.64 AUD
}

class ExchangeRateService:
    """Service to fetch and cache currency exchange rates."""
    
    def __init__(self, session=None, cache_file=None, cache_ttl=86400):
        """Initialize the exchange rate service.
        
        Args:
            session: aiohttp session to use for requests
            cache_file: Path to file for caching exchange rates
            cache_ttl: Time to live for cache in seconds (default: 24 hours)
        """
        self.session = session
        self.cache_file = cache_file or self._get_default_cache_path()
        self.cache_ttl = cache_ttl
        self.rates = {}
        self.last_update = 0
    
    def _get_default_cache_path(self):
        """Get default path for cache file."""
        try:
            home_dir = os.path.expanduser("~")
            return os.path.join(home_dir, ".ge_spot_exchange_rates.json")
        except Exception:
            # Fallback for environments where home directory might not be available
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
    
    async def _fetch_ecb_rates(self):
        """Fetch exchange rates from European Central Bank API."""
        await self._ensure_session()
        
        try:
            async with self.session.get(ECB_URL, timeout=10) as response:
                if response.status != 200:
                    _LOGGER.error(f"Failed to fetch exchange rates: HTTP {response.status}")
                    return None
                
                xml_data = await response.text()
                return self._parse_ecb_xml(xml_data)
        except Exception as e:
            _LOGGER.error(f"Error fetching exchange rates: {e}")
            return None
    
    def _parse_ecb_xml(self, xml_data):
        """Parse ECB exchange rate XML data."""
        try:
            root = ET.fromstring(xml_data)
            ns = {
                "gesmes": "http://www.gesmes.org/xml/2002-08-01",
                "ecb": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"
            }
            
            rates = {"EUR": 1.0}  # Base currency is always 1.0
            
            # Find the exchange rates
            for cube in root.findall(".//ecb:Cube[@currency]", ns):
                currency = cube.attrib.get("currency")
                rate = float(cube.attrib.get("rate"))
                rates[currency] = rate
            
            _LOGGER.info(f"Fetched {len(rates)-1} exchange rates from ECB")
            return rates
        except Exception as e:
            _LOGGER.error(f"Error parsing ECB XML: {e}")
            return None
    
    def _load_cache(self):
        """Load exchange rates from cache file."""
        if not os.path.exists(self.cache_file):
            return False
        
        try:
            modified_time = os.path.getmtime(self.cache_file)
            age = time.time() - modified_time
            
            # If cache is too old, don't use it
            if age > self.cache_ttl:
                _LOGGER.debug(f"Exchange rate cache is too old ({age:.1f}s > {self.cache_ttl}s)")
                return False
            
            with open(self.cache_file, "r") as f:
                data = json.load(f)
                
            if not data or "rates" not in data:
                return False
                
            self.rates = data["rates"]
            self.last_update = data.get("timestamp", modified_time)
            
            _LOGGER.info(f"Loaded exchange rates from cache (age: {age:.1f}s, currencies: {len(self.rates)})")
            return True
        except Exception as e:
            _LOGGER.error(f"Error loading exchange rate cache: {e}")
            return False
    
    def _save_cache(self):
        """Save exchange rates to cache file."""
        if not self.rates:
            return False
            
        try:
            data = {
                "rates": self.rates,
                "timestamp": time.time(),
                "date": datetime.datetime.now().isoformat()
            }
            
            with open(self.cache_file, "w") as f:
                json.dump(data, f)
                
            _LOGGER.debug(f"Saved exchange rates to {self.cache_file}")
            return True
        except Exception as e:
            _LOGGER.error(f"Error saving exchange rate cache: {e}")
            return False
    
    async def get_rates(self, force_refresh=False):
        """Get exchange rates (from cache or fresh fetch).
        
        Args:
            force_refresh: Force refresh regardless of cache state
            
        Returns:
            Dictionary of exchange rates
        """
        now = time.time()
        
        # Try to load from cache if we don't have rates or if they're stale
        if not self.rates or now - self.last_update > self.cache_ttl or force_refresh:
            # Try to load from cache first (unless forced refresh)
            if not force_refresh and self._load_cache():
                return self.rates
                
            # Fetch fresh rates if cache is unavailable or too old
            fresh_rates = await self._fetch_ecb_rates()
            if fresh_rates:
                self.rates = fresh_rates
                self.last_update = now
                self._save_cache()
                return self.rates
            elif not self.rates:
                # If we failed to fetch and have no cached rates, use fallback defaults
                self.rates = FALLBACK_RATES.copy()
                _LOGGER.warning("Using fallback exchange rates")
            
        return self.rates
    
    async def convert(self, amount, from_currency, to_currency):
        """Convert an amount from one currency to another.
        
        Args:
            amount: Amount to convert
            from_currency: Source currency code
            to_currency: Target currency code
            
        Returns:
            Converted amount
        """
        if from_currency == to_currency:
            return amount
            
        rates = await self.get_rates()
        
        # Handle same currency early
        if from_currency == to_currency:
            return amount
            
        # Check if we have the rates
        if from_currency not in rates or to_currency not in rates:
            _LOGGER.warning(f"Missing exchange rates for {from_currency} → {to_currency}, using fallback rates")
            
            # Try fallback rates if official rates not available
            if from_currency in FALLBACK_RATES and to_currency in FALLBACK_RATES:
                from_rate = FALLBACK_RATES[from_currency]
                to_rate = FALLBACK_RATES[to_currency]
            else:
                _LOGGER.error(f"No exchange rate found for {from_currency} → {to_currency}, returning original amount")
                return amount
        else:
            from_rate = rates[from_currency]
            to_rate = rates[to_currency]
        
        # Convert: from_amount / from_rate * to_rate
        result = amount / from_rate * to_rate
        _LOGGER.debug(f"Currency conversion: {amount} {from_currency} → {result} {to_currency} (rates: {from_currency}={from_rate}, {to_currency}={to_rate})")
        
        return result

# Global instance for reuse
_EXCHANGE_SERVICE = None

async def get_exchange_service(session=None):
    """Get the exchange service instance."""
    global _EXCHANGE_SERVICE
    
    if _EXCHANGE_SERVICE is None:
        _EXCHANGE_SERVICE = ExchangeRateService(session)
        await _EXCHANGE_SERVICE.get_rates()  # Initialize rates
        
    return _EXCHANGE_SERVICE

async def convert_currency(amount, from_currency, to_currency, session=None):
    """Convert currency (convenience function)."""
    service = await get_exchange_service(session)
    return await service.convert(amount, from_currency, to_currency)
