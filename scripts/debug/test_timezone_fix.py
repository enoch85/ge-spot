#!/usr/bin/env python3
"""Test script for the timezone fix."""
import sys
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

# Add the parent directory to the path so we can import the custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Import the timezone service
from custom_components.ge_spot.timezone.service import TimezoneService
from custom_components.ge_spot.timezone.timezone_utils import get_timezone_object
from custom_components.ge_spot.const.time import TimezoneName
from custom_components.ge_spot.const.sources import Source

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def create_test_data() -> Dict[str, float]:
    """Create test data with ISO timestamps for both today and tomorrow."""
    # Get today and tomorrow dates
    today = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)
    
    # Create hourly prices for today and tomorrow
    hourly_prices = {}
    
    # Add today's prices (every hour)
    for hour in range(24):
        dt = datetime.combine(today, datetime.min.time().replace(hour=hour), timezone.utc)
        iso_key = dt.isoformat()
        hourly_prices[iso_key] = float(hour) + 10.0  # Simple price pattern
        
    # Add tomorrow's prices (every hour)
    for hour in range(24):
        dt = datetime.combine(tomorrow, datetime.min.time().replace(hour=hour), timezone.utc)
        iso_key = dt.isoformat()
        hourly_prices[iso_key] = float(hour) + 50.0  # Different price pattern for tomorrow
    
    # Add a few simple format hours (without date information)
    for hour in range(5):
        simple_key = f"{hour:02d}:00"
        hourly_prices[simple_key] = float(hour) + 100.0  # Yet another price pattern
    
    return hourly_prices

def test_sort_today_tomorrow():
    """Test the sort_today_tomorrow method."""
    logger.info("Testing sort_today_tomorrow method")
    
    # Create a TimezoneService instance
    tz_service = TimezoneService()
    
    # Create test data
    hourly_prices = create_test_data()
    logger.info(f"Created {len(hourly_prices)} test hourly prices")
    
    # Sort the prices into today and tomorrow buckets
    today_prices, tomorrow_prices = tz_service.sort_today_tomorrow(
        hourly_prices, 
        source_timezone=TimezoneName.UTC
    )
    
    # Log the results
    logger.info(f"Sorted into {len(today_prices)} today prices and {len(tomorrow_prices)} tomorrow prices")
    
    # Verify that the prices were sorted correctly
    today = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)
    
    # Check a few today prices
    for hour in [0, 6, 12, 18]:
        hour_key = f"{hour:02d}:00"
        if hour_key in today_prices:
            logger.info(f"Today price for {hour_key}: {today_prices[hour_key]}")
        else:
            logger.warning(f"No today price found for {hour_key}")
    
    # Check a few tomorrow prices
    for hour in [0, 6, 12, 18]:
        hour_key = f"{hour:02d}:00"
        if hour_key in tomorrow_prices:
            logger.info(f"Tomorrow price for {hour_key}: {tomorrow_prices[hour_key]}")
        else:
            logger.warning(f"No tomorrow price found for {hour_key}")
    
    # Verify that the simple format hours were assigned to today
    for hour in range(5):
        hour_key = f"{hour:02d}:00"
        if hour_key in today_prices and today_prices[hour_key] > 100.0:
            logger.info(f"Simple format hour {hour_key} was correctly assigned to today: {today_prices[hour_key]}")
        else:
            logger.warning(f"Simple format hour {hour_key} was not correctly assigned to today")
    
    return today_prices, tomorrow_prices

def test_different_timezones():
    """Test sorting with different source and target timezones."""
    logger.info("\nTesting with different timezones")
    
    # Create test data
    hourly_prices = create_test_data()
    
    # Test with different source and target timezones
    source_timezones = [TimezoneName.UTC, "Europe/Stockholm", "America/New_York"]
    
    for source_tz in source_timezones:
        logger.info(f"\nTesting with source timezone: {source_tz}")
        
        # Create a TimezoneService instance with area-specific timezone
        tz_service = TimezoneService()
        
        # Sort the prices
        today_prices, tomorrow_prices = tz_service.sort_today_tomorrow(
            hourly_prices, 
            source_timezone=source_tz
        )
        
        # Log the results
        logger.info(f"Sorted into {len(today_prices)} today prices and {len(tomorrow_prices)} tomorrow prices")
        
        # Check a few hours
        for hour in [0, 12]:
            hour_key = f"{hour:02d}:00"
            if hour_key in today_prices:
                logger.info(f"Today price for {hour_key}: {today_prices[hour_key]}")
            if hour_key in tomorrow_prices:
                logger.info(f"Tomorrow price for {hour_key}: {tomorrow_prices[hour_key]}")

def test_with_real_data():
    """Test with data that mimics the real price data format."""
    logger.info("\nTesting with real-like data")
    
    # Create a mix of ISO and simple format timestamps
    hourly_prices = {}
    
    # Today's date
    today = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)
    
    # Add some ISO format timestamps for today
    for hour in range(24):
        dt = datetime.combine(today, datetime.min.time().replace(hour=hour), timezone.utc)
        iso_key = dt.isoformat()
        hourly_prices[iso_key] = float(hour) + 20.0
    
    # Add some ISO format timestamps for tomorrow
    for hour in range(24):
        dt = datetime.combine(tomorrow, datetime.min.time().replace(hour=hour), timezone.utc)
        iso_key = dt.isoformat()
        hourly_prices[iso_key] = float(hour) + 60.0
    
    # Add some simple format timestamps (these should default to today)
    for hour in range(24):
        simple_key = f"{hour:02d}:00"
        hourly_prices[simple_key] = float(hour) + 100.0
    
    # Add some tomorrow-prefixed timestamps
    for hour in range(24):
        prefixed_key = f"tomorrow_{hour:02d}:00"
        hourly_prices[prefixed_key] = float(hour) + 150.0
    
    # Create a TimezoneService instance
    tz_service = TimezoneService()
    
    # Sort the prices
    today_prices, tomorrow_prices = tz_service.sort_today_tomorrow(
        hourly_prices, 
        source_timezone=TimezoneName.UTC
    )
    
    # Log the results
    logger.info(f"Sorted into {len(today_prices)} today prices and {len(tomorrow_prices)} tomorrow prices")
    
    # Check a few hours
    for hour in [0, 12, 23]:
        hour_key = f"{hour:02d}:00"
        if hour_key in today_prices:
            logger.info(f"Today price for {hour_key}: {today_prices[hour_key]}")
        if hour_key in tomorrow_prices:
            logger.info(f"Tomorrow price for {hour_key}: {tomorrow_prices[hour_key]}")

def main():
    """Run the tests."""
    logger.info("Starting timezone fix tests")
    
    # Test the sort_today_tomorrow method
    test_sort_today_tomorrow()
    
    # Test with different timezones
    test_different_timezones()
    
    # Test with real-like data
    test_with_real_data()
    
    logger.info("All tests completed")

if __name__ == "__main__":
    main()
