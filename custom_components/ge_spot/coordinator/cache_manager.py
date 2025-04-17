"""Cache manager for electricity spot prices."""
import logging
from datetime import datetime
from typing import Any, Dict, Optional, List

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..price.cache import PriceCache

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
        self._price_cache = PriceCache(hass, config)

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
        self._price_cache.store(data, area, source, timestamp or dt_util.now())

    def get_data(self, area: str) -> Optional[Dict[str, Any]]:
        """Get data from cache.

        Args:
            area: Area code

        Returns:
            Dictionary with cached data, or None if not available
        """
        return self._price_cache.get_data(area)

    def get_current_hour_price(self, area: str) -> Optional[Dict[str, Any]]:
        """Get current hour price from cache.

        Args:
            area: Area code

        Returns:
            Dictionary with current hour price data, or None if not available
        """
        return self._price_cache.get_current_hour_price(area)

    def has_current_hour_price(self, area: str) -> bool:
        """Check if cache has current hour price.

        Args:
            area: Area code

        Returns:
            True if cache has current hour price
        """
        return self._price_cache.has_current_hour_price(area)

    def clear(self, area: str) -> bool:
        """Clear cache for area.

        Args:
            area: Area code

        Returns:
            True if cache was cleared
        """
        if hasattr(self._price_cache, "clear"):
            self._price_cache.clear(area)
            return True
        return False

    def cleanup(self) -> None:
        """Clean up cache."""
        self._price_cache.cleanup()
