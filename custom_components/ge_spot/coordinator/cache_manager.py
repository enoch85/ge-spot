"""Cache manager for electricity spot prices."""
import json
import logging
import os
# Ensure date is imported from datetime
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional
import pytz

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..price.advanced_cache import AdvancedCache
from ..const.defaults import Defaults # Import Defaults for CACHE_TTL

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
        # Use default TTL from Defaults if not in config
        default_ttl_minutes = config.get("cache_ttl", Defaults.CACHE_TTL)
        # Pass TTL in seconds to AdvancedCache
        config_with_ttl_seconds = {**config, "cache_ttl": default_ttl_minutes * 60}
        self._price_cache = AdvancedCache(hass, config_with_ttl_seconds)


    def store(
        self,
        data: Dict[str, Any],
        area: str,
        source: str,
        target_date: date, # Added target_date
        timestamp: Optional[datetime] = None
    ) -> None:
        """Store data in cache for a specific date.

        Args:
            data: Data to store
            area: Area code
            source: Source identifier
            target_date: The primary date this data pertains to (e.g., today's date)
            timestamp: Optional timestamp (will be converted to UTC)
        """
        key = self._generate_cache_key(area, source, target_date) # Pass date to key gen

        # Ensure timestamp is aware and UTC before storing as ISO string
        # Use datetime.now(timezone.utc) for robust UTC timestamping
        store_time = timestamp or datetime.now(timezone.utc)
        if store_time.tzinfo is None:
             _LOGGER.warning("Naive timestamp provided for caching, assuming UTC.")
             store_time = store_time.replace(tzinfo=timezone.utc)
        else:
             store_time = store_time.astimezone(timezone.utc)

        # Extract api_timezone for metadata
        api_timezone = data.get("api_timezone") or data.get("timezone")
        if not api_timezone:
            _LOGGER.warning(f"No api_timezone or timezone found in data for area {area}, source {source}, target_date {target_date}. Cache entry may not be processable from cache.")
        metadata = {
            "area": area,
            "source": source,
            "target_date": target_date.isoformat(), # Store target date in metadata
            "timestamp": store_time.isoformat(), # Store as UTC ISO string
            "api_timezone": api_timezone
        }

        # Use AdvancedCache.set() - TTL is handled by AdvancedCache based on its config
        self._price_cache.set(key, data, metadata=metadata)
        _LOGGER.debug(f"Stored cache entry for key: {key} with api_timezone: {api_timezone}")


    def _generate_cache_key(self, area: str, source: str, target_date: date) -> str:
        """Generate a consistent cache key including the target date."""
        date_str = target_date.isoformat() # Format date as YYYY-MM-DD
        return f"{area}_{date_str}_{source}"

    def get_data(self, area: str, target_date: date, source: Optional[str] = None, max_age_minutes: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Retrieve data from cache for a specific date if valid.

        Args:
            area: Area code
            target_date: The date for which data is requested.
            source: Optional source identifier to filter the cache.
            max_age_minutes: Optional maximum age of the cache entry in minutes.
                             If None, only the entry's TTL is checked.

        Returns:
            Dictionary with cached data, or None if not available or too old.
        """
        # If source is specified, try that first using AdvancedCache.get()
        if source:
            cache_key = self._generate_cache_key(area, source, target_date) # Use date in key
            # AdvancedCache.get handles TTL expiry check internally
            entry_data = self._price_cache.get(cache_key)
            if entry_data:
                # If max_age_minutes is specified, perform an additional check
                if max_age_minutes is not None:
                    entry_info = self._price_cache.get_info().get("entries", {}).get(cache_key)
                    # Ensure the entry found actually matches the requested target_date from metadata
                    # (Although key matching should guarantee this, it's a safety check)
                    if entry_info and entry_info.get("metadata", {}).get("target_date") == target_date.isoformat() and self._is_entry_within_max_age(entry_info, max_age_minutes):
                         _LOGGER.debug(f"Cache hit for specific key {cache_key} within max_age.")
                         return entry_data
                    else:
                         _LOGGER.debug(f"Cache entry {cache_key} found but is older than max_age_minutes ({max_age_minutes}) or metadata mismatch.")
                         return None # Treat as expired for this request
                else:
                    # No max_age check needed, TTL check passed in .get()
                    _LOGGER.debug(f"Cache hit for specific key: {cache_key} (TTL check only).")
                    return entry_data # Return the data part directly

        # If specific source not found/expired or not specified, search all entries for the area AND date
        _LOGGER.debug(f"No specific source hit for '{source}'. Searching all entries for area {area} and date {target_date.isoformat()}.")
        valid_entries_with_timestamp = []
        all_entries_info = self._price_cache.get_info().get("entries", {})
        target_date_str = target_date.isoformat()

        for key, entry_info in all_entries_info.items():
            metadata = entry_info.get("metadata", {})
            # Check if the key belongs to the requested area AND target_date
            # We check metadata explicitly here as key structure might vary slightly
            if metadata.get("area") == area and metadata.get("target_date") == target_date_str:
                 # Check if expired based on TTL (already checked by .get() later, but good for pre-filtering)
                 if not entry_info.get("is_expired"):
                     # Check against max_age_minutes if specified
                     if max_age_minutes is None or self._is_entry_within_max_age(entry_info, max_age_minutes):
                         # Retrieve the actual data using .get() which re-validates TTL
                         entry_data = self._price_cache.get(key)
                         if entry_data:
                             try:
                                 # Use created_at from entry_info for sorting
                                 created_at_str = entry_info.get("created_at")
                                 created_at = dt_util.parse_datetime(created_at_str) if created_at_str else datetime.min.replace(tzinfo=timezone.utc)
                                 if created_at.tzinfo is None: # Ensure timezone aware for sorting
                                     created_at = created_at.replace(tzinfo=timezone.utc)
                                 valid_entries_with_timestamp.append((created_at, entry_data))
                             except Exception as e:
                                  _LOGGER.warning(f"Error parsing created_at for sorting cache key {key}: {e}")
                     else:
                          _LOGGER.debug(f"Cache entry {key} is older than max_age_minutes ({max_age_minutes}).")


        if not valid_entries_with_timestamp:
            _LOGGER.debug(f"No valid (non-expired, within max_age) cache entries found for area {area} and date {target_date_str}")
            return None

        # Sort valid entries by timestamp (datetime object), newest first
        valid_entries_with_timestamp.sort(key=lambda x: x[0], reverse=True)
        _LOGGER.debug(f"Found {len(valid_entries_with_timestamp)} valid cache entries for area {area} date {target_date_str}. Returning newest.")
        # Return the data part of the newest valid entry
        return valid_entries_with_timestamp[0][1]

    def _is_entry_within_max_age(self, entry_info: Dict[str, Any], max_age_minutes: int) -> bool:
        """Check if a cache entry info dict is within the specified max age."""
        created_at_str = entry_info.get("created_at")
        if not created_at_str:
            return False # Cannot determine age

        try:
            created_at = dt_util.parse_datetime(created_at_str)
            if not created_at: return False

            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc) # Assume UTC

            now_utc = datetime.now(timezone.utc)
            max_age_delta = timedelta(minutes=max_age_minutes)

            # Allow a 5-minute grace period for future timestamps
            future_threshold = now_utc + timedelta(seconds=300)
            if created_at > future_threshold:
                 _LOGGER.warning(f"Cache entry has significant future timestamp: {created_at_str}. Invalidating.")
                 return False
            elif created_at > now_utc:
                 _LOGGER.debug(f"Cache entry timestamp {created_at_str} is slightly in the future. Capping at current time for age check.")
                 created_at = now_utc # Cap at current time for age calculation

            return (now_utc - created_at) <= max_age_delta
        except Exception as e:
            _LOGGER.warning(f"Error checking max_age for timestamp {created_at_str}: {e}")
            return False


    def get_current_hour_price(self, area: str, target_timezone=None) -> Optional[Dict[str, Any]]:
        """Get current hour price from cache for today's date in the target timezone."""
        # Use the correct date in the target timezone for cache lookup
        tz = target_timezone
        if tz is None:
            from custom_components.ge_spot.timezone.timezone_utils import get_timezone_object
            tz = get_timezone_object("Europe/Stockholm")  # Fallback, should be passed in
        today = dt_util.now(tz).date()
        data = self.get_data(area, target_date=today, max_age_minutes=Defaults.CACHE_TTL)
        if not data:
            return None

        # Extract current hour price if available
        try:
            # Ensure we use the correct timezone for the current hour key
            # Attempt to get timezone from metadata of any cache entry for the area
            area_tz_str = None
            all_entries_info = self._price_cache.get_info().get("entries", {})
            for key, entry_info in all_entries_info.items():
                 metadata = entry_info.get("metadata", {})
                 if metadata.get("area") == area and metadata.get("target_date") == today.isoformat(): # Check for today's date
                    # Try to get timezone from metadata (assuming it might be stored there)
                    # This part is speculative, adjust if timezone is stored differently
                    if "timezone" in metadata: # Assuming timezone might be stored in data, not metadata directly
                        cached_data_for_tz = self._price_cache.get(key)
                        if cached_data_for_tz and "api_timezone" in cached_data_for_tz:
                             area_tz_str = cached_data_for_tz["api_timezone"]
                             break
                        elif cached_data_for_tz and "timezone" in cached_data_for_tz: # Fallback key
                             area_tz_str = cached_data_for_tz["timezone"]
                             break

            # If not found in cache metadata, fallback to HA default
            local_tz = pytz.timezone(area_tz_str) if area_tz_str else dt_util.get_default_home_assistant_timezone()
            current_hour_key = dt_util.now(local_tz).strftime("%H:00")
        except Exception as e:
             # Fallback to system time if timezone lookup fails
             _LOGGER.warning(f"Could not determine area timezone for current hour key, using system time. Error: {e}")
             current_hour_key = dt_util.now().strftime("%H:00")

        hourly_prices = data.get("hourly_prices", {})

        if current_hour_key in hourly_prices:
            return {
                "price": hourly_prices[current_hour_key],
                "hour": current_hour_key,
                "source": data.get("data_source", data.get("source", "unknown")) # Prefer data_source
            }

        _LOGGER.debug(f"Current hour key '{current_hour_key}' not found in cached hourly prices for {area} on {today.isoformat()}.")
        return None


    def has_current_hour_price(self, area: str) -> bool:
        """Check if cache has current hour price for today."""
        return self.get_current_hour_price(area) is not None

    def clear(self, area: str, target_date: Optional[date] = None) -> bool:
        """Clear cache for a specific area, optionally for a specific date."""
        cache_info = self._price_cache.get_info()
        keys_to_delete = []
        target_date_str = target_date.isoformat() if target_date else None

        for key, entry_info in cache_info.get("entries", {}).items():
            metadata = entry_info.get("metadata", {})
            matches_area = metadata.get("area") == area
            matches_date = target_date is None or metadata.get("target_date") == target_date_str

            if matches_area and matches_date:
                keys_to_delete.append(key)


        if not keys_to_delete:
            _LOGGER.debug(f"No cache keys found for area {area}" + (f" and date {target_date_str}" if target_date else ""))
            return False

        deleted = False
        for key in keys_to_delete:
            if self._price_cache.delete(key):
                deleted = True
                _LOGGER.debug("Deleted cache key %s", key)

        return deleted

    def clear_cache(self, area: Optional[str] = None, target_date: Optional[date] = None) -> bool:
        """Clear all cache or cache for a specific area/date."""
        if area:
            return self.clear(area, target_date) # Pass date to clear
        elif target_date:
             _LOGGER.warning("Clearing cache by date without specifying an area is not supported. Please specify an area.")
             return False # Or implement if needed, but less common use case
        else:
            # Clear all areas using AdvancedCache's clear method
            self._price_cache.clear()
            _LOGGER.info("Cleared all cache entries.")
            return True # Assume clear() succeeded if no exception

    def cleanup(self) -> None:
        """Clean up expired cache entries."""
        # Delegate to AdvancedCache's internal cleanup/eviction logic
        self._price_cache._evict_if_needed()
        _LOGGER.debug("Cache cleanup triggered.")

    def update_cache(self, processed_data: Dict[str, Any]):
        """Update the cache using the store method, extracting the target date."""
        if not processed_data or not isinstance(processed_data, dict):
            _LOGGER.warning("Attempted to update cache with invalid data.")
            return

        area = processed_data.get("area")
        # Use 'data_source' if available (set by processor), fallback to 'source'
        source = processed_data.get("data_source") or processed_data.get("source")
        # Determine the target date - needs logic based on processed_data content
        # Assuming 'last_updated' or similar field reflects the primary date
        # THIS IS A PLACEHOLDER - Needs proper logic based on how processed_data indicates its date scope
        target_date = dt_util.now().date() # Default to today, needs refinement
        last_updated_str = processed_data.get("last_updated")
        try:
             if last_updated_str:
                  # Attempt to parse the date from last_updated timestamp
                  ts = dt_util.parse_datetime(last_updated_str)
                  if ts:
                       # Use the date part of the timestamp, assuming it reflects the data's target day
                       # Consider the timezone of the timestamp if available
                       target_date = ts.date()
             else:
                  _LOGGER.warning("Could not determine target_date from processed_data, defaulting to today.")
        except Exception as e:
             _LOGGER.warning(f"Error parsing date from last_updated '{last_updated_str}', defaulting to today: {e}")


        if not area or not source:
            _LOGGER.warning("Cannot update cache: Area or Source missing in processed data.")
            return

        _LOGGER.debug(f"Updating cache for area {area}, source {source}, date {target_date.isoformat()} via store method.")
        # Delegate saving to the store method which correctly uses AdvancedCache.set
        # Pass the processed data itself as the value to store
        self.store(data=processed_data, area=area, source=source, target_date=target_date) # Pass target_date

    def get_cache_stats(self) -> Dict[str, Any]:
         """Get statistics about the cache."""
         return self._price_cache.get_info()
