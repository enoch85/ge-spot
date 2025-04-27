import sys
import os
import getpass
import pytest
import logging
from datetime import datetime, timezone, timedelta
import pytz

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Go up two levels to reach the workspace root where custom_components is located
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from custom_components.ge_spot.api.entsoe import EntsoeAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService

@pytest.mark.asyncio
async def test_entsoe_full_chain():
    """
    Test the full chain from fetching ENTSOE data to price conversion.
    This test makes actual API calls and validates real responses.
    If it fails, we should fix the core code, not adapt the test.
    """
    area = "SE4"
    api_key = os.environ.get("ENTSOE_API_KEY")
    if not api_key:
        pytest.skip("ENTSOE_API_KEY environment variable not set")
    
    # Arrange
    api = EntsoeAPI(config={"api_key": api_key})
    logger.info(f"Fetching ENTSOE data for area: {area}")
    
    # Step 1: Fetch raw data - no exception handling, if this fails we want to know
    raw_data = await api.fetch_raw_data(area=area)
    
    # Validate raw data structure (basic checks)
    assert raw_data is not None, "Raw data should not be None"
    assert isinstance(raw_data, dict), f"Raw data should be a dictionary, got {type(raw_data)}"
    
    # Log raw data structure for debugging
    logger.info(f"Raw data contains keys: {list(raw_data.keys())}")
    
    # Step 2: Parse raw data
    parsed_data = await api.parse_raw_data(raw_data)
    
    # Validate parsed data format
    assert parsed_data is not None, "Parsed data should not be None"
    assert isinstance(parsed_data, dict), f"Parsed data should be a dictionary, got {type(parsed_data)}"
    
    # Required fields validation
    assert "hourly_prices" in parsed_data, "Parsed data should contain 'hourly_prices' key"
    assert "source" in parsed_data, "Parsed data should contain 'source' key"
    assert parsed_data["source"] == Source.ENTSOE, f"Source should be {Source.ENTSOE}, got {parsed_data.get('source')}"
    assert parsed_data["area"] == area, f"Area should be {area}, got {parsed_data.get('area')}"
    assert "currency" in parsed_data, "Parsed data should contain 'currency' key"
    assert parsed_data["currency"] == Currency.EUR, f"ENTSOE currency should be EUR, got {parsed_data.get('currency')}"
    
    # Validate hourly prices
    hourly_prices = parsed_data.get("hourly_prices", {})
    assert isinstance(hourly_prices, dict), f"hourly_prices should be a dictionary, got {type(hourly_prices)}"
    
    # Real-world validation: ENTSOE should return data
    assert hourly_prices, "No hourly prices found - this indicates a real issue with the API or parser"
    
    # Check for reasonable number of hours (at least 24 for day-ahead prices)
    min_expected_hours = 24
    assert len(hourly_prices) >= min_expected_hours, f"Expected at least {min_expected_hours} hourly prices, got {len(hourly_prices)}"
    
    logger.info(f"Parsed data contains {len(hourly_prices)} hourly prices")
    
    # Validate timestamp format and price values
    for timestamp, price in hourly_prices.items():
        try:
            # Validate ISO timestamp format
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            
            # Check timestamp is in a reasonable range (not too far in past/future)
            now = datetime.now().astimezone()
            three_days_ago = now - timedelta(days=3)
            five_days_ahead = now + timedelta(days=5)
            assert three_days_ago <= dt <= five_days_ahead, f"Timestamp {timestamp} outside reasonable range"
        except ValueError:
            pytest.fail(f"Invalid timestamp format: '{timestamp}'")
        
        # Validate price
        assert isinstance(price, float), f"Price should be a float, got {type(price)} for timestamp {timestamp}"
        
        # Real-world validation: Prices should be within reasonable bounds for electricity markets
        # ENTSOE prices typically range from -500 to 3000 EUR/MWh in extreme cases
        assert -1000 <= price <= 5000, f"Price {price} for {timestamp} is outside reasonable range"
    
    # Step 3: Test currency conversion
    # This tests a critical real-world function that users depend on
    exchange_service = ExchangeRateService()
    await exchange_service.get_rates(force_refresh=True)
    
    source_currency = parsed_data.get("currency")
    target_currency = Currency.SEK
    
    # Real-world validation: ENTSOE should return currency
    assert source_currency is not None, "Source currency should not be None"
    
    converted_prices = {}
    for ts, price in hourly_prices.items():
        # Test specific conversion logic - if this fails, it's a real issue
        price_converted = await exchange_service.convert(price, source_currency, target_currency)
        
        # Validate conversion result
        assert isinstance(price_converted, float), f"Converted price should be a float, got {type(price_converted)}"
        
        # Real-world validation: Conversion should produce non-zero results for non-zero inputs
        if abs(price) > 0.001:
            assert abs(price_converted) > 0.001, f"Conversion produced unexpectedly small value: {price_converted} from {price}"
        
        # Convert MWh -> kWh (this is what users see in the UI)
        price_kwh = price_converted / 1000
        converted_prices[ts] = price_kwh
    
    # Step 4: Validate today's hours
    # This verifies that we can extract data for the current day, which is a core feature
    market_tz = pytz.timezone('Europe/Stockholm')
    now = datetime.now(market_tz)
    today_local = now.date()
    
    # Find all hours for today in the local timezone
    today_hours = [ts for ts in converted_prices if datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(market_tz).date() == today_local]
    
    # Real-world validation: Should have complete data for today
    # Don't skip or modify this test - if it fails, there's a real issue to fix
    expected_hours = 24
    assert len(today_hours) == expected_hours, f"Expected {expected_hours} hourly prices for today, got {len(today_hours)}"
    
    # Verify timestamps are properly ordered and contiguous
    sorted_hours = sorted(today_hours)
    for i in range(1, len(sorted_hours)):
        prev_dt = datetime.fromisoformat(sorted_hours[i-1].replace('Z', '+00:00'))
        curr_dt = datetime.fromisoformat(sorted_hours[i].replace('Z', '+00:00'))
        hour_diff = (curr_dt - prev_dt).total_seconds() / 3600
        
        # Real-world validation: Hours should be sequential
        assert abs(hour_diff - 1.0) < 0.1, f"Non-hourly gap between {sorted_hours[i-1]} and {sorted_hours[i]}"
    
    # Log some example values for verification
    logger.info(f"Today's hours ({len(today_hours)}): {sorted_hours[:3]}... to {sorted_hours[-3:]}")
    logger.info(f"Price range: {min(converted_prices[ts] for ts in today_hours):.4f} to {max(converted_prices[ts] for ts in today_hours):.4f} {target_currency}/kWh")
    
    # Check if price variation exists (real markets have price variation)
    prices = [converted_prices[ts] for ts in today_hours]
    price_variation = max(prices) - min(prices)
    assert price_variation > 0.001, "No price variation found - suspicious for real market data"
    
    # Test complete - if we get here, the full chain works correctly
    logger.info("ENTSO-E Full Chain Test: PASS - All steps from API fetch to final price conversion are working")

if __name__ == "__main__":
    import asyncio
    print("Starting ENTSO-E full-chain test...")
    try:
        asyncio.run(test_entsoe_full_chain())
    except Exception as e:
        import traceback
        print("Exception occurred:")
        traceback.print_exc()
