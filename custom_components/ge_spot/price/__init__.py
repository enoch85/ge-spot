"""
Price module for the GE-Spot integration.
This module has been replaced by classes in the api/base/ directory.
"""

from ..api.base.data_structure import StandardizedPriceData

# Create a compatibility shim for ElectricityPriceAdapter
class ElectricityPriceAdapter:
    """Compatibility shim for the ElectricityPriceAdapter class.

    This class provides backward compatibility for code that was expecting
    the old ElectricityPriceAdapter class. It wraps the new StandardizedPriceData
    class from the refactored api/base directory.
    """

    def __init__(self, hass, data_list, include_vat=False):
        """Initialize the adapter with price data.

        Args:
            hass: Home Assistant instance
            data_list: List of price data
            include_vat: Whether to include VAT in prices
        """
        self.hass = hass
        self.data_list = data_list
        self.include_vat = include_vat
        self._process_data()

    def _process_data(self):
        """Process the data to extract prices and statistics."""
        # Initialize default empty values
        self.current_price = None
        self.next_hour_price = None
        self.hourly_prices = {}
        self.tomorrow_hourly_prices = {}
        self.prices_tomorrow_updated = False
        self.min_price = None
        self.max_price = None
        self.avg_price = None

        # Process each data item in the list
        for data in self.data_list:
            if not data:
                continue

            # Extract prices
            if "hourly_prices" in data and data["hourly_prices"]:
                self.hourly_prices.update(data["hourly_prices"])

            # Extract tomorrow's prices if available
            if "tomorrow_hourly_prices" in data and data["tomorrow_hourly_prices"]:
                self.tomorrow_hourly_prices.update(data["tomorrow_hourly_prices"])
                self.prices_tomorrow_updated = data.get("has_tomorrow_prices", False)

            # Current and next hour prices
            if "current_price" in data and data["current_price"] is not None:
                self.current_price = data["current_price"]

            if "next_hour_price" in data and data["next_hour_price"] is not None:
                self.next_hour_price = data["next_hour_price"]

            # Statistics
            if "statistics" in data and data["statistics"]:
                stats = data["statistics"]
                if "min" in stats and stats["min"] is not None:
                    self.min_price = stats["min"]
                if "max" in stats and stats["max"] is not None:
                    self.max_price = stats["max"]
                if "average" in stats and stats["average"] is not None:
                    self.avg_price = stats["average"]

    def get_prices(self):
        """Get all prices.

        Returns:
            Dictionary with hourly prices
        """
        return self.hourly_prices

    def get_tomorrow_prices(self):
        """Get tomorrow's prices if available.

        Returns:
            Dictionary with tomorrow's hourly prices
        """
        return self.tomorrow_hourly_prices

    def get_current_price(self):
        """Get the current price.

        Returns:
            Current price or None if not available
        """
        return self.current_price

    def get_next_price(self):
        """Get the next hour price.

        Returns:
            Next hour price or None if not available
        """
        return self.next_hour_price

    def get_min_price(self):
        """Get the minimum price.

        Returns:
            Minimum price or None if not available
        """
        return self.min_price

    def get_max_price(self):
        """Get the maximum price.

        Returns:
            Maximum price or None if not available
        """
        return self.max_price

    def get_average_price(self):
        """Get the average price.

        Returns:
            Average price or None if not available
        """
        return self.avg_price

    def has_tomorrow_prices(self):
        """Check if tomorrow's prices are available.

        Returns:
            True if tomorrow's prices are available, False otherwise
        """
        return self.prices_tomorrow_updated and bool(self.tomorrow_hourly_prices)

# Export the compatibility class
__all__ = ["ElectricityPriceAdapter"]
