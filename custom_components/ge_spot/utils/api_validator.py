"""Data validation utilities for API responses."""
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from homeassistant.util import dt as dt_util

from ..timezone import TimezoneService
from ..const.sources import Source
from .data_validator import DataValidator

_LOGGER = logging.getLogger(__name__)

class ApiValidator:
    """Utility class for validating API responses."""

    # Create a singleton instance of DataValidator
    _data_validator = DataValidator()

    @staticmethod
    def is_data_adequate(data: Dict[str, Any], source_name: str = "unknown",
                        require_current_hour: bool = True,
                        min_hours: int = 12) -> bool:
        """Check if the data is adequate for use.

        Args:
            data: API response data
            source_name: Name of the API source
            require_current_hour: Whether current hour price is required
            min_hours: Minimum number of hourly prices required

        Returns:
            True if data is valid and usable
        """
        # Use the new DataValidator for validation
        validation_result = ApiValidator._data_validator.validate_price_data(data, source_name)

        # Track validation result for historical analysis
        ApiValidator._data_validator.track_validation_result(source_name, validation_result)

        # If validation failed, return False
        if not validation_result["valid"]:
            return False

        # Additional checks specific to this validator

        # Check number of hours available - try new format first, fall back to legacy
        today_hour_count = len(data.get("today_hourly_prices", {}))
        tomorrow_hour_count = len(data.get("tomorrow_hourly_prices", {}))
        legacy_hour_count = len(data.get("hourly_prices", {}))
        
        # Use today hours if available, otherwise use legacy format
        hour_count = today_hour_count if today_hour_count > 0 else legacy_hour_count
        
        # Log if we have tomorrow data
        if tomorrow_hour_count > 0:
            _LOGGER.debug(f"Found {tomorrow_hour_count} hours of tomorrow's data for {source_name}")

        # Special handling for sources with different data availability patterns
        if source_name.lower() == Source.AEMO.lower():
            # For AEMO, we only require at least 1 hour of data
            # Missing hours will be filled from fallback sources if available
            if hour_count < 1:
                _LOGGER.warning(f"No hourly prices from {source_name}: {hour_count}/1")
                return False
        elif source_name.lower() == Source.ENTSOE.lower():
            # For ENTSO-E, we only require at least 6 hours of data
            # This is because ENTSO-E sometimes only provides partial data
            if hour_count < 6:
                _LOGGER.warning(f"Insufficient hourly prices from {source_name}: {hour_count}/6")
                return False
        elif hour_count < min_hours:
            _LOGGER.warning(f"Insufficient hourly prices from {source_name}: {hour_count}/{min_hours}")
            return False

        # Check for current hour price if required
        if require_current_hour:
            try:
                tz_service = TimezoneService()
                current_hour_key = tz_service.get_current_hour_key()

                # Try to find current hour in today_hourly_prices first, then fallback to hourly_prices
                if "today_hourly_prices" in data and current_hour_key in data["today_hourly_prices"]:
                    current_price = data["today_hourly_prices"][current_hour_key]
                elif "hourly_prices" in data and current_hour_key in data["hourly_prices"]:
                    current_price = data["hourly_prices"][current_hour_key]
                else:
                    _LOGGER.warning(f"Current hour {current_hour_key} missing from {source_name}")
                    return False
                if current_price is None or not isinstance(current_price, (int, float)):
                    _LOGGER.warning(f"Invalid current hour price from {source_name}: {current_price}")
                    return False
            except ValueError as e:
                _LOGGER.error(f"Timezone error checking current hour price: {e}")
                # Return False for timezone errors to avoid using invalid data
                return False
            except Exception as e:
                _LOGGER.error(f"Error checking current hour price: {e}")
                # Continue validation even if this check fails

        # Check for anomalies
        if validation_result.get("anomalies"):
            anomalies = validation_result["anomalies"]
            _LOGGER.warning(f"Price anomalies detected from {source_name}: {len(anomalies)} anomalies")
            # Log the top 3 anomalies
            for i, anomaly in enumerate(anomalies[:3]):
                _LOGGER.warning(f"Anomaly {i+1}: Hour {anomaly['hour']}, Price {anomaly['price']}, Z-score {anomaly['z_score']:.2f}")
            # Don't fail validation for anomalies, just log warnings

        return True

    @staticmethod
    def get_source_reliability(source_name: str) -> Dict[str, Any]:
        """Get reliability metrics for a source.

        Args:
            source_name: Source identifier

        Returns:
            Dict with reliability metrics
        """
        return ApiValidator._data_validator.get_source_reliability(source_name)
