"""Core adapter testing functionality for GE-Spot integration."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from custom_components.ge_spot.price.adapter import ElectricityPriceAdapter

logger = logging.getLogger(__name__)

class ImprovedElectricityPriceAdapter:
    """Improved adapter for electricity price data that can handle ISO format dates."""

    def __init__(self, hass, raw_data: List[Dict], use_subunit: bool = False) -> None:
        """Initialize the price adapter."""
        self.hass = hass
        self.raw_data = raw_data or []
        self.use_subunit = use_subunit

        # Get today's and tomorrow's dates for comparison
        self.today = datetime.now(timezone.utc).date()
        self.tomorrow = self.today + timedelta(days=1)

        # Extract core data once for reuse
        self.hourly_prices, self.dates_by_hour = self._extract_hourly_prices()
        self.tomorrow_prices, self.tomorrow_dates_by_hour = self._extract_tomorrow_prices()
        
        # If we don't have tomorrow prices but have dates in hourly prices,
        # try to extract tomorrow's data from hourly_prices
        if not self.tomorrow_prices and self.dates_by_hour:
            self._extract_tomorrow_from_hourly()
            
        self.price_list = self._convert_to_price_list(self.hourly_prices)
        self.tomorrow_list = self._convert_to_price_list(self.tomorrow_prices)

    def _parse_hour_from_string(self, hour_str: str) -> Tuple[Optional[int], Optional[datetime]]:
        """Parse hour and date from hour string.
        
        Args:
            hour_str: Hour string in either "HH:00", "tomorrow_HH:00", or ISO format
            
        Returns:
            Tuple of (hour, datetime) where hour is an integer 0-23 and datetime is the full datetime
            if available, or None if not available
        """
        # Check if this is a tomorrow hour from timezone conversion
        if hour_str.startswith("tomorrow_"):
            # Extract the hour key without the prefix
            hour_key = hour_str[9:]  # Remove "tomorrow_" prefix
            try:
                hour = int(hour_key.split(":")[0])
                if 0 <= hour < 24:  # Only accept valid hours
                    # Create a datetime for tomorrow with this hour
                    dt = datetime.combine(self.tomorrow, datetime.min.time().replace(hour=hour), timezone.utc)
                    return hour, dt
            except (ValueError, IndexError):
                pass
        
        # Try simple "HH:00" format first
        try:
            hour = int(hour_str.split(":")[0])
            if 0 <= hour < 24:
                return hour, None
        except (ValueError, IndexError):
            pass
            
        # Try ISO format
        if "T" in hour_str:
            try:
                # Handle ISO format with timezone
                dt = datetime.fromisoformat(hour_str.replace('Z', '+00:00'))
                return dt.hour, dt
            except (ValueError, TypeError):
                pass
                
        # If we get here, we couldn't parse the hour
        logger.warning(f"Could not parse hour from: {hour_str}")
        return None, None

    def _extract_hourly_prices(self) -> Tuple[Dict[str, float], Dict[str, datetime]]:
        """Extract hourly prices from raw data.
        
        Returns:
            Tuple of (hourly_prices, dates_by_hour) where hourly_prices is a dict of hour_key -> price
            and dates_by_hour is a dict of hour_key -> datetime
        """
        hourly_prices = {}
        dates_by_hour = {}

        for item in self.raw_data:
            if not isinstance(item, dict):
                continue

            if "hourly_prices" in item and isinstance(item["hourly_prices"], dict):
                # Store formatted hour -> price mapping
                logger.debug(f"Found hourly_prices in raw data: {len(item['hourly_prices'])} entries")
                for hour_str, price in item["hourly_prices"].items():
                    hour, dt = self._parse_hour_from_string(hour_str)
                    if hour is not None:
                        hour_key = f"{hour:02d}:00"
                        hourly_prices[hour_key] = price
                        if dt is not None:
                            dates_by_hour[hour_key] = dt

        logger.debug(f"Extracted {len(hourly_prices)} hourly prices: {sorted(hourly_prices.keys())}")
        return hourly_prices, dates_by_hour

    def _extract_tomorrow_prices(self) -> Tuple[Dict[str, float], Dict[str, datetime]]:
        """Extract tomorrow's hourly prices from raw data.
        
        Returns:
            Tuple of (tomorrow_prices, tomorrow_dates_by_hour) where tomorrow_prices is a dict of hour_key -> price
            and tomorrow_dates_by_hour is a dict of hour_key -> datetime
        """
        tomorrow_prices = {}
        tomorrow_dates_by_hour = {}

        for item in self.raw_data:
            if not isinstance(item, dict):
                continue

            if "tomorrow_hourly_prices" in item and isinstance(item["tomorrow_hourly_prices"], dict):
                # Store formatted hour -> price mapping
                logger.debug(f"Found tomorrow_hourly_prices in raw data: {len(item['tomorrow_hourly_prices'])} entries")
                for hour_str, price in item["tomorrow_hourly_prices"].items():
                    hour, dt = self._parse_hour_from_string(hour_str)
                    if hour is not None:
                        hour_key = f"{hour:02d}:00"
                        tomorrow_prices[hour_key] = price
                        if dt is not None:
                            tomorrow_dates_by_hour[hour_key] = dt

        logger.debug(f"Extracted {len(tomorrow_prices)} tomorrow prices: {sorted(tomorrow_prices.keys())}")
        return tomorrow_prices, tomorrow_dates_by_hour

    def _extract_tomorrow_from_hourly(self) -> None:
        """Extract tomorrow's data from hourly_prices if dates are available."""
        if not self.dates_by_hour:
            return
            
        # Look for hours with tomorrow's date
        tomorrow_hour_keys = []
        for hour_key, dt in self.dates_by_hour.items():
            if dt.date() == self.tomorrow:
                # This is tomorrow's data, move it to tomorrow_prices
                self.tomorrow_prices[hour_key] = self.hourly_prices[hour_key]
                self.tomorrow_dates_by_hour[hour_key] = dt
                tomorrow_hour_keys.append(hour_key)
                
        # Remove tomorrow's data from hourly_prices if we found any
        if self.tomorrow_prices:
            logger.info(f"Extracted {len(self.tomorrow_prices)} hours of tomorrow's data from hourly_prices")
            
            # Remove tomorrow's hours from hourly_prices
            for hour_key in tomorrow_hour_keys:
                if hour_key in self.hourly_prices:
                    del self.hourly_prices[hour_key]
                    
            logger.info(f"Kept {len(self.hourly_prices)} hours of today's data in hourly_prices")

    def _convert_to_price_list(self, price_dict: Dict[str, float]) -> List[float]:
        """Convert price dictionary to ordered list."""
        price_list = []

        # Format as sorted hour keys to ensure proper ordering
        for hour in range(24):
            hour_key = f"{hour:02d}:00"
            if hour_key in price_dict:
                price_list.append(price_dict[hour_key])

        return price_list

    def is_tomorrow_valid(self) -> bool:
        """Check if tomorrow's data is available."""
        # Consider valid if we have at least 20 hours of data
        is_valid = len(self.tomorrow_list) >= 20
        logger.debug(f"Tomorrow data validation: {len(self.tomorrow_list)}/24 hours available, valid: {is_valid}")
        return is_valid


