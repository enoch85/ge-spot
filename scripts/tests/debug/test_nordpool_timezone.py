"""Test for Nordpool timezone handling."""
import asyncio
import logging
import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

# Add the parent directory to the path so we can import custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Configure logging
logging.basicConfig(level=logging.DEBUG)
_LOGGER = logging.getLogger(__name__)

async def test_nordpool_current_hour():
    """Test that Nordpool correctly identifies the current hour price."""
    # Using a mock approach since we can't directly connect to API in the test
    
    # Mock the raw data structure we'd get from Nordpool
    # This simulates what we'd get from the API with a sample of hours
    mock_today_date = datetime.now().date().strftime("%Y-%m-%d")
    mock_tomorrow_date = (datetime.now() + timedelta(days=1)).date().strftime("%Y-%m-%d")
    
    # Current hour for reference
    current_hour = datetime.now().hour
    current_hour_str = f"{current_hour:02d}:00"
    
    # Sample hours to test
    mock_raw_data = {
        f"{mock_today_date}T00:00:00": 10.5,
        f"{mock_today_date}T01:00:00": 11.2,
        # Skip to current hour
        f"{mock_today_date}T{current_hour:02d}:00:00": 25.5,
        # Add next hour
        f"{mock_today_date}T{(current_hour + 1) % 24:02d}:00:00": 26.8,
        # Add some tomorrow hours
        f"{mock_tomorrow_date}T00:00:00": 15.3,
        f"{mock_tomorrow_date}T01:00:00": 14.9,
        f"{mock_tomorrow_date}T{current_hour:02d}:00:00": 35.7,  # Same hour tomorrow
    }
    
    # Import only what we need to avoid dependencies
    from custom_components.ge_spot.timezone import TimezoneService
    from custom_components.ge_spot.timezone.converter import TimezoneConverter
    from custom_components.ge_spot.price.adapter import ElectricityPriceAdapter
    
    # Create converter instance
    converter = TimezoneConverter()
    
    # Convert timestamps to make sample today/tomorrow data format
    today_data = {}
    tomorrow_data = {}
    
    for timestamp, price in mock_raw_data.items():
        if mock_today_date in timestamp:
            today_data[timestamp] = price
        else:
            tomorrow_data[timestamp] = price
    
    # Create mock raw data structure as ElectricityPriceAdapter expects
    mock_data = [
        {
            "today_hourly_prices": today_data,
            "tomorrow_hourly_prices": tomorrow_data
        }
    ]
    
    # Create adapter
    adapter = ElectricityPriceAdapter(None, mock_data)
    
    # Get current price
    current_price = adapter.get_current_price()
    
    # Get today and tomorrow prices
    today_prices = adapter.today_hourly_prices
    tomorrow_prices = adapter.tomorrow_prices
    
    # Log all information
    _LOGGER.info(f"Current hour: {current_hour_str}")
    _LOGGER.info(f"Current price: {current_price}")
    _LOGGER.info("\nToday's prices:")
    for hour, price in today_prices.items():
        _LOGGER.info(f"  {hour}: {price}")
    
    _LOGGER.info("\nTomorrow's prices:")
    for hour, price in tomorrow_prices.items():
        _LOGGER.info(f"  {hour}: {price}")
    
    # Verify current hour is found in today's data
    assert current_price is not None, "Current price should not be None"
    assert current_price == 25.5, f"Expected 25.5 for current hour {current_hour_str}, got {current_price}"
    
    # Verify we're not using tomorrow's price for current hour
    tomorrow_current = tomorrow_prices.get(current_hour_str)
    assert tomorrow_current is not None, "Tomorrow should have an entry for current hour"
    assert current_price != tomorrow_current, "Current price should not match tomorrow's price for same hour"
    
    _LOGGER.info(f"\nTEST PASSED: Current hour ({current_hour_str}) price is {current_price}")
    
    return True

if __name__ == "__main__":
    # Run the test
    loop = asyncio.get_event_loop()
    try:
        result = loop.run_until_complete(test_nordpool_current_hour())
        print(f"\nTest result: {'PASS' if result else 'FAIL'}")
    except AssertionError as e:
        print(f"\nTest failed: {e}")
