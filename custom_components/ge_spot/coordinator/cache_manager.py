"""Cache manager for electricity spot prices."""
import logging
from datetime import datetime
from typing import Any, Dict, Optional, List

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..price.advanced_cache import AdvancedCache

_LOGGER = logging.getLogger(__name__)

class CacheManager:
    """Manager for cache operations."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: Dict[str, Any]
    ):
        """Initialize the cache manager.

        Args:
            hass: Home Assistant instance
            config: Configuration dictionary
        """
        self.hass = hass
        self.config = config
        self._price_cache = AdvancedCache(hass, config)

    def store(
        self,
        data: Dict[str, Any],
        area: str,
        source: str,
        timestamp: Optional[datetime] = None
    ) -> None:
        """Store data in cache.

        Args:
            data: Data to store
            area: Area code
            source: Source identifier
            timestamp: Optional timestamp
        """
        # Create a cache key based on area and source
        key = f"{area}_{source}"
        
        # Add metadata
        metadata = {
            "area": area,
            "source": source,
            "timestamp": (timestamp or dt_util.now()).isoformat()
        }
        
        # Store in cache
        self._price_cache.set(key, data, metadata=metadata)

    def get_data(self, area: str, max_age_minutes: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get data from cache, optionally filtering by maximum age.

        Args:
            area: Area code
            max_age_minutes: Optional maximum age of the cache entry in minutes.

        Returns:
            Dictionary with cached data, or None if not available or too old.
        """
        cache_info = self._price_cache.get_info()
        area_keys = [key for key in cache_info.get("entries", {}).keys() if key.startswith(f"{area}_")]

        if not area_keys:
            _LOGGER.debug("No cache keys found for area %s", area)
            return None

        valid_keys = []
        now = dt_util.now() # Use timezone-aware now

        for key in area_keys:
            entry_info = cache_info["entries"].get(key)
            if not entry_info:
                continue # Should not happen if key is from get_info, but safety first

            # Check internal expiry based on TTL
            if entry_info.get("is_expired", True):
                 _LOGGER.debug("Cache entry %s is expired based on its TTL.", key)
                 continue # Skip expired entries

            # Check against max_age_minutes if provided
            if max_age_minutes is not None:
                try:
                    created_at = dt_util.parse_datetime(entry_info["created_at"])
                    if created_at is None: # Handle potential parsing failure
                         _LOGGER.warning("Could not parse created_at for cache key %s", key)
                         continue
                    age_seconds = (now - created_at).total_seconds()
                    if age_seconds > max_age_minutes * 60:
                        _LOGGER.debug("Cache entry %s is older (%s s) than max_age_minutes (%s min).", key, age_seconds, max_age_minutes)
                        continue # Skip entries older than max_age_minutes
                except Exception as e:
                    _LOGGER.warning("Error checking age for cache key %s: %s", key, e)
                    continue # Skip if age check fails

            # If we reach here, the entry is valid
            valid_keys.append(key)

        if not valid_keys:
            _LOGGER.debug("No valid (non-expired, within max_age) cache entries found for area %s", area)
            return None

        # Get the most recently created entry among the valid ones
        try:
            latest_key = max(
                valid_keys,
                key=lambda k: dt_util.parse_datetime(cache_info["entries"][k].get("created_at", "")) or dt_util.utc_from_timestamp(0) # Use created_at, handle missing/parse errors
            )
            _LOGGER.debug("Selected latest valid cache key %s for area %s", latest_key, area)
        except Exception as e:
             _LOGGER.error("Error finding latest valid cache key for area %s: %s", area, e)
             return None # Return None if finding the max fails

        # Return the data using the AdvancedCache.get method, which handles final access update
        # and potentially another expiry check if time passed significantly
        return self._price_cache.get(latest_key)

    def get_current_hour_price(self, area: str) -> Optional[Dict[str, Any]]:
        """Get current hour price from cache."""
        # Get data without max_age limit for current hour check
        data = self.get_data(area) # No max_age needed here
        if not data:
            return None
            
        # Extract current hour price if available
        current_hour = dt_util.now().strftime("%H:00")
        hourly_prices = data.get("hourly_prices", {})
        
        if current_hour in hourly_prices:
            return {
                "price": hourly_prices[current_hour],
                "hour": current_hour,
                "source": data.get("source", "unknown")
            }
            
        return None

    def has_current_hour_price(self, area: str) -> bool:
        """Check if cache has current hour price.

        Args:
            area: Area code

        Returns:
            True if cache has current hour price
        """
        return self.get_current_hour_price(area) is not None

    def clear(self, area: str) -> bool:
        """Clear cache for a specific area.
        
        Args:
            area: Area code to clear cache for
            
        Returns:
            True if cache was cleared
        """
        cache_info = self._price_cache.get_info()
        area_keys = [key for key in cache_info.get("entries", {}).keys() if key.startswith(f"{area}_")]
        
        if not area_keys:
            _LOGGER.debug("No cache keys found for area %s", area)
            return False
        
        deleted = False
        for key in area_keys:
            if self._price_cache.delete(key):
                deleted = True
                _LOGGER.debug("Deleted cache key %s", key)
        
        return deleted

    def clear_cache(self, area: Optional[str] = None) -> bool:
        """Clear all cache or cache for a specific area.
        
        Args:
            area: Optional area code. If None, clear all cache.
            
        Returns:
            True if cache was cleared.
        """
        if area:
            return self.clear(area)
        else:
            # Clear all areas
            cache_info = self._price_cache.get_info()
            all_keys = list(cache_info.get("entries", {}).keys())
            
            deleted = False
            for key in all_keys:
                if self._price_cache.delete(key):
                    deleted = True
                    
            return deleted

    def cleanup(self) -> None:
        """Clean up cache."""
        # The AdvancedCache automatically cleans up expired entries
        # when accessing them, but we can also manually evict entries
        self._price_cache._evict_if_needed()

    def update_cache(self, data: Dict[str, Any]) -> None:
        """Update the cache with processed data.
        
        Args:
            data: Processed data to cache
        """
        if not data or not isinstance(data, dict):
            _LOGGER.warning("Cannot cache invalid data")
            return
            
        area = data.get("area")
        source = data.get("source", data.get("data_source", "unknown"))
        
        if not area:
            _LOGGER.warning("Cannot cache data without area")
            return
            
        # Store in cache
        self.store(data, area, source)