def create_test_data_with_dates(today=None, tomorrow=None) -> Dict[str, Any]:
    """Create test data with ISO format dates in hourly_prices.
    
    Args:
        today: Today's date (defaults to current date)
        tomorrow: Tomorrow's date (defaults to today + 1 day)
        
    Returns:
        Dictionary with test data
    """
    if today is None:
        today = datetime.now(timezone.utc).date()
    if tomorrow is None:
        tomorrow = today + timedelta(days=1)
        
    hourly_prices = {}
    
    # Add today's hours with ISO format dates
    for hour in range(24):
        dt = datetime.combine(today, datetime.min.time().replace(hour=hour), timezone.utc)
        iso_key = dt.isoformat()
        hourly_prices[iso_key] = 10.0 + hour
    
    return {
        "hourly_prices": hourly_prices,
        "source": "test_source"
    }


def create_test_data_without_dates() -> Dict[str, Any]:
    """Create test data without dates in hourly_prices.
    
    Returns:
        Dictionary with test data
    """
    hourly_prices = {}
    
    # Add hours without dates
    for hour in range(24):
        hour_key = f"{hour:02d}:00"
        hourly_prices[hour_key] = 10.0 + hour
    
    return {
        "hourly_prices": hourly_prices,
        "source": "test_source"
    }


def create_test_data_mixed(today=None, tomorrow=None) -> Dict[str, Any]:
    """Create test data with mixed today's and tomorrow's data in hourly_prices.
    
    Args:
        today: Today's date (defaults to current date)
        tomorrow: Tomorrow's date (defaults to today + 1 day)
        
    Returns:
        Dictionary with test data
    """
    if today is None:
        today = datetime.now(timezone.utc).date()
    if tomorrow is None:
        tomorrow = today + timedelta(days=1)
        
    hourly_prices = {}
    
    # Add today's hours with ISO format dates
    for hour in range(12):  # First 12 hours of today
        dt = datetime.combine(today, datetime.min.time().replace(hour=hour), timezone.utc)
        iso_key = dt.isoformat()
        hourly_prices[iso_key] = 10.0 + hour
    
    # Add tomorrow's hours with ISO format dates
    for hour in range(24):  # All 24 hours of tomorrow
        dt = datetime.combine(tomorrow, datetime.min.time().replace(hour=hour), timezone.utc)
        iso_key = dt.isoformat()
        hourly_prices[iso_key] = 50.0 + hour
    
    # Print the hourly_prices to debug
    logger.info(f"Created mixed test data with {len(hourly_prices)} entries")
    logger.info(f"Today's date: {today}, Tomorrow's date: {tomorrow}")
    
    # Count entries by date
    today_count = 0
    tomorrow_count = 0
    for key in hourly_prices.keys():
        if today.isoformat() in key:
            today_count += 1
        elif tomorrow.isoformat() in key:
            tomorrow_count += 1
            
    logger.info(f"Today's entries: {today_count}, Tomorrow's entries: {tomorrow_count}")
    
    return {
        "hourly_prices": hourly_prices,
        "source": "test_source"
    }


