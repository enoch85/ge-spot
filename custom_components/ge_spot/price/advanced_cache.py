"""Advanced caching system for price data."""
import logging
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple, Union, Set
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..const.config import Config
from ..const.defaults import Defaults

_LOGGER = logging.getLogger(__name__)

class CacheEntry:
    """Cache entry with TTL and metadata."""

    def __init__(self, data: Any, ttl: int = 3600, metadata: Optional[Dict[str, Any]] = None):
        """Initialize a cache entry.

        Args:
            data: The data to cache
            ttl: Time to live in seconds
            metadata: Optional metadata
        """
        self.data = data
        self.created_at = datetime.now(timezone.utc)
        self.ttl = ttl
        self.metadata = metadata or {}
        self.access_count = 0
        self.last_accessed = self.created_at

    @property
    def age(self) -> float:
        """Get the age of the cache entry in seconds."""
        return (datetime.now(timezone.utc) - self.created_at).total_seconds()

    @property
    def is_expired(self) -> bool:
        """Check if the cache entry is expired."""
        return self.age > self.ttl

    def access(self) -> None:
        """Mark the cache entry as accessed."""
        self.access_count += 1
        self.last_accessed = datetime.now(timezone.utc)

    @property
    def info(self) -> Dict[str, Any]:
        """Get information about the cache entry."""
        return {
            "created_at": self.created_at.isoformat(),
            "age": self.age,
            "ttl": self.ttl,
            "is_expired": self.is_expired,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat(),
            "metadata": self.metadata
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert the cache entry to a dictionary for serialization."""
        return {
            "data": self.data,
            "created_at": self.created_at.isoformat(),
            "ttl": self.ttl,
            "metadata": self.metadata,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CacheEntry':
        """Create a cache entry from a dictionary.

        Args:
            data: Dictionary with cache entry data

        Returns:
            Cache entry
        """
        entry = cls(data["data"], data["ttl"], data["metadata"])
        entry.created_at = datetime.fromisoformat(data["created_at"])
        if entry.created_at.tzinfo is None:
            entry.created_at = entry.created_at.replace(tzinfo=timezone.utc)
        entry.access_count = data["access_count"]
        entry.last_accessed = datetime.fromisoformat(data["last_accessed"])
        if entry.last_accessed.tzinfo is None:
            entry.last_accessed = entry.last_accessed.replace(tzinfo=timezone.utc)
        return entry


class AdvancedCache:
    """Advanced cache with TTL, persistence, and memory optimization."""

    def __init__(self, hass: Optional[HomeAssistant] = None, config: Optional[Dict[str, Any]] = None):
        """Initialize the cache.

        Args:
            hass: Optional Home Assistant instance
            config: Optional configuration
        """
        self.hass = hass
        self.config = config or {}

        # Configuration
        self.max_entries = self.config.get(Config.CACHE_MAX_ENTRIES, Defaults.CACHE_MAX_ENTRIES)
        self.default_ttl = self.config.get(Config.CACHE_TTL, Defaults.CACHE_TTL)
        self.persist_cache = self.config.get(Config.PERSIST_CACHE, Defaults.PERSIST_CACHE)
        self.cache_dir = self.config.get(Config.CACHE_DIR, Defaults.CACHE_DIR)

        # Cache storage
        self._cache: Dict[str, CacheEntry] = {}

        # Load cache from disk if enabled
        if self.persist_cache and hass:
            self._load_cache()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the cache.

        Args:
            key: Cache key
            default: Default value if key not found or expired

        Returns:
            Cached value or default
        """
        if key not in self._cache:
            return default

        entry = self._cache[key]

        # Check if expired
        if entry.is_expired:
            # Remove expired entry
            del self._cache[key]
            return default

        # Update access stats
        entry.access()

        return entry.data

    def set(self, key: str, value: Any, ttl: Optional[int] = None,
           metadata: Optional[Dict[str, Any]] = None) -> None:
        """Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional time to live in seconds
            metadata: Optional metadata
        """
        # Use default TTL if not specified
        ttl = ttl if ttl is not None else self.default_ttl

        # Create cache entry
        entry = CacheEntry(value, ttl, metadata)

        # Add to cache
        self._cache[key] = entry

        # Check if we need to evict entries
        self._evict_if_needed()

        # Persist cache if enabled
        if self.persist_cache and self.hass:
            self._save_cache()

    def delete(self, key: str) -> bool:
        """Delete a value from the cache.

        Args:
            key: Cache key

        Returns:
            True if key was found and deleted, False otherwise
        """
        if key in self._cache:
            del self._cache[key]

            # Persist cache if enabled
            if self.persist_cache and self.hass:
                self._save_cache()

            return True

        return False

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()

        # Persist cache if enabled
        if self.persist_cache and self.hass:
            self._save_cache()

    def get_info(self) -> Dict[str, Any]:
        """Get information about the cache.

        Returns:
            Dictionary with cache information
        """
        # Count expired entries
        expired_count = sum(1 for entry in self._cache.values() if entry.is_expired)

        return {
            "total_entries": len(self._cache),
            "expired_entries": expired_count,
            "max_entries": self.max_entries,
            "default_ttl": self.default_ttl,
            "persist_cache": self.persist_cache,
            "cache_dir": self.cache_dir,
            "entries": {key: entry.info for key, entry in self._cache.items()}
        }

    def _evict_if_needed(self) -> None:
        """Evict entries if the cache is full."""
        if len(self._cache) <= self.max_entries:
            return

        # First, remove expired entries
        expired_keys = [key for key, entry in self._cache.items() if entry.is_expired]
        for key in expired_keys:
            del self._cache[key]

        # If still too many entries, remove least recently used
        if len(self._cache) > self.max_entries:
            # Sort by last accessed time
            sorted_keys = sorted(
                self._cache.keys(),
                key=lambda k: self._cache[k].last_accessed
            )

            # Remove oldest entries
            to_remove = len(self._cache) - self.max_entries
            for key in sorted_keys[:to_remove]:
                del self._cache[key]

    def _get_cache_file_path(self) -> str:
        """Get the path to the cache file."""
        if not self.hass:
            return ""

        # Get Home Assistant config directory
        config_dir = self.hass.config.path()

        # Create cache directory if it doesn't exist
        cache_dir = os.path.join(config_dir, self.cache_dir)
        os.makedirs(cache_dir, exist_ok=True)

        # Cache file path
        return os.path.join(cache_dir, "price_cache.json")

    def _save_cache(self) -> None:
        """Save the cache to disk."""
        if not self.hass:
            return

        try:
            # Get cache file path
            cache_file = self._get_cache_file_path()

            # Convert cache to serializable format
            cache_data = {
                key: entry.to_dict()
                for key, entry in self._cache.items()
                if not entry.is_expired  # Only save non-expired entries
            }

            # Save to file
            with open(cache_file, "w") as f:
                json.dump(cache_data, f)

            _LOGGER.debug(f"Cache saved to {cache_file}")

        except Exception as e:
            _LOGGER.error(f"Failed to save cache: {e}")

    def _load_cache(self) -> None:
        """Load the cache from disk."""
        if not self.hass:
            return

        try:
            # Get cache file path
            cache_file = self._get_cache_file_path()

            # Check if file exists
            if not os.path.exists(cache_file):
                return

            # Load from file
            with open(cache_file, "r") as f:
                cache_data = json.load(f)

            # Convert to cache entries
            for key, entry_data in cache_data.items():
                try:
                    entry = CacheEntry.from_dict(entry_data)

                    # Only add non-expired entries
                    if not entry.is_expired:
                        self._cache[key] = entry
                except Exception as e:
                    _LOGGER.warning(f"Failed to load cache entry {key}: {e}")

            _LOGGER.debug(f"Cache loaded from {cache_file}")

        except Exception as e:
            _LOGGER.error(f"Failed to load cache: {e}")
