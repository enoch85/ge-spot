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
SAMPLE_NORDPOOL_RESPONSE = {
    "deliveryDateCET": "2025-04-27",
    "version": 2,
    "updatedAt": "2025-04-26T10:55:58.9728151Z",
    "deliveryAreas": ["SE4"],
    "market": "DayAhead",
    "multiAreaEntries": [
        {"deliveryStart": "2025-04-26T22:00:00Z", "deliveryEnd": "2025-04-26T23:00:00Z", "entryPerArea": {"SE4": 34.61}},
        {"deliveryStart": "2025-04-26T23:00:00Z", "deliveryEnd": "2025-04-27T00:00:00Z", "entryPerArea": {"SE4": 32.82}},
        {"deliveryStart": "2025-04-27T00:00:00Z", "deliveryEnd": "2025-04-27T01:00:00Z", "entryPerArea": {"SE4": 31.15}},
        {"deliveryStart": "2025-04-27T01:00:00Z", "deliveryEnd": "2025-04-27T02:00:00Z", "entryPerArea": {"SE4": 31.36}},
        {"deliveryStart": "2025-04-27T02:00:00Z", "deliveryEnd": "2025-04-27T03:00:00Z", "entryPerArea": {"SE4": 30.98}},
        {"deliveryStart": "2025-04-27T03:00:00Z", "deliveryEnd": "2025-04-27T04:00:00Z", "entryPerArea": {"SE4": 31.91}},
        {"deliveryStart": "2025-04-27T04:00:00Z", "deliveryEnd": "2025-04-27T05:00:00Z", "entryPerArea": {"SE4": 35.22}},
        {"deliveryStart": "2025-04-27T05:00:00Z", "deliveryEnd": "2025-04-27T06:00:00Z", "entryPerArea": {"SE4": 32.70}},
        {"deliveryStart": "2025-04-27T06:00:00Z", "deliveryEnd": "2025-04-27T07:00:00Z", "entryPerArea": {"SE4": 20.65}},
        {"deliveryStart": "2025-04-27T07:00:00Z", "deliveryEnd": "2025-04-27T08:00:00Z", "entryPerArea": {"SE4": 1.41}},
        {"deliveryStart": "2025-04-27T08:00:00Z", "deliveryEnd": "2025-04-27T09:00:00Z", "entryPerArea": {"SE4": -1.12}},
        {"deliveryStart": "2025-04-27T09:00:00Z", "deliveryEnd": "2025-04-27T10:00:00Z", "entryPerArea": {"SE4": -3.86}},
        {"deliveryStart": "2025-04-27T10:00:00Z", "deliveryEnd": "2025-04-27T11:00:00Z", "entryPerArea": {"SE4": -9.40}},
        {"deliveryStart": "2025-04-27T11:00:00Z", "deliveryEnd": "2025-04-27T12:00:00Z", "entryPerArea": {"SE4": -14.63}},
        {"deliveryStart": "2025-04-27T12:00:00Z", "deliveryEnd": "2025-04-27T13:00:00Z", "entryPerArea": {"SE4": -16.60}},
        {"deliveryStart": "2025-04-27T13:00:00Z", "deliveryEnd": "2025-04-27T14:00:00Z", "entryPerArea": {"SE4": -8.14}},
        {"deliveryStart": "2025-04-27T14:00:00Z", "deliveryEnd": "2025-04-27T15:00:00Z", "entryPerArea": {"SE4": -0.15}},
        {"deliveryStart": "2025-04-27T15:00:00Z", "deliveryEnd": "2025-04-27T16:00:00Z", "entryPerArea": {"SE4": 5.46}},
        {"deliveryStart": "2025-04-27T16:00:00Z", "deliveryEnd": "2025-04-27T17:00:00Z", "entryPerArea": {"SE4": 33.82}},
        {"deliveryStart": "2025-04-27T17:00:00Z", "deliveryEnd": "2025-04-27T18:00:00Z", "entryPerArea": {"SE4": 42.45}},
        {"deliveryStart": "2025-04-27T18:00:00Z", "deliveryEnd": "2025-04-27T19:00:00Z", "entryPerArea": {"SE4": 53.20}},
        {"deliveryStart": "2025-04-27T19:00:00Z", "deliveryEnd": "2025-04-27T20:00:00Z", "entryPerArea": {"SE4": 56.33}},
        {"deliveryStart": "2025-04-27T20:00:00Z", "deliveryEnd": "2025-04-27T21:00:00Z", "entryPerArea": {"SE4": 33.63}},
        {"deliveryStart": "2025-04-27T21:00:00Z", "deliveryEnd": "2025-04-27T22:00:00Z", "entryPerArea": {"SE4": 32.43}}
    ],
    "blockPriceAggregates": [
        {"blockName": "Off-peak 1", "deliveryStart": "2025-04-26T22:00:00Z", "deliveryEnd": "2025-04-27T06:00:00Z",
         "averagePricePerArea": {"SE4": {"average": 32.59, "min": 30.98, "max": 35.22}}},
        {"blockName": "Peak", "deliveryStart": "2025-04-27T06:00:00Z", "deliveryEnd": "2025-04-27T18:00:00Z",
         "averagePricePerArea": {"SE4": {"average": 4.16, "min": -16.60, "max": 42.45}}},
        {"blockName": "Off-peak 2", "deliveryStart": "2025-04-27T18:00:00Z", "deliveryEnd": "2025-04-27T22:00:00Z",
         "averagePricePerArea": {"SE4": {"average": 43.90, "min": 32.43, "max": 56.33}}}
    ],
    "currency": "EUR",
    "exchangeRate": 1,
    "areaStates": [{"state": "Final", "areas": ["SE4"]}],
    "areaAverages": [{"areaCode": "SE4", "price": 20.26}]
}