def test_adapter_with_dates(hass, test_data_with_dates):
    """Test adapter with dates in hourly_prices.
    
    Args:
        hass: Home Assistant instance
        test_data_with_dates: Test data with dates
        
    Returns:
        Dictionary with test results
    """
    # Create adapter with data that has dates
    adapter = ElectricityPriceAdapter(hass, [test_data_with_dates], False)
    
    # Check if adapter preserves dates
    hourly_prices = adapter.hourly_prices
    
    # Log the keys to see what format they are in
    logger.info(f"Hourly price keys: {list(hourly_prices.keys())[:5]}")
    
    # Check if any keys in adapter hourly prices have dates
    adapter_has_dates = any("T" in key for key in hourly_prices.keys())
    
    return {
        "adapter_has_dates": adapter_has_dates,
        "hourly_prices_count": len(hourly_prices),
        "hourly_price_keys": list(hourly_prices.keys())[:5]
    }


def test_adapter_with_mixed_data(hass, test_data_mixed):
    """Test adapter with mixed today's and tomorrow's data.
    
    Args:
        hass: Home Assistant instance
        test_data_mixed: Test data with mixed today's and tomorrow's data
        
    Returns:
        Dictionary with test results
    """
    # Create adapter with mixed data
    adapter = ElectricityPriceAdapter(hass, [test_data_mixed], False)
    
    # Check if adapter has all hours
    hourly_prices = adapter.hourly_prices
    tomorrow_prices = adapter.tomorrow_prices
    
    # Log the keys to see what format they are in
    logger.info(f"Hourly price keys: {list(hourly_prices.keys())}")
    logger.info(f"Tomorrow price keys: {list(tomorrow_prices.keys())}")
    
    # Check if tomorrow's data is correctly identified
    is_tomorrow_valid = adapter.is_tomorrow_valid()
    
    return {
        "hourly_prices_count": len(hourly_prices),
        "tomorrow_prices_count": len(tomorrow_prices),
        "is_tomorrow_valid": is_tomorrow_valid,
        "hourly_price_keys": list(hourly_prices.keys()),
        "tomorrow_price_keys": list(tomorrow_prices.keys())
    }


def test_improved_adapter_with_mixed_data(hass, test_data_mixed):
    """Test improved adapter with mixed today's and tomorrow's data.
    
    Args:
        hass: Home Assistant instance
        test_data_mixed: Test data with mixed today's and tomorrow's data
        
    Returns:
        Dictionary with test results
    """
    # Create improved adapter with mixed data
    adapter = ImprovedElectricityPriceAdapter(hass, [test_data_mixed], False)
    
    # Check if adapter has separated today's and tomorrow's data
    hourly_prices = adapter.hourly_prices
    tomorrow_prices = adapter.tomorrow_prices
    
    # Log the keys to see what format they are in
    logger.info(f"Hourly price keys: {list(hourly_prices.keys())}")
    logger.info(f"Tomorrow price keys: {list(tomorrow_prices.keys())}")
    
    # Check if tomorrow's data is correctly identified
    is_tomorrow_valid = adapter.is_tomorrow_valid()
    
    return {
        "hourly_prices_count": len(hourly_prices),
        "tomorrow_prices_count": len(tomorrow_prices),
        "is_tomorrow_valid": is_tomorrow_valid,
        "hourly_price_keys": list(hourly_prices.keys()),
        "tomorrow_price_keys": list(tomorrow_prices.keys())
    }


def compare_adapters(hass, test_data_mixed):
    """Compare original and improved adapters with mixed data.
    
    Args:
        hass: Home Assistant instance
        test_data_mixed: Test data with mixed today's and tomorrow's data
        
    Returns:
        Dictionary with comparison results
    """
    # Test original adapter
    original_result = test_adapter_with_mixed_data(hass, test_data_mixed)
    
    # Test improved adapter
    improved_result = test_improved_adapter_with_mixed_data(hass, test_data_mixed)
    
    return {
        "original": original_result,
        "improved": improved_result,
        "comparison": {
            "original_identifies_tomorrow": original_result["is_tomorrow_valid"],
            "improved_identifies_tomorrow": improved_result["is_tomorrow_valid"],
            "original_tomorrow_hours": original_result["tomorrow_prices_count"],
            "improved_tomorrow_hours": improved_result["tomorrow_prices_count"]
        }
    }
