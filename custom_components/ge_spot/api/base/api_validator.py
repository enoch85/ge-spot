"""Data validation utilities for API responses."""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from homeassistant.util import dt as dt_util

from ...timezone.service import TimezoneService
from ...const.sources import Source
from ...utils.data_validator import DataValidator

_LOGGER = logging.getLogger(__name__)


class ApiValidator:
    """Utility class for validating API responses."""

    # Create a singleton instance of DataValidator
    _data_validator = DataValidator()

    @staticmethod
    def is_data_adequate(
        data: Dict[str, Any],
        source_name: str = "unknown",
        require_current_hour: bool = True,
        min_intervals: int = 48,
    ) -> bool:
        """Check if the data is adequate for use.

        Args:
            data: API response data
            source_name: Name of the API source
            require_current_hour: Whether current interval price is required
            min_intervals: Minimum number of interval prices required

        Returns:
            True if data is valid and usable
        """
        # Use the new DataValidator for validation
        validation_result = ApiValidator._data_validator.validate_price_data(
            data, source_name
        )

        # Track validation result for historical analysis
        ApiValidator._data_validator.track_validation_result(
            source_name, validation_result
        )

        # If validation failed, return False
        if not validation_result["valid"]:
            return False

        # Additional checks specific to this validator

        # Check number of intervals available
        interval_count = len(data.get("today_interval_prices", {}))

        # Special handling for sources with different data availability patterns
        if source_name.lower() == Source.AEMO.lower():
            # For AEMO, we only require at least 16 intervals of data (4 hours with 15-min intervals)
            # Missing intervals will be filled from fallback sources if available
            if interval_count < 16:
                _LOGGER.warning(
                    f"No interval prices from {source_name}: {interval_count}/16"
                )
                return False
        elif source_name.lower() == Source.ENTSOE.lower():
            # For ENTSO-E, we only require at least 24 intervals of data (6 hours with 15-min intervals)
            # This is because ENTSO-E sometimes only provides partial data
            if interval_count < 24:
                _LOGGER.warning(
                    f"Insufficient interval prices from {source_name}: {interval_count}/24"
                )
                return False
        elif interval_count < min_intervals:
            _LOGGER.warning(
                f"Insufficient interval prices from {source_name}: {interval_count}/{min_intervals}"
            )
            return False

        # Check for current interval price if required
        if require_current_hour:
            try:
                tz_service = TimezoneService()
                current_interval_key = tz_service.get_current_interval_key()

                if current_interval_key not in data.get("today_interval_prices", {}):
                    _LOGGER.warning(
                        f"Current interval {current_interval_key} missing from {source_name}"
                    )
                    return False

                current_price = data["today_interval_prices"][current_interval_key]
                if current_price is None or not isinstance(current_price, (int, float)):
                    _LOGGER.warning(
                        f"Invalid current interval price from {source_name}: {current_price}"
                    )
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
            _LOGGER.warning(
                f"Price anomalies detected from {source_name}: {len(anomalies)} anomalies"
            )
            # Log the top 3 anomalies
            for i, anomaly in enumerate(anomalies[:3]):
                _LOGGER.warning(
                    f"Anomaly {i+1}: Hour {anomaly['hour']}, Price {anomaly['price']}, Z-score {anomaly['z_score']:.2f}"
                )
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
