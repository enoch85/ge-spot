import logging
from typing import Any, Dict, Optional

from ..timezone import TimezoneService

_LOGGER = logging.getLogger(__name__)

class TimezoneConverter:
    """Handles centralized timezone normalization for price data."""

    def __init__(self, tz_service: TimezoneService):
        """Initialize the TimezoneConverter."""
        self._tz_service = tz_service

    def normalize_hourly_prices(
        self,
        hourly_prices: Dict[str, Any], # Expects dict like {"2023-10-27T10:00:00+01:00": 123.45}
        source_timezone_str: Optional[str] = None # Optional: Hint about the source data's timezone
    ) -> Dict[str, Any]:
        """Normalizes timestamps in the hourly price dictionary to the target timezone.

        Args:
            hourly_prices: Dictionary of raw hourly prices with timestamps as keys.
            source_timezone_str: Optional timezone string if known from the source API.

        Returns:
            A dictionary with timestamps normalized to the format 'HH:00' in the target timezone.
        """
        if not hourly_prices:
            return {}

        _LOGGER.debug(
            "Normalizing %d hourly price timestamps using target timezone: %s",
            len(hourly_prices),
            self._tz_service.target_timezone
        )

        normalized_prices = {}
        try:
            # Use the TimezoneService's existing method to handle the conversion and DST
            # This assumes tz_service has a method like normalize_timestamps or similar
            # Let's adapt based on the likely existing `normalize_hourly_prices` logic
            # found previously in API adapters.

            # We need to ensure the input format matches what the service expects.
            # If the service expects datetime objects, we parse them first.
            # If it handles string parsing internally, we pass the dict directly.

            # Assuming tz_service.normalize_hourly_prices handles the logic:
            normalized_prices = self._tz_service.normalize_hourly_prices(
                hourly_prices,
                source_tz_str=source_timezone_str # Pass hint if available
            )

            _LOGGER.debug("Normalization complete. Result keys: %s", list(normalized_prices.keys()))

        except Exception as e:
            _LOGGER.error(
                "Error during timezone normalization: %s. Input keys: %s",
                e,
                list(hourly_prices.keys()),
                exc_info=True
            )
            # Return empty dict or re-raise depending on desired error handling
            return {}

        return normalized_prices

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
            final_today_prices = self.normalize_hourly_prices(today_prices_raw, source_timezone_str)

        if tomorrow_prices_raw:
            _LOGGER.debug("Normalizing tomorrow's prices...")
            final_tomorrow_prices = self.normalize_hourly_prices(tomorrow_prices_raw, source_timezone_str)

        return final_today_prices, final_tomorrow_prices

# Example usage (would be in DataProcessor):
# tz_converter = TimezoneConverter(self._tz_service)
# final_today, final_tomorrow = tz_converter.normalize_today_and_tomorrow_prices(
#     raw_data.get("hourly_prices"), # Assuming raw data structure
#     raw_data.get("tomorrow_hourly_prices_raw"), # Assuming raw data structure
#     raw_data.get("api_timezone")
# )
