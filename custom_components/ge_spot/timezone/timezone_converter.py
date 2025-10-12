import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone, date, timedelta

# Importing timezone_utils directly instead of from ..timezone to avoid circular import
from .timezone_utils import get_timezone_object

_LOGGER = logging.getLogger(__name__)

class TimezoneConverter:
    """Handles centralized timezone normalization for price data."""

    def __init__(self, tz_service):
        """Initialize the TimezoneConverter.

        Args:
            tz_service: Timezone service instance that provides timezone conversion functionality
        """
        self._tz_service = tz_service

    def parse_datetime_with_tz(self, iso_datetime_str: str, source_timezone_str: Optional[str] = None) -> Optional[datetime]:
        """Parse an ISO datetime string into an aware datetime object.

        Args:
            iso_datetime_str: ISO formatted datetime string
            source_timezone_str: Optional timezone hint if the string doesn't contain TZ info

        Returns:
            Aware datetime object in the source timezone, or None if parsing fails
        """
        try:
            # Try to parse with fromisoformat, handling Z for UTC
            iso_str = iso_datetime_str.replace('Z', '+00:00')
            dt = datetime.fromisoformat(iso_str)

            # If dt is naive but we have a source_timezone_str, make it aware
            if dt.tzinfo is None and source_timezone_str:
                source_tz = get_timezone_object(source_timezone_str)
                if source_tz:
                    # Use replace() for timezone-aware datetime creation
                    dt = dt.replace(tzinfo=source_tz)
                else:
                    _LOGGER.error(f"Invalid source timezone: {source_timezone_str}")
                    return None

            # Ensure dt is timezone aware
            if dt.tzinfo is None:
                _LOGGER.error(f"Could not determine timezone for: {iso_datetime_str}")
                return None

            return dt
        except (ValueError, TypeError) as e:
            _LOGGER.error(f"Error parsing datetime '{iso_datetime_str}': {e}")
            return None

    def normalize_interval_prices(
        self,
        interval_prices: Dict[str, Any],
        source_timezone_str: Optional[str] = None,
        preserve_date: bool = True
    ) -> Dict[str, Any]:
        """Normalizes timestamps in the interval price dictionary to the target timezone.

        Args:
            interval_prices: Dictionary of raw interval prices with timestamps as keys.
            source_timezone_str: Optional timezone string if known from the source API.
            preserve_date: Whether to include date in the key format (for differentiating today/tomorrow)

        Returns:
            A dictionary with timestamps normalized to the format 'HH:MM' or 'YYYY-MM-DD HH:MM' in the target timezone.
        """
        if not interval_prices:
            return {}

        _LOGGER.debug(
            "Normalizing %d interval price timestamps using target timezone: %s (preserve_date=%s)",
            len(interval_prices),
            self._tz_service.target_timezone,
            preserve_date
        )

        normalized_prices = {}
        try:
            # Process each ISO timestamp to target timezone interval format
            for iso_key, price_data in interval_prices.items():
                # Parse the ISO timestamp to datetime with timezone
                dt = self.parse_datetime_with_tz(iso_key, source_timezone_str)
                if dt is None:
                    _LOGGER.warning(f"Skipping entry with invalid timestamp: {iso_key}")
                    continue

                # Convert to target timezone
                target_dt = dt.astimezone(self._tz_service.target_timezone)

                # Format as 'HH:MM' or 'YYYY-MM-DD HH:MM' in target timezone
                if preserve_date:
                    target_key = f"{target_dt.date().isoformat()} {target_dt.hour:02d}:{target_dt.minute:02d}"
                    # Store date in price data for sorting/filtering if it's a dict
                    if isinstance(price_data, dict):
                        price_data["date"] = target_dt.date().isoformat()
                else:
                    target_key = f"{target_dt.hour:02d}:{target_dt.minute:02d}"

                # Handle potential DST fallback duplicates
                # Only log as DST fallback if the keys don't have dates (when preserve_date=False)
                # With preserve_date=True, duplicates across days are normal (e.g., "2025-10-02 00:00" and "2025-10-03 00:00")
                if target_key in normalized_prices:
                    if preserve_date:
                        # With dates, this is just a different day - overwrite is expected
                        _LOGGER.debug(f"Duplicate interval key found: {target_key} - overwriting with newer value (likely next day)")
                    else:
                        # Without dates, this could be genuine DST fallback (same hour repeating in one day)
                        _LOGGER.debug(f"Duplicate interval found: {target_key} - handling DST fallback")
                    # In case of DST fallback, use the second occurrence
                    # This aligns with how most energy markets handle the extra interval

                # Store the price
                normalized_prices[target_key] = price_data if isinstance(price_data, dict) else price_data

            _LOGGER.debug("Normalization complete. Result keys: %s", list(normalized_prices.keys())[:5] + ["..."] if len(normalized_prices) > 5 else list(normalized_prices.keys()))
            _LOGGER.debug(f"Normalization summary: Input had {len(interval_prices)} prices, output has {len(normalized_prices)} normalized prices")

        except Exception as e:
            _LOGGER.error(
                "Error during timezone normalization: %s. Input keys: %s",
                e,
                list(interval_prices.keys()),
                exc_info=True
            )
            return {}

        return normalized_prices

    def split_into_today_tomorrow(
        self,
        normalized_prices: Dict[str, Any]
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Split normalized interval prices into today and tomorrow buckets.

        Args:
            normalized_prices: Dictionary of prices already normalized to target timezone

        Returns:
            Tuple of (today_prices, tomorrow_prices) dictionaries
        """
        today_prices = {}
        tomorrow_prices = {}

        # Get today's and tomorrow's date in the target timezone
        now = datetime.now(self._tz_service.target_timezone)
        today_date = now.date()
        # Use timedelta to properly handle month/year boundaries
        tomorrow_date = (now + timedelta(days=1)).date()

        today_date_str = today_date.isoformat()
        tomorrow_date_str = tomorrow_date.isoformat()

        # Check if keys have date information (like '2025-04-29 10:00')
        has_date_in_keys = any(" " in key for key in normalized_prices.keys())

        _LOGGER.debug(f"split_into_today_tomorrow: Received {len(normalized_prices)} normalized prices. has_date_in_keys={has_date_in_keys}. Sample keys: {list(normalized_prices.keys())[:5]}")

        if has_date_in_keys:
            # Keys already have date info, we can directly separate today and tomorrow
            for key, price in normalized_prices.items():
                date_part = key.split(" ")[0]
                interval_part = key.split(" ")[1]

                if date_part == today_date_str:
                    today_prices[interval_part] = price
                elif date_part == tomorrow_date_str:
                    tomorrow_prices[interval_part] = price
        else:
            # Use the original logic with interval ranges
            today_intervals = self._tz_service.get_today_range()
            tomorrow_intervals = self._tz_service.get_tomorrow_range()

            # Since we can't differentiate by date, use the API price date if available
            for interval_key, price in normalized_prices.items():
                if isinstance(price, dict) and "date" in price:
                    price_date = price["date"]
                    price_without_date = price.copy()
                    price_without_date.pop("date", None)

                    if price_date == today_date_str:
                        today_prices[interval_key] = price_without_date
                    elif price_date == tomorrow_date_str:
                        tomorrow_prices[interval_key] = price_without_date
                elif interval_key in today_intervals:
                    today_prices[interval_key] = price
                elif interval_key in tomorrow_intervals:
                    tomorrow_prices[interval_key] = price

        _LOGGER.debug(f"Split prices into today ({len(today_prices)} intervals) and tomorrow ({len(tomorrow_prices)} intervals)")
        return today_prices, tomorrow_prices

    def normalize_today_and_tomorrow_prices(
        self,
        today_prices_raw: Optional[Dict[str, Any]],
        tomorrow_prices_raw: Optional[Dict[str, Any]],
        source_timezone_str: Optional[str] = None
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Normalizes timestamps for both today's and tomorrow's raw prices."""

        final_today_prices = {}
        final_tomorrow_prices = {}

        if today_prices_raw:
            _LOGGER.debug("Normalizing today's prices...")
            final_today_prices = self.normalize_interval_prices(today_prices_raw, source_timezone_str)

        if tomorrow_prices_raw:
            _LOGGER.debug("Normalizing tomorrow's prices...")
            final_tomorrow_prices = self.normalize_interval_prices(tomorrow_prices_raw, source_timezone_str)

        return final_today_prices, final_tomorrow_prices

# Example usage (would be in DataProcessor):
# tz_converter = TimezoneConverter(self._tz_service)
# final_today, final_tomorrow = tz_converter.normalize_today_and_tomorrow_prices(
#     raw_data.get("today_interval_prices"), # Assuming raw data structure
#     raw_data.get("tomorrow_interval_prices_raw"), # Assuming raw data structure
#     raw_data.get("api_timezone")
# )
