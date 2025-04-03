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

class ExchangeRateService:
    """Service to fetch and cache currency exchange rates."""
    
    def __init__(self, session=None, cache_file=None, cache_ttl=86400):
        """Initialize the exchange rate service."""
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
            
            rates = {"EUR": 1.0}  # Base currency is EUR
            
            # Find exchange rates in the XML
            for cube in root.findall(".//ecb:Cube[@currency]", ns):
                currency = cube.attrib.get("currency")
                rate = float(cube.attrib.get("rate"))
                rates[currency] = rate
            
            # Include fallback rates for Nordic currencies if not in ECB data
            if "SEK" not in rates:
                rates["SEK"] = 10.72  # Fallback rate
            if "NOK" not in rates:
                rates["NOK"] = 11.7   # Fallback rate
            if "DKK" not in rates:
                rates["DKK"] = 7.46   # Fallback rate
            
            _LOGGER.info(f"Fetched {len(rates)-1} exchange rates")
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
        """Get exchange rates (from cache or fresh fetch)."""
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
                # If failed to fetch and have no cached rates, use fallback defaults
                self.rates = {
                    "EUR": 1.0,
                    "SEK": 10.72,
                    "NOK": 11.7,
                    "DKK": 7.46,
                    "GBP": 0.85,
                    "AUD": 1.64
                }
                _LOGGER.warning("Using fallback exchange rates")
            
        return self.rates
    
    async def convert(self, amount, from_currency, to_currency):
        """Convert an amount from one currency to another."""
        if from_currency == to_currency or amount is None:
            return amount
            
        rates = await self.get_rates()
        
        # Handle same currency early
        if from_currency == to_currency:
            return amount
            
        # Check if we have the rates
        if from_currency not in rates or to_currency not in rates:
            _LOGGER.warning(f"Missing exchange rates for {from_currency} → {to_currency}")
            return amount  # Return original amount if we can't convert
            
        # EUR-based conversion: amount / from_rate * to_rate
        from_rate = rates[from_currency]
        to_rate = rates[to_currency]
        
        result = amount / from_rate * to_rate
        _LOGGER.debug(f"Currency conversion: {amount} {from_currency} → {result} {to_currency} (rates: {from_rate}, {to_rate})")
        
        return result

# Global instance for reuse
_EXCHANGE_SERVICE = None

async def get_exchange_service(session=None):
    """Get the exchange service singleton."""
    global _EXCHANGE_SERVICE
    
    if _EXCHANGE_SERVICE is None:
        _EXCHANGE_SERVICE = ExchangeRateService(session)
        await _EXCHANGE_SERVICE.get_rates()  # Initialize rates
        
    return _EXCHANGE_SERVICE
