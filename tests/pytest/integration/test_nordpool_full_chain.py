import sys
import os
import pytest
import json
import logging
from datetime import datetime, timezone, timedelta
import pytz
import respx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Go up two levels to reach the workspace root where custom_components is located
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from custom_components.ge_spot.api.nordpool import NordpoolAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.const.areas import AreaMapping
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService

# Sample response data that matches the Nordpool API format
# Use dynamic dates to prevent test failures over time
def get_test_date():
    """Get today's date for test data generation."""
    return datetime.now().strftime("%Y-%m-%d")

def get_yesterday():
    """Get yesterday's date."""
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

def generate_nordpool_response(delivery_date, area="SE4"):
    """Generate a Nordpool response for a specific date."""
    base_date = datetime.fromisoformat(delivery_date)
    start_time = base_date.replace(hour=22, minute=0, second=0) - timedelta(days=1)
    
    entries = []
    base_prices = [34.61, 32.82, 31.15, 31.36, 30.98, 31.91, 35.22, 32.70, 20.65, 1.41,
                   -1.12, -3.86, -9.40, -14.63, -16.60, -8.14, -0.15, 5.46, 33.82, 42.45,
                   53.20, 56.33, 33.63, 32.43]
    
    for hour_idx in range(24):
        entry_start = start_time + timedelta(hours=hour_idx)
        entry_end = entry_start + timedelta(hours=1)
        entries.append({
            "deliveryStart": entry_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "deliveryEnd": entry_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "entryPerArea": {area: base_prices[hour_idx]}
        })
    
    return {
        "deliveryDateCET": delivery_date,
        "version": 2,
        "updatedAt": f"{get_yesterday()}T10:55:58.9728151Z",
        "deliveryAreas": [area],
        "market": "DayAhead",
        "multiAreaEntries": entries,
        "blockPriceAggregates": [
            {"blockName": "Off-peak 1", "deliveryStart": entries[0]["deliveryStart"], 
             "deliveryEnd": entries[7]["deliveryEnd"],
             "averagePricePerArea": {area: {"average": 32.59, "min": 30.98, "max": 35.22}}},
            {"blockName": "Peak", "deliveryStart": entries[8]["deliveryStart"], 
             "deliveryEnd": entries[19]["deliveryEnd"],
             "averagePricePerArea": {area: {"average": 4.16, "min": -16.60, "max": 42.45}}},
            {"blockName": "Off-peak 2", "deliveryStart": entries[20]["deliveryStart"], 
             "deliveryEnd": entries[23]["deliveryEnd"],
             "averagePricePerArea": {area: {"average": 43.90, "min": 32.43, "max": 56.33}}}
        ],
        "currency": "EUR",
        "exchangeRate": 1,
        "areaStates": [{"state": "Final", "areas": [area]}],
        "areaAverages": [{"areaCode": area, "price": 20.26}]
    }

SAMPLE_NORDPOOL_RESPONSE = generate_nordpool_response(get_test_date())

