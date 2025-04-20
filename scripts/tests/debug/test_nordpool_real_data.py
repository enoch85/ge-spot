"""Test for Nordpool timezone handling with realistic data format."""
import asyncio
import logging
import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

# Add the parent directory to the path so we can import custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Configure logging
logging.basicConfig(level=logging.DEBUG)
_LOGGER = logging.getLogger(__name__)

async def test_nordpool_timezone_handling():
    """Test that Nordpool correctly identifies the current hour price with realistic data."""
    # Import components
    from custom_components.ge_spot.api.parsers.nordpool_parser import NordpoolPriceParser
    from custom_components.ge_spot.price.adapter import ElectricityPriceAdapter
    
    # Current time info for reference
    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now()
    current_hour = now_local.hour
    current_hour_str = f"{current_hour:02d}:00"
    
    # Print time information for reference
    print(f"Current time (UTC): {now_utc.strftime('%Y-%m-%d %H:%M:%S')} (hour: {now_utc.hour})")
    print(f"Current time (Local): {now_local.strftime('%Y-%m-%d %H:%M:%S')} (hour: {now_local.hour})")
    
    # Create a realistic mock Nordpool API response
    # Note: Nordpool API uses UTC timestamps in its deliveryStart field
    mock_today_date = now_utc.date().strftime("%Y-%m-%d")
    mock_tomorrow_date = (now_utc.date() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Create a timestamp for the current local hour in UTC
    utc_for_current_local_hour = now_utc.replace(hour=now_utc.hour, minute=0, second=0, microsecond=0)
    utc_hour_str = utc_for_current_local_hour.strftime("%Y-%m-%dT%H:00:00")
    
    # Create mock entries for a typical Nordpool API response
    mock_entries = []
    # Add entries for today
    for h in range(0, 24):
        entry_time = now_utc.replace(hour=h, minute=0, second=0, microsecond=0)
        entry_time_str = entry_time.strftime("%Y-%m-%dT%H:00:00")
        mock_entries.append({
            "deliveryStart": entry_time_str,
            "entryPerArea": {
                "SE4": 50.0 + h  # Price increases by hour for easy debugging
            }
        })
    
    # Add entries for tomorrow
    for h in range(0, 24):
        tomorrow = now_utc.date() + timedelta(days=1)
        entry_time = datetime.combine(tomorrow, datetime.min.time()).replace(
            hour=h, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        entry_time_str = entry_time.strftime("%Y-%m-%dT%H:00:00")
        mock_entries.append({
            "deliveryStart": entry_time_str,
            "entryPerArea": {
                "SE4": 100.0 + h  # Higher prices for tomorrow
            }
        })
    
    # Create mock API response in Nordpool format
    mock_data = {
        "multiAreaEntries": mock_entries
    }
    
    # Parse the data with our Nordpool parser
    parser = NordpoolPriceParser()
    parsed_data = parser.parse_hourly_prices(mock_data, "SE4")
    
    # Check if the result is in the expected format (dict with today/tomorrow keys)
    if isinstance(parsed_data, dict) and "today_hourly_prices" in parsed_data:
        today_prices = parsed_data["today_hourly_prices"]
        tomorrow_prices = parsed_data.get("tomorrow_hourly_prices", {})
    else:
        # Old format - all prices in one dict
        today_prices = parsed_data
        tomorrow_prices = {}
    
    # Create ElectricityPriceAdapter with parsed data
    adapter = ElectricityPriceAdapter(None, [{
        "today_hourly_prices": today_prices,
        "tomorrow_hourly_prices": tomorrow_prices
    }])
    
    # Get current price
    current_price = adapter.get_current_price()
    
    # Print the results
    print("\nParsed hourly prices:")
    print("\nToday's prices:")
    for hour_key in sorted(today_prices.keys()):
        price = today_prices[hour_key]
        print(f"  {hour_key}: {price}")
    
    print("\nTomorrow's prices:")
    for hour_key in sorted(tomorrow_prices.keys()):
        price = tomorrow_prices[hour_key]
        print(f"  {hour_key}: {price}")
    
    print(f"\nCurrent hour: {current_hour_str}")
    print(f"Current price: {current_price}")
    
    # Now test if we get the correct current price
    # For Nordpool, the current_price should be from today, not tomorrow
    # This was the issue in the original bug
    
    # Calculate expected price from today based on current hour
    expected_current_price = None
    for hour_key, price in today_prices.items():
        # Try to match based on hour number for simple keys
        if ':' in hour_key and not 'T' in hour_key:
            hour = int(hour_key.split(':')[0])
            if hour == current_hour:
                expected_current_price = price
                break
        # For ISO format timestamps, parse and check hour
        elif 'T' in hour_key:
            try:
                dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                # Convert to local timezone for comparison
                if dt.tzinfo is timezone.utc:
                    dt = dt.astimezone(None)
                if dt.hour == current_hour:
                    expected_current_price = price
                    break
            except (ValueError, TypeError):
                continue
    
    # Verify results
    if current_price is None:
        print("\nTEST FAILED: Current price is None")
        return False
    
    if expected_current_price is None:
        print("\nTEST WARNING: Could not determine expected price for current hour")
        return True
    
    if current_price == expected_current_price:
        print(f"\nTEST PASSED: Current price matches expected ({current_price})")
        return True
    else:
        print(f"\nTEST FAILED: Current price {current_price} does not match expected {expected_current_price}")
        return False

if __name__ == "__main__":
    # Run the test
    loop = asyncio.get_event_loop()
    try:
        result = loop.run_until_complete(test_nordpool_timezone_handling())
        print(f"\nOverall test result: {'PASS' if result else 'FAIL'}")
    except Exception as e:
        print(f"\nTest error: {str(e)}")
        import traceback
        traceback.print_exc()
