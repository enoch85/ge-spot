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

    def get_data(self, area: str) -> Optional[Dict[str, Any]]:
        """Get data from cache.

        Args:
            area: Area code

        Returns:
            Dictionary with cached data, or None if not available
        """
        # Try to get data for this area from any source
        # First, try to find keys that match this area
        cache_info = self._price_cache.get_info()
        area_keys = [key for key in cache_info.get("entries", {}).keys() if key.startswith(f"{area}_")]
        
        # If no keys found, return None
        if not area_keys:
            return None
            
        # Get the most recently updated entry
        latest_key = max(
            area_keys,
            key=lambda k: cache_info["entries"][k].get("last_accessed", "")
        )
        
        # Return the data
        return self._price_cache.get(latest_key)

    def get_current_hour_price(self, area: str) -> Optional[Dict[str, Any]]:
        """Get current hour price from cache.

        Args:
            area: Area code

        Returns:
            Dictionary with current hour price data, or None if not available
        """
        # Get all data for this area
        data = self.get_data(area)
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
        """Clear cache for area.

        Args:
            area: Area code

        Returns:
            True if cache was cleared
        """
        # Find all keys for this area
        cache_info = self._price_cache.get_info()
        area_keys = [key for key in cache_info.get("entries", {}).keys() if key.startswith(f"{area}_")]
        
        # Delete each key
        deleted = False
        for key in area_keys:
            if self._price_cache.delete(key):
                deleted = True
                
        return deleted

    def cleanup(self) -> None:
        """Clean up cache."""
        # The AdvancedCache automatically cleans up expired entries
        # when accessing them, but we can also manually evict entries
        self._price_cache._evict_if_needed()