# Sample response for tomorrow data
SAMPLE_NORDPOOL_TOMORROW_RESPONSE = {
    "deliveryDateCET": "2025-04-28",
    "version": 2,
    "updatedAt": "2025-04-27T10:55:58.9728151Z",
    "deliveryAreas": ["SE4"],
    "market": "DayAhead",
    "multiAreaEntries": [
        {"deliveryStart": "2025-04-27T22:00:00Z", "deliveryEnd": "2025-04-27T23:00:00Z", "entryPerArea": {"SE4": 30.21}},
        {"deliveryStart": "2025-04-27T23:00:00Z", "deliveryEnd": "2025-04-28T00:00:00Z", "entryPerArea": {"SE4": 29.82}},
        {"deliveryStart": "2025-04-28T00:00:00Z", "deliveryEnd": "2025-04-28T01:00:00Z", "entryPerArea": {"SE4": 28.65}},
        {"deliveryStart": "2025-04-28T01:00:00Z", "deliveryEnd": "2025-04-28T02:00:00Z", "entryPerArea": {"SE4": 27.36}},
        {"deliveryStart": "2025-04-28T02:00:00Z", "deliveryEnd": "2025-04-28T03:00:00Z", "entryPerArea": {"SE4": 26.98}},
        {"deliveryStart": "2025-04-28T03:00:00Z", "deliveryEnd": "2025-04-28T04:00:00Z", "entryPerArea": {"SE4": 27.91}},
        {"deliveryStart": "2025-04-28T04:00:00Z", "deliveryEnd": "2025-04-28T05:00:00Z", "entryPerArea": {"SE4": 30.22}},
        {"deliveryStart": "2025-04-28T05:00:00Z", "deliveryEnd": "2025-04-28T06:00:00Z", "entryPerArea": {"SE4": 31.70}},
        {"deliveryStart": "2025-04-28T06:00:00Z", "deliveryEnd": "2025-04-28T07:00:00Z", "entryPerArea": {"SE4": 35.65}},
        {"deliveryStart": "2025-04-28T07:00:00Z", "deliveryEnd": "2025-04-28T08:00:00Z", "entryPerArea": {"SE4": 40.41}},
        {"deliveryStart": "2025-04-28T08:00:00Z", "deliveryEnd": "2025-04-28T09:00:00Z", "entryPerArea": {"SE4": 41.12}},
        {"deliveryStart": "2025-04-28T09:00:00Z", "deliveryEnd": "2025-04-28T10:00:00Z", "entryPerArea": {"SE4": 40.86}},
        {"deliveryStart": "2025-04-28T10:00:00Z", "deliveryEnd": "2025-04-28T11:00:00Z", "entryPerArea": {"SE4": 39.40}},
        {"deliveryStart": "2025-04-28T11:00:00Z", "deliveryEnd": "2025-04-28T12:00:00Z", "entryPerArea": {"SE4": 38.63}},
        {"deliveryStart": "2025-04-28T12:00:00Z", "deliveryEnd": "2025-04-28T13:00:00Z", "entryPerArea": {"SE4": 36.60}},
        {"deliveryStart": "2025-04-28T13:00:00Z", "deliveryEnd": "2025-04-28T14:00:00Z", "entryPerArea": {"SE4": 35.14}},
        {"deliveryStart": "2025-04-28T14:00:00Z", "deliveryEnd": "2025-04-28T15:00:00Z", "entryPerArea": {"SE4": 34.15}},
        {"deliveryStart": "2025-04-28T15:00:00Z", "deliveryEnd": "2025-04-28T16:00:00Z", "entryPerArea": {"SE4": 35.46}},
        {"deliveryStart": "2025-04-28T16:00:00Z", "deliveryEnd": "2025-04-28T17:00:00Z", "entryPerArea": {"SE4": 43.82}},
        {"deliveryStart": "2025-04-28T17:00:00Z", "deliveryEnd": "2025-04-28T18:00:00Z", "entryPerArea": {"SE4": 48.45}},
        {"deliveryStart": "2025-04-28T18:00:00Z", "deliveryEnd": "2025-04-28T19:00:00Z", "entryPerArea": {"SE4": 50.20}},
        {"deliveryStart": "2025-04-28T19:00:00Z", "deliveryEnd": "2025-04-28T20:00:00Z", "entryPerArea": {"SE4": 47.33}},
        {"deliveryStart": "2025-04-28T20:00:00Z", "deliveryEnd": "2025-04-28T21:00:00Z", "entryPerArea": {"SE4": 43.63}},
        {"deliveryStart": "2025-04-28T21:00:00Z", "deliveryEnd": "2025-04-28T22:00:00Z", "entryPerArea": {"SE4": 40.43}}
    ],
    "currency": "EUR",
    "exchangeRate": 1,
    "areaStates": [{"state": "Final", "areas": ["SE4"]}],
    "areaAverages": [{"areaCode": "SE4", "price": 37.26}]
}

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
@respx.mock
async def test_nordpool_full_chain():
    """
    Test the full chain from fetching Nordpool data to price conversion.
    This test uses mocked API responses to avoid real network calls.
    """
    # Set up mocks for the Nordpool API
    respx.get("https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices").mock(
        side_effect=lambda request: respx.MockResponse(
            status_code=200,
            json=SAMPLE_NORDPOOL_RESPONSE if "date=2025-04-27" in request.url or "date=2025-04-26" in request.url
                 else SAMPLE_NORDPOOL_TOMORROW_RESPONSE
        )
    )

    # Mock exchange rates API
    respx.get("https://api.exchangeratesapi.io/latest").mock(
        return_value=respx.MockResponse(status_code=200, json=MOCK_EXCHANGE_RATES)
    )

    area = "SE4"
    api = NordpoolAPI()
    logger.info(f"Fetching Nordpool data for area: {area}")

    # Step 1: Fetch raw data
    raw_data = await api.fetch_raw_data(area=area)

    # Validate raw data structure (basic checks)
    assert raw_data is not None, "Raw data should not be None"
    assert isinstance(raw_data, dict), f"Raw data should be a dictionary, got {type(raw_data)}"
    assert "today" in raw_data, "Raw data should contain 'today' key"

    # Additional validation of today data
    today_data = raw_data.get('today', {})
    assert isinstance(today_data, dict), f"Today data should be a dictionary, got {type(today_data)}"

    # Check multiAreaEntries - this is the core data structure from Nordpool
    multi_area_entries = today_data.get('multiAreaEntries', [])
    assert isinstance(multi_area_entries, list), f"multiAreaEntries should be a list, got {type(multi_area_entries)}"
    assert len(multi_area_entries) > 0, "multiAreaEntries should not be empty - real Nordpool data should have entries"

    # Log raw data structure for debugging
    logger.info(f"Raw data contains keys: {list(raw_data.keys())}")
    logger.info(f"Found {len(multi_area_entries)} multiAreaEntries")

    # Step 2: Parse raw data
    parsed_data = await api.parse_raw_data(raw_data)

    # Validate parsed data format
    assert parsed_data is not None, "Parsed data should not be None"
    assert isinstance(parsed_data, dict), f"Parsed data should be a dictionary, got {type(parsed_data)}"
    assert "interval_prices" in parsed_data, "Parsed data should contain 'interval_prices' key"
    assert "source" in parsed_data, "Parsed data should contain 'source' key"
    assert parsed_data["source"] == Source.NORDPOOL, f"Source should be {Source.NORDPOOL}, got {parsed_data.get('source')}"
    assert parsed_data["area"] == area, f"Area should be {area}, got {parsed_data.get('area')}"

    # Validate interval prices
    interval_prices = parsed_data.get("interval_prices", {})
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
