"""Cache manager for electricity spot prices."""
import json
import logging
import os
from datetime import datetime, timedelta, timezone # Ensure timezone is imported
from typing import Any, Dict, Optional
import pytz

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

        # Ensure timestamp is aware and UTC before storing as ISO string
        store_time = timestamp or dt_util.now()
        if store_time.tzinfo is None:
             # Assume naive timestamps are UTC, log warning
             _LOGGER.warning("Naive timestamp provided for caching, assuming UTC.")
             store_time = store_time.replace(tzinfo=pytz.utc)
        else:
             # Convert aware timestamp to UTC
             store_time = store_time.astimezone(pytz.utc)

        # Add metadata
        metadata = {
            "area": area,
            "source": source,
            "timestamp": store_time.isoformat() # Store as UTC ISO string
        }

        # Store in cache
        self._price_cache.set(key, data, metadata=metadata)

    def get_data(self, area: str, source: Optional[str] = None, max_age_minutes: int = 60) -> Optional[Dict[str, Any]]:
        """Retrieve data from cache if valid and not expired.

        Args:
            area: Area code
            source: Optional source identifier to filter the cache
            max_age_minutes: Optional maximum age of the cache entry in minutes.

        Returns:
            Dictionary with cached data, or None if not available or too old.
        """
        cache_data = self._load_cache()
        if not cache_data:
            _LOGGER.debug("Cache file is empty or could not be loaded.")
            return None

        # If source is specified, try that first
        if source:
            cache_key = self._generate_cache_key(area, source)
            entry = cache_data.get(cache_key)
            if entry:
                _LOGGER.debug(f"Checking specific cache key: {cache_key}")
                validated_entry = self._validate_cache_entry(entry, cache_key, max_age_minutes)
                if validated_entry:
                    return validated_entry.get("data")

        # If specific source not found or not specified, iterate through all entries for the area
        _LOGGER.debug(f"No specific source or entry invalid/expired. Searching all entries for area {area}")
        valid_entries = []
        for key, entry in cache_data.items():
            # Basic check if the key belongs to the requested area
            if key.startswith(f"{area}_"):
                 validated_entry = self._validate_cache_entry(entry, key, max_age_minutes)
                 if validated_entry:
                     valid_entries.append(validated_entry)

        if not valid_entries:
            _LOGGER.debug(f"No valid (non-expired, within max_age) cache entries found for area {area}")
            return None

        # Sort valid entries by 'created_at' timestamp, newest first
        valid_entries.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        _LOGGER.debug(f"Found {len(valid_entries)} valid cache entries for area {area}. Returning newest.")
        # Return the data part of the newest valid entry
        return valid_entries[0].get("data")


    def _validate_cache_entry(self, entry: Dict[str, Any], cache_key: str, max_age_minutes: int) -> Optional[Dict[str, Any]]:
        """Validate a single cache entry for timestamp and expiry."""
        created_at_str = entry.get("created_at")
        if not created_at_str:
            _LOGGER.warning(f"Cache entry {cache_key} missing 'created_at' timestamp. Skipping.")
            return None

        try:
            # Parse the stored timestamp string
            created_at = dt_util.parse_datetime(created_at_str)
            if created_at is None: # Handle parsing failure
                _LOGGER.error(f"Failed to parse 'created_at' timestamp: {created_at_str} for key {cache_key}")
                return None

            # Ensure the parsed timestamp is timezone-aware (it should be UTC)
            if created_at.tzinfo is None:
                _LOGGER.warning(f"Cache timestamp for {cache_key} is naive, assuming UTC: {created_at_str}")
                created_at = created_at.replace(tzinfo=timezone.utc) # Assume UTC

        except (TypeError, ValueError) as e:
            _LOGGER.error(f"Invalid 'created_at' format in cache for key {cache_key}: {created_at_str}. Error: {e}")
            return None # Skip invalid entry

        # Get current time in UTC for comparison
        now_utc = datetime.now(timezone.utc)

        # Check for future timestamp (comparing UTC against UTC)
        # Allow a small grace period (e.g., 5 seconds) for minor clock skew
        if created_at > (now_utc + timedelta(seconds=5)):
            _LOGGER.warning(f"Cache entry {cache_key} has a future 'created_at' timestamp ({created_at}) compared to now_utc ({now_utc}). Skipping.")
            return None # Skip future entry

        # Check max_age
        if (now_utc - created_at) > timedelta(minutes=max_age_minutes):
            _LOGGER.debug(f"Cache entry {cache_key} is expired based on its TTL ({max_age_minutes} min). Age: {now_utc - created_at}")
            return None # Skip expired entry

        _LOGGER.debug(f"Cache entry {cache_key} is valid and within TTL.")
        # Return the original entry dict if valid
        return entry

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

    def update_cache(self, processed_data: Dict[str, Any]):
        """Update the cache file with new processed data."""
        if not processed_data or not isinstance(processed_data, dict):
            _LOGGER.warning("Attempted to update cache with invalid data.")
            return

        area = processed_data.get("area")
        source = processed_data.get("source") # Use 'source' which is set by DataProcessor

        if not area or not source:
            _LOGGER.warning("Cannot update cache: Area or Source missing in processed data.")
            return

        cache_data = self._load_cache()

        # Use UTC timestamp consistently
        timestamp_utc = datetime.now(timezone.utc).isoformat() # Generate UTC timestamp string
        cache_key = self._generate_cache_key(area, source)
        cache_entry = {
            "created_at": timestamp_utc, # Store UTC ISO string
            "data": processed_data
        }

        cache_data[cache_key] = cache_entry
        _LOGGER.debug(f"Updating cache for key: {cache_key}")

        try:
            with open(self.cache_file_path, 'w') as f:
                json.dump(cache_data, f, indent=4)
            _LOGGER.debug(f"Saved cache entry {cache_key} with timestamp {timestamp_utc}")
        except IOError as e:
            _LOGGER.error(f"Error writing cache file {self.cache_file_path}: {e}")
        except Exception as e:
            _LOGGER.error(f"Unexpected error writing cache file: {e}", exc_info=True)
