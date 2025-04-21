"""Price caching for electricity prices."""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from homeassistant.util import dt as dt_util
from homeassistant.core import HomeAssistant

from ..timezone import TimezoneService
from ..timezone.dst_handler import DSTHandler
from ..const.time import DSTTransitionType

_LOGGER = logging.getLogger(__name__)

class PriceCache:
    """Cache for electricity price data with timezone and DST awareness."""

    def __init__(self, hass: HomeAssistant, config: Optional[Dict[str, Any]] = None):
        """Initialize the price cache."""
        self.hass = hass
        self.config = config or {}
        # Structure: {area: {date_str: {source: data}}}
        self._cache = {}
        # Cache for current execution to avoid redundant calculations
        self._cache_info = None

        # Initialize timezone service and DST handler for default timezone
        # Note: Area-specific timezone service will be created as needed
        self._default_tz_service = TimezoneService(hass, config=self.config)
        self._dst_handler = DSTHandler(dt_util.get_time_zone(hass.config.time_zone) if hass else None)

    def _get_cache_info(self, area: str) -> Dict[str, Any]:
        """Get cache information once to avoid redundant calls."""
        now = dt_util.now()
        today_str = now.strftime("%Y-%m-%d")

        # Create area-specific timezone service with config
        tz_service = TimezoneService(self.hass, area, self.config)
        is_transition, transition_type = tz_service.is_dst_transition_day(now)

        cache_key = f"{area}_{now.isoformat()}"
        if self._cache_info and self._cache_info.get('key') == cache_key:
            return self._cache_info

        hour_key = tz_service.get_current_hour_key()
        now_dst_info = self._dst_handler.get_dst_offset_info(now)
        result = {
            'key': cache_key,
            'area': area,
            'date': today_str,
            'hour_key': hour_key,
            'has_price': False,
            'dst_info': now_dst_info,
            'dst_transition': transition_type if is_transition else "none"
        }

        # IMPORTANT: We only look for the current hour's price in today's data, never in tomorrow's data
        # This ensures we don't mix today's and tomorrow's data
        if area in self._cache and today_str in self._cache[area]:
            _LOGGER.debug(f"Found cache entry for {area} on {today_str}")
            
            # Log all available sources in cache for this area/day
            sources = list(self._cache[area][today_str].keys())
            _LOGGER.debug(f"Available sources in cache for {area}/{today_str}: {sources}")
            
            # First try primary sources
            for source, data in self._cache[area][today_str].items():
                _LOGGER.debug(f"Checking source {source} for hour key {hour_key}")
                
                # Check all possible price fields
                price_found = False
                
                # Check hourly_prices (standard format)
                if "hourly_prices" in data:
                    hourly_keys = list(data["hourly_prices"].keys())
                    _LOGGER.debug(f"Source {source} has hourly_prices with keys: {hourly_keys[:5]}...")
                    
                    # First try exact match
                    if hour_key in data["hourly_prices"]:
                        price = data["hourly_prices"][hour_key]
                        _LOGGER.debug(f"Found price {price} for hour {hour_key} in source {source} hourly_prices")
                        result.update({
                            'has_price': True,
                            'source': source,
                            'price': price,
                            'price_source': 'CACHE_HOURLY',
                            'api_timezone': data.get("api_timezone"),
                            'tz_source': 'API_DATA' if data.get("api_timezone") else 'CONSTANTS',
                            'currency': data.get("currency", "EUR"),
                            'currency_source': 'API_DATA' if data.get("currency") else 'CONSTANTS',
                            'ha_timezone': data.get("ha_timezone"),
                            'full_data': dict(data)
                        })
                        result['full_data']["current_price"] = price
                        result['full_data']["current_hour"] = hour_key
                        price_found = True
                        break
                    else:
                        # Try to find a key that matches the current hour
                        current_hour = int(hour_key.split(":")[0])
                        for key in hourly_keys:
                            if ":" in key:
                                try:
                                    key_hour = int(key.split(":")[0])
                                    if key_hour == current_hour:
                                        price = data["hourly_prices"][key]
                                        _LOGGER.debug(f"Found matching hour in hourly_prices with key {key}: {price}")
                                        result.update({
                                            'has_price': True,
                                            'source': source,
                                            'price': price,
                                            'price_source': 'CACHE_HOURLY_ALT',
                                            'api_timezone': data.get("api_timezone"),
                                            'tz_source': 'API_DATA' if data.get("api_timezone") else 'CONSTANTS',
                                            'currency': data.get("currency", "EUR"),
                                            'currency_source': 'API_DATA' if data.get("currency") else 'CONSTANTS',
                                            'ha_timezone': data.get("ha_timezone"),
                                            'full_data': dict(data)
                                        })
                                        result['full_data']["current_price"] = price
                                        result['full_data']["current_hour"] = hour_key
                                        price_found = True
                                        break
                                except (ValueError, IndexError):
                                    continue
                            
                        if not price_found:
                            _LOGGER.debug(f"Hour key {hour_key} not found in source {source} hourly_prices")
                
                # Check today_hourly_prices if hourly_prices didn't have it
                if not price_found and "today_hourly_prices" in data:
                    today_keys = list(data["today_hourly_prices"].keys())
                    _LOGGER.debug(f"Source {source} has today_hourly_prices with keys: {today_keys[:5]}...")
                    
                    # First try exact match
                    if hour_key in data["today_hourly_prices"]:
                        price = data["today_hourly_prices"][hour_key]
                        _LOGGER.debug(f"Found price {price} for hour {hour_key} in source {source} today_hourly_prices")
                        result.update({
                            'has_price': True,
                            'source': source,
                            'price': price,
                            'price_source': 'CACHE_TODAY',
                            'api_timezone': data.get("api_timezone"),
                            'tz_source': 'API_DATA' if data.get("api_timezone") else 'CONSTANTS',
                            'currency': data.get("currency", "EUR"),
                            'currency_source': 'API_DATA' if data.get("currency") else 'CONSTANTS',
                            'ha_timezone': data.get("ha_timezone"),
                            'full_data': dict(data)
                        })
                        result['full_data']["current_price"] = price
                        result['full_data']["current_hour"] = hour_key
                        price_found = True
                        break
                    else:
                        # Try to find a key that matches the current hour
                        current_hour = int(hour_key.split(":")[0])
                        for key in today_keys:
                            if ":" in key:
                                try:
                                    key_hour = int(key.split(":")[0])
                                    if key_hour == current_hour:
                                        price = data["today_hourly_prices"][key]
                                        _LOGGER.debug(f"Found matching hour in today_hourly_prices with key {key}: {price}")
                                        result.update({
                                            'has_price': True,
                                            'source': source,
                                            'price': price,
                                            'price_source': 'CACHE_TODAY_ALT',
                                            'api_timezone': data.get("api_timezone"),
                                            'tz_source': 'API_DATA' if data.get("api_timezone") else 'CONSTANTS',
                                            'currency': data.get("currency", "EUR"),
                                            'currency_source': 'API_DATA' if data.get("currency") else 'CONSTANTS',
                                            'ha_timezone': data.get("ha_timezone"),
                                            'full_data': dict(data)
                                        })
                                        result['full_data']["current_price"] = price
                                        result['full_data']["current_hour"] = hour_key
                                        price_found = True
                                        break
                                except (ValueError, IndexError):
                                    continue
                            
                        if not price_found:
                            _LOGGER.debug(f"Hour key {hour_key} not found in source {source} today_hourly_prices")
                
                # If no price fields found at all
                if not "hourly_prices" in data and not "today_hourly_prices" in data:
                    _LOGGER.debug(f"Source {source} does not have hourly_prices or today_hourly_prices")
                    # Log all available keys to help diagnose the issue
                    _LOGGER.debug(f"Available keys in source {source}: {list(data.keys())}")
            
            # If no price found in primary sources, check if we have fallback data
            if not result.get('has_price', False):
                _LOGGER.debug("No price found in primary sources, checking fallback data")
                for source, data in self._cache[area][today_str].items():
                    if "fallback_data" in data:
                        _LOGGER.debug(f"Found fallback data in source {source}")
                        for fb_source, fb_data in data["fallback_data"].items():
                            _LOGGER.debug(f"Checking fallback source {fb_source} for hour key {hour_key}")
                            if "hourly_prices" in fb_data and hour_key in fb_data["hourly_prices"]:
                                price = fb_data["hourly_prices"][hour_key]
                                _LOGGER.debug(f"Found price {price} for hour {hour_key} in fallback source {fb_source}")
                                result.update({
                                    'has_price': True,
                                    'source': fb_source,
                                    'primary_source': source,
                                    'price': price,
                                    'price_source': 'CACHE_FALLBACK',
                                    'api_timezone': fb_data.get("api_timezone", data.get("api_timezone")),
                                    'tz_source': 'API_DATA' if fb_data.get("api_timezone") else 'CONSTANTS',
                                    'currency': fb_data.get("currency", data.get("currency", "EUR")),
                                    'currency_source': 'API_DATA' if fb_data.get("currency") else 'CONSTANTS',
                                    'ha_timezone': data.get("ha_timezone"),
                                    'full_data': dict(fb_data)
                                })
                                result['full_data']["current_price"] = price
                                result['full_data']["current_hour"] = hour_key
                                break

        self._cache_info = result
        return result

    def store(self, data: Dict[str, Any], area: str, source: str, last_api_fetch=None) -> bool:
        """Store price data with timezone awareness.

        Args:
            data: The price data to store
            area: The area code (e.g., 'SE1', 'FI')
            source: The data source (e.g., 'nordpool', 'entsoe')
            last_api_fetch: Optional timestamp of when the data was fetched from the API
        """
        if not data:
            return False
            
        # Initialize hourly_prices if it doesn't exist
        if "hourly_prices" not in data:
            data["hourly_prices"] = {}

        # Get today's date in area-specific timezone
        tz_service = TimezoneService(self.hass, area, self.config)
        now = dt_util.now()
        today_str = now.strftime("%Y-%m-%d")

        # Check if today is a DST transition day
        is_transition, transition_type = tz_service.is_dst_transition_day(now)
        if is_transition:
            _LOGGER.debug(f"Storing data for DST transition day ({transition_type})")
            # Add DST transition info to data
            data["dst_transition"] = transition_type

        # Initialize cache structure
        if area not in self._cache:
            self._cache[area] = {}
        if today_str not in self._cache[area]:
            self._cache[area][today_str] = {}

        # Capture timezone information
        ha_timezone = str(self.hass.config.time_zone) if self.hass else str(now.tzinfo)
        api_timezone = data.get("api_timezone")  # API handlers store timezone info here

        # Get area-specific timezone if available
        area_timezone = None
        if tz_service.area_timezone:
            area_timezone = str(tz_service.area_timezone)
            _LOGGER.debug(f"Using area-specific timezone {area_timezone} for cache storage")

        # Store the data with timezone metadata
        cached_data = {
            **data,
            "stored_in_timezone": str(now.tzinfo),
            "cached_at": now.isoformat(),
            "api_timezone": api_timezone if api_timezone else str(now.tzinfo),
            "ha_timezone": ha_timezone,
            "area_timezone": area_timezone,
            "last_api_fetch": last_api_fetch.isoformat() if last_api_fetch else now.isoformat()
        }

        # Log the hourly prices keys before storing
        if "hourly_prices" in cached_data:
            hourly_keys = list(cached_data["hourly_prices"].keys())
            _LOGGER.debug(f"Storing hourly_prices with keys: {hourly_keys[:5]}... ({len(hourly_keys)} total)")
        
        if "today_hourly_prices" in cached_data:
            today_keys = list(cached_data["today_hourly_prices"].keys())
            _LOGGER.debug(f"Storing today_hourly_prices with keys: {today_keys[:5]}... ({len(today_keys)} total)")
        
        # Get current hour key for comparison
        tz_service = TimezoneService(self.hass, area, self.config)
        current_hour_key = tz_service.get_current_hour_key()
        _LOGGER.debug(f"Current hour key at storage time: {current_hour_key}")
        
        # Check if the current hour key exists in the data
        current_hour_price = None
        
        # First check in hourly_prices
        if "hourly_prices" in cached_data and current_hour_key in cached_data["hourly_prices"]:
            current_hour_price = cached_data["hourly_prices"][current_hour_key]
            _LOGGER.debug(f"Current hour key {current_hour_key} found in hourly_prices with value: {current_hour_price}")
        
        # Then check in today_hourly_prices
        elif "today_hourly_prices" in cached_data and current_hour_key in cached_data["today_hourly_prices"]:
            current_hour_price = cached_data["today_hourly_prices"][current_hour_key]
            _LOGGER.debug(f"Current hour key {current_hour_key} found in today_hourly_prices with value: {current_hour_price}")
        
        # If not found in either, try to find it with a different format
        else:
            _LOGGER.warning(f"Current hour key {current_hour_key} not found in any hourly prices data")
            
            # Log all available keys to help diagnose the issue
            if "hourly_prices" in cached_data:
                hourly_keys = list(cached_data["hourly_prices"].keys())
                _LOGGER.debug(f"Available hourly_prices keys: {hourly_keys}")
                
                # Try to find a key that might match the current hour
                current_hour = int(current_hour_key.split(":")[0])
                for key in hourly_keys:
                    if ":" in key:
                        try:
                            key_hour = int(key.split(":")[0])
                            if key_hour == current_hour:
                                current_hour_price = cached_data["hourly_prices"][key]
                                _LOGGER.debug(f"Found matching hour in hourly_prices with key {key}: {current_hour_price}")
                                # Store it with the standard format key as well
                                cached_data["hourly_prices"][current_hour_key] = current_hour_price
                                break
                        except (ValueError, IndexError):
                            continue
            
            if current_hour_price is None and "today_hourly_prices" in cached_data:
                today_keys = list(cached_data["today_hourly_prices"].keys())
                _LOGGER.debug(f"Available today_hourly_prices keys: {today_keys}")
                
                # Try to find a key that might match the current hour
                current_hour = int(current_hour_key.split(":")[0])
                for key in today_keys:
                    if ":" in key:
                        try:
                            key_hour = int(key.split(":")[0])
                            if key_hour == current_hour:
                                current_hour_price = cached_data["today_hourly_prices"][key]
                                _LOGGER.debug(f"Found matching hour in today_hourly_prices with key {key}: {current_hour_price}")
                                # Store it with the standard format key as well
                                cached_data["today_hourly_prices"][current_hour_key] = current_hour_price
                                break
                        except (ValueError, IndexError):
                            continue
        
        # Ensure the current hour price is stored in both hourly_prices and today_hourly_prices
        # IMPORTANT: We only do this for the current hour to ensure we don't mix today's and tomorrow's data
        if current_hour_price is not None:
            # Initialize if needed
            if "hourly_prices" not in cached_data:
                cached_data["hourly_prices"] = {}
            if "today_hourly_prices" not in cached_data:
                cached_data["today_hourly_prices"] = {}
            
            # Store in both places to ensure it can be found
            # This is safe because we're only storing the current hour's price, which is definitely today's data
            cached_data["hourly_prices"][current_hour_key] = current_hour_price
            cached_data["today_hourly_prices"][current_hour_key] = current_hour_price
            _LOGGER.debug(f"Ensured current hour price {current_hour_price} is stored with key {current_hour_key} in both hourly_prices and today_hourly_prices")
        else:
            _LOGGER.warning(f"Could not find current hour price for {current_hour_key} in any format")

        self._cache[area][today_str][source] = cached_data
        _LOGGER.debug(f"Stored price data for {area}/{source} with timezones - API: {api_timezone}, HA: {ha_timezone}")

        # Store tomorrow's data if available
        # IMPORTANT: Tomorrow's data is stored separately from today's data to ensure they don't get mixed
        if "tomorrow_hourly_prices" in data and data["tomorrow_hourly_prices"]:
            # We no longer move data between today and tomorrow
            # Each dataset should be correctly categorized by the data managers
            # This simplifies the cache and maintains separation of concerns
            _LOGGER.debug(f"Storing tomorrow data with {len(data['tomorrow_hourly_prices'])} hours")
            
            tomorrow_date = now.date() + timedelta(days=1)
            tomorrow_str = tomorrow_date.strftime("%Y-%m-%d")

            # Check if tomorrow is a DST transition day
            tomorrow_dt = datetime.combine(tomorrow_date, datetime.min.time(), tzinfo=now.tzinfo)
            is_tomorrow_transition, tomorrow_transition_type = tz_service.is_dst_transition_day(tomorrow_dt)

            if tomorrow_str not in self._cache[area]:
                self._cache[area][tomorrow_str] = {}

            # Create tomorrow data with complete structure matching today's data
            tomorrow_data = {
                "current_price": None,
                "next_hour_price": None,
                "day_average_price": None,
                "peak_price": None,
                "off_peak_price": None,
                "hourly_prices": data["tomorrow_hourly_prices"],
                "raw_values": {},  # Ensure raw_values exists
                "raw_prices": data.get("raw_tomorrow", []),  # Include raw prices if available
                "data_source": data.get("data_source"),
                "currency": data.get("currency"),
                "stored_in_timezone": str(now.tzinfo),
                "cached_at": now.isoformat(),
                "api_timezone": api_timezone if api_timezone else str(now.tzinfo),
                "ha_timezone": ha_timezone,
                "last_api_fetch": last_api_fetch.isoformat() if last_api_fetch else now.isoformat()
            }

            # Add DST transition info if applicable
            if is_tomorrow_transition:
                tomorrow_data["dst_transition"] = tomorrow_transition_type

            self._cache[area][tomorrow_str][source] = tomorrow_data
            _LOGGER.debug(f"Stored tomorrow price data for {area}/{source}")

        # Clear cached info to force recalculation
        self._cache_info = None
        return True

    def has_current_hour_price(self, area: str) -> bool:
        """Check if we have the current hour's price in cache."""
        cache_info = self._get_cache_info(area)
        return cache_info.get('has_price', False)

    def get_current_hour_price(self, area: str) -> Optional[Dict[str, Any]]:
        """Get current hour price with proper timezone and DST handling."""
        cache_info = self._get_cache_info(area)

        if cache_info.get('has_price'):
            price = cache_info['price']
            hour_key = cache_info['hour_key']

            # Create area-specific timezone service to get area timezone
            tz_service = TimezoneService(self.hass, area, self.config)
            area_timezone = str(tz_service.area_timezone) if tz_service.area_timezone else None

            return {
                "price": price,
                "source": cache_info['source'],
                "hour": int(hour_key.split(":")[0]),
                "hour_str": hour_key,
                "api_timezone": cache_info['api_timezone'],
                "ha_timezone": cache_info['ha_timezone'],
                "area_timezone": area_timezone,
                "dst_info": cache_info.get('dst_info', 'unknown'),
                "tz_source": cache_info.get('tz_source', 'unknown'),
                "currency": cache_info.get('currency', 'unknown'),
                "date": cache_info['date'],
                "last_api_fetch": cache_info.get('full_data', {}).get('last_api_fetch')
            }

        return None

    def get_data(self, area: str) -> Optional[Dict[str, Any]]:
        """Get data with current hour price updated."""
        cache_info = self._get_cache_info(area)

        if cache_info.get('has_price'):
            data = cache_info.get('full_data', {})
            # Ensure raw_values exists
            if "raw_values" not in data:
                data["raw_values"] = {}
            return data

        return None

    def clear(self, area: str) -> None:
        """Clear all cached data for the specified area, including timezone and metadata."""
        # Clear all price data for the area
        if area in self._cache:
            self._cache[area] = {}
            _LOGGER.info(f"Cleared price cache for area {area}")

        # Reset the cache info to force recalculation of timezone-related data
        self._cache_info = None

        # This will ensure that all metadata including timestamps, timezone info,
        # DST information, and other cached calculations will be regenerated
        _LOGGER.info(f"Reset metadata cache for area {area}")

    def cleanup(self, max_days: int = 3) -> None:
        """Clean up old cache entries."""
        cutoff_date = datetime.now().date() - timedelta(days=max_days)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")

        removed = 0
        for area in list(self._cache.keys()):
            for date_str in list(self._cache[area].keys()):
                if date_str < cutoff_str:
                    del self._cache[area][date_str]
                    removed += 1

        if removed > 0:
            _LOGGER.debug(f"Cleaned up {removed} old cache entries")

        # Clear cached info
        self._cache_info = None
