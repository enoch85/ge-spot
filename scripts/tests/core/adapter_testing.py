"""Core adapter testing functionality for GE-Spot integration."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from custom_components.ge_spot.price.adapter import ElectricityPriceAdapter

logger = logging.getLogger(__name__)

class ImprovedElectricityPriceAdapter(ElectricityPriceAdapter):
    """
    This class now extends the standard ElectricityPriceAdapter.
    
    The improved functionality has been incorporated into the main ElectricityPriceAdapter class.
    This class is kept for backward compatibility with existing tests.
    """
    # Since all the improved functionality is now in the parent class,
    # we don't need to implement any additional methods


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