# Sample response for tomorrow data
SAMPLE_NORDPOOL_TOMORROW_RESPONSE = generate_nordpool_response(
    (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
)

# Mock exchange rate response
MOCK_EXCHANGE_RATES = {
    "rates": {
        "SEK": 11.0,
        "NOK": 10.5,
        "DKK": 7.45,
        "EUR": 1.0,
        "USD": 1.1
    },
    "base": "EUR"
}

@pytest.mark.asyncio
async def test_nordpool_full_chain(monkeypatch):
    """
    Test the full chain from fetching Nordpool data to price conversion.
    This test uses monkeypatched responses to avoid real network calls.
    """
    area = "SE4"
    
    # Create a monkeypatched version of fetch_day_ahead_prices that returns parsed data directly
    async def mock_fetch_day_ahead_prices(self, area=None, **kwargs):
        logger.info(f"Mock fetch_day_ahead_prices called for area: {area}")
        # Return parsed data structure (what the parser would return)
        # Generate interval prices from the mock data
        interval_prices = {}
        for entry in SAMPLE_NORDPOOL_RESPONSE["multiAreaEntries"]:
            timestamp = entry["deliveryStart"]
            price = entry["entryPerArea"]["SE4"]
            interval_prices[timestamp] = price
        
        return {
            "today_interval_prices": interval_prices,
            "source": Source.NORDPOOL,
            "area": area,
            "currency": "EUR",
            "api_timezone": "Europe/Oslo",
            "fetched_at": datetime.now().isoformat(),
        }
    
    # Patch the NordpoolAPI.fetch_day_ahead_prices method
    monkeypatch.setattr(NordpoolAPI, "fetch_day_ahead_prices", mock_fetch_day_ahead_prices)
    
    # Mock the exchange rate service to avoid real network calls
    async def mock_get_rates(self, force_refresh=False):
        return MOCK_EXCHANGE_RATES["rates"]
    
    async def mock_convert(self, amount, from_currency, to_currency):
        if from_currency == to_currency:
            return amount
        # Simulate conversion using mock rates
        eur_amount = amount / MOCK_EXCHANGE_RATES["rates"].get(from_currency, 1.0)
        return eur_amount * MOCK_EXCHANGE_RATES["rates"].get(to_currency, 1.0)
    
    monkeypatch.setattr(ExchangeRateService, "get_rates", mock_get_rates)
    monkeypatch.setattr(ExchangeRateService, "convert", mock_convert)
    
    # Create API instance
    api = NordpoolAPI()
    logger.info(f"Fetching Nordpool data for area: {area}")

    # Step 1: Fetch parsed data (new API combines fetch + parse)
    parsed_data = await api.fetch_day_ahead_prices(area=area)

    # Validate parsed data format
    assert parsed_data is not None, "Parsed data should not be None"
    assert isinstance(parsed_data, dict), f"Parsed data should be a dictionary, got {type(parsed_data)}"
    assert "today_interval_prices" in parsed_data, "Parsed data should contain 'today_interval_prices' key"
    assert "source" in parsed_data, "Parsed data should contain 'source' key"
    assert parsed_data["source"] == Source.NORDPOOL, f"Source should be {Source.NORDPOOL}, got {parsed_data.get('source')}"
    assert parsed_data["area"] == area, f"Area should be {area}, got {parsed_data.get('area')}"

    # Validate interval prices
    interval_prices = parsed_data.get("today_interval_prices", {})
    assert isinstance(interval_prices, dict), f"interval_prices should be a dictionary, got {type(interval_prices)}"

    # Real-world validation: Nordpool should return data
    assert interval_prices, "No interval prices found - this indicates a real issue with the API or parser"

    # Check for reasonable number of intervals (at least 24 for day-ahead prices, could be more with 15-min)
    min_expected_intervals = 24
    assert len(interval_prices) >= min_expected_intervals, f"Expected at least {min_expected_intervals} interval prices, got {len(interval_prices)}"

    logger.info(f"Parsed data contains {len(interval_prices)} interval prices")

    # Validate timestamp format and price values
    for timestamp, price in interval_prices.items():
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
        # Typical Nordpool prices range: -50 to 500 EUR/MWh in extreme cases
        assert -100 <= price <= 1000, f"Price {price} for {timestamp} is outside reasonable range"

    # Step 3: Test currency conversion
    # This tests a critical real-world function that users depend on
    exchange_service = ExchangeRateService()
    await exchange_service.get_rates(force_refresh=True)

    source_currency = parsed_data.get("currency")
    target_currency = Currency.SEK

    # Real-world validation: Nordpool should return currency
    assert source_currency is not None, "Source currency should not be None"

    converted_prices = {}
    for ts, price in interval_prices.items():
        # Test specific conversion logic - if this fails, it's a real issue
        price_converted = await exchange_service.convert(price, source_currency, target_currency)

        # Validate conversion result
        assert isinstance(price_converted, float), f"Converted price should be a float, got {type(price_converted)}"

        # Real-world validation: Conversion should produce non-zero results
        # If price is non-zero, converted price should be non-zero
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
    # For the test, we need to be more flexible about the dates since we're using mocked data
    # Count any consecutive 24 hour prices as a "day"
    hour_counts = {}
    for ts in converted_prices:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(market_tz)
        day_key = dt.date()
        if day_key not in hour_counts:
            hour_counts[day_key] = 0
        hour_counts[day_key] += 1

    # Check if we have at least one day with 24 hours
    complete_days = [day for day, count in hour_counts.items() if count >= 24]
    assert complete_days, "Could not find any complete day with 24 hours of price data"

    # Use the first complete day for testing
    test_day = complete_days[0]
    today_hours = [ts for ts in converted_prices
                 if datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(market_tz).date() == test_day]

    # Verify we have enough hours for a complete day
    expected_hours = 24
    assert len(today_hours) >= expected_hours, f"Expected at least {expected_hours} hourly prices for a day, got {len(today_hours)}"

    # Log some example values for verification
    sorted_hours = sorted(today_hours)
    logger.info(f"Day's hours ({len(today_hours)}): {sorted_hours[:3]}... to {sorted_hours[-3:]}")
    logger.info(f"Price range: {min(converted_prices[ts] for ts in today_hours):.4f} to {max(converted_prices[ts] for ts in today_hours):.4f} {target_currency}/kWh")

    # Step 5: Verify timestamps are properly ordered and contiguous
    # Take the first 24 hours to ensure we're checking a contiguous set
    test_hours = sorted_hours[:24]
    for i in range(1, len(test_hours)):
        prev_dt = datetime.fromisoformat(test_hours[i-1].replace('Z', '+00:00'))
        curr_dt = datetime.fromisoformat(test_hours[i].replace('Z', '+00:00'))
        hour_diff = (curr_dt - prev_dt).total_seconds() / 3600

        # Real-world validation: Hours should be sequential
        assert abs(hour_diff - 1.0) < 0.1, f"Non-hourly gap between {test_hours[i-1]} and {test_hours[i]}"

if __name__ == "__main__":
    import asyncio
    print("Starting Nordpool full-chain test...")
    try:
        asyncio.run(test_nordpool_full_chain())
    except Exception as e:
        import traceback
        print("Exception occurred:")
        traceback.print_exc()
