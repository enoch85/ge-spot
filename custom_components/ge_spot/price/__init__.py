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
        self.next_interval_price = None
        self.interval_prices = {}
        self.tomorrow_interval_prices = {}
        self.prices_tomorrow_updated = False
        self.min_price = None
        self.max_price = None
        self.avg_price = None

        # Process each data item in the list
        for data in self.data_list:
            if not data:
                continue

            # Extract prices
            if "interval_prices" in data and data["interval_prices"]:
                self.interval_prices.update(data["interval_prices"])

            # Extract tomorrow's prices if available
            if "tomorrow_interval_prices" in data and data["tomorrow_interval_prices"]:
                self.tomorrow_interval_prices.update(data["tomorrow_interval_prices"])
                self.prices_tomorrow_updated = data.get("has_tomorrow_prices", False)

            # Current and next interval prices
            if "current_price" in data and data["current_price"] is not None:
                self.current_price = data["current_price"]

            if "next_interval_price" in data and data["next_interval_price"] is not None:
                self.next_interval_price = data["next_interval_price"]

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
            Dictionary with interval prices
        """
        return self.interval_prices

    def get_tomorrow_prices(self):
        """Get tomorrow's prices if available.

        Returns:
            Dictionary with tomorrow's interval prices
        """
        return self.tomorrow_interval_prices

    def get_current_price(self):
        """Get the current price.

        Returns:
            Current price or None if not available
        """
        return self.current_price

    def get_next_price(self):
        """Get the next interval price.

        Returns:
            Next interval price or None if not available
        """
        return self.next_interval_price

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
        return self.prices_tomorrow_updated and bool(self.tomorrow_interval_prices)

# Export the compatibility class
__all__ = ["ElectricityPriceAdapter"]
