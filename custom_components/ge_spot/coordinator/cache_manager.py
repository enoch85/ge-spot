"""Cache manager for electricity spot prices."""
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union
from datetime import tzinfo
import pytz

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..utils.advanced_cache import AdvancedCache
from ..const.defaults import Defaults # Import Defaults for CACHE_TTL
from ..timezone.timezone_utils import get_timezone_object # Import the missing function

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
        self._timezone_service = None  # Can be set later if needed
        # Use default TTL from Defaults if not in config
        default_ttl_minutes = config.get("cache_ttl", Defaults.CACHE_TTL)
        # Pass TTL in seconds to AdvancedCache
        config_with_ttl_seconds = {**config, "cache_ttl": default_ttl_minutes * 60}
        self._price_cache = AdvancedCache(hass, config_with_ttl_seconds)


    def store(self, area: str, source: str, data: Dict[str, Any], timestamp: Optional[datetime] = None, target_date: Optional[date] = None) -> None:
        """Store data in the cache.

        Args:
            area: The area code
            source: The source identifier
            data: The data to store
            timestamp: Optional timestamp of when the data was fetched (defaults to now)
            target_date: Optional specific date the data is for (defaults to timestamp's date)
        """
        if not timestamp:
            timestamp = dt_util.utcnow() # Use aware UTC timestamp by default if none provided
        elif timestamp.tzinfo is None:
            # Do not assume UTC for naive timestamps. This indicates an issue.
            _LOGGER.error(f"Attempted to store data for {area} from {source} with a naive timestamp: {timestamp}. Timezone information is required.")
            # Option 1: Raise an error
            # raise ValueError("Naive timestamp provided to cache store. Timezone-aware timestamp is required.")
            # Option 2: Log error and skip caching this entry (safer for now)
            return

        # Use provided target_date if available, otherwise use timestamp's date
        actual_target_date = target_date if target_date is not None else timestamp.date()

        cache_key = self._generate_cache_key(area, source, actual_target_date)

        # FIX: Ensure the data dictionary itself contains source_timezone before storing
        source_timezone = data.get("source_timezone")
        if not source_timezone:
            # This is normal during validation when storing raw data (before processing adds timezone)
            _LOGGER.debug(f"No source_timezone in data for area {area}, source {source} - may be raw validation data")
            # Optionally, add a default or raise an error if this should never happen
        else:
            # Ensure the key is present in the data dictionary being stored
            data["source_timezone"] = source_timezone

        metadata = {
            "area": area,
            "source": source,
            "target_date": actual_target_date.isoformat(), # Store target date in metadata
            "timestamp": timestamp.isoformat(), # Store as UTC ISO string
            "source_timezone": source_timezone # Store in metadata as well
        }

        # Use AdvancedCache.set() - TTL is handled by AdvancedCache based on its config
        self._price_cache.set(cache_key, data, metadata=metadata)
        _LOGGER.debug(f"Stored cache entry for key: {cache_key} with source_timezone: {source_timezone}")


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
        # Only log if source was specified but not found (actual fallback scenario)
        if source is not None:
            _LOGGER.debug(f"Specific source '{source}' not found or expired. Searching all entries for area {area} and date {target_date.isoformat()}.")
        # When source=None, searching all entries is expected behavior - no log needed
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

        # If no valid entries were found for today's date, check if we have yesterday's data with tomorrow's prices
        # This handles the midnight transition case
        now = dt_util.now()
        current_date = now.date()

        # Only attempt the migration if we're looking for today's date and it's just after midnight
        if target_date == current_date:
            # Only allow migration between 00:00 and 00:10 (10 minute window after midnight)
            if now.hour == 0 and now.minute < 10:
                yesterday = target_date - timedelta(days=1)
                _LOGGER.debug(
                    "No valid cache entries for today (%s). Checking yesterday's cache for tomorrow's data.",
                    target_date
                )

                # Look for any source from yesterday that has tomorrow data
                for key, entry_info in all_entries_info.items():
                    metadata = entry_info.get("metadata", {})
                    if metadata.get("area") == area and metadata.get("target_date") == yesterday.isoformat():
                        entry_data = self._price_cache.get(key)

                        # Check if this entry has tomorrow's prices that we can use for today
                        if entry_data and "tomorrow_interval_prices" in entry_data and entry_data["tomorrow_interval_prices"]:
                            found_source = metadata.get("source", "unknown")
                            _LOGGER.info(
                                "Found yesterday's cached data from %s with tomorrow's prices for area %s. "
                                "Using it for today's prices after midnight transition.",
                                found_source, area
                            )

                            # Create a shallow copy to prevent cache corruption
                            # (We only modify top-level keys, so shallow copy is sufficient and much faster)
                            data_copy = dict(entry_data)

                            # Move tomorrow's prices to today's prices
                            data_copy["today_interval_prices"] = data_copy["tomorrow_interval_prices"]
                            data_copy["tomorrow_interval_prices"] = {}

                            # Mark as migrated for debugging purposes
                            data_copy["migrated_from_tomorrow"] = True
                            data_copy["original_cache_date"] = yesterday.isoformat()

                            # Store this migrated data with today's date so we don't need to migrate again
                            self.store(
                                area=area,
                                source=found_source,
                                data=data_copy,
                                timestamp=now,
                                target_date=current_date
                            )

                            # Return the migrated data
                            return data_copy

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
        self.store(area=area, source=source, data=processed_data, target_date=target_date) # Corrected parameter order

    def get_cache_stats(self) -> Dict[str, Any]:
         """Get statistics about the cache."""
         return self._price_cache.get_info()
