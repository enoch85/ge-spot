"""Data validation utilities for API responses."""
import logging
from typing import Dict, Any, Optional

_LOGGER = logging.getLogger(__name__)

class ApiValidator:
    """Utility class for validating API responses."""

    @staticmethod
    def is_data_adequate(data: Dict[str, Any]) -> bool:
        """Check if the data is adequate for use."""
        if not data:
            return False

        # Must have current price
        if "current_price" not in data or data["current_price"] is None:
            _LOGGER.warning("Missing current_price in data")
            return False

        # Must have hourly prices with at least one entry
        if "hourly_prices" not in data or not data["hourly_prices"]:
            _LOGGER.warning("Missing or empty hourly_prices in data")
            return False

        # Check that hourly_prices is a dictionary
        if not isinstance(data["hourly_prices"], dict):
            _LOGGER.warning("hourly_prices is not a dictionary")
            return False

        # Check that at least one hourly price is non-None and is a valid number
        if not any(isinstance(price, (int, float)) and price is not None for price in data["hourly_prices"].values()):
            _LOGGER.warning("All hourly prices are None or not valid numbers")
            return False

        return True
