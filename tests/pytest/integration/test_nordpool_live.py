import pytest
import logging
import respx
from datetime import datetime, timedelta

from custom_components.ge_spot.api.nordpool import NordpoolAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_15min_intervals(base_date_str, base_prices, area_code):
    """Generate 96 15-minute intervals from 24 hourly base prices.
    
    Args:
        base_date_str: Date string in format "2025-04-27"
        base_prices: List of 24 hourly prices to interpolate
        area_code: Area code (e.g., "SE3", "FI")
    
    Returns:
        List of 96 interval entries with 15-minute granularity
    """
    entries = []
    # Start from 22:00 UTC on the day before (midnight CET)
    base_date = datetime.fromisoformat(base_date_str)
    start_time = base_date.replace(hour=22, minute=0, second=0) - timedelta(days=1)
    
    for hour_idx in range(24):
        base_price = base_prices[hour_idx]
        # Create 4 intervals per hour with slight price variations
        for quarter in range(4):
            interval_start = start_time + timedelta(hours=hour_idx, minutes=quarter * 15)
            interval_end = interval_start + timedelta(minutes=15)
            
            # Add small realistic variation (±2%) to each 15-min interval
            price_variation = base_price * (0.98 + 0.04 * (quarter / 4.0))
            
            entries.append({
                "deliveryStart": interval_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "deliveryEnd": interval_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "entryPerArea": {area_code: round(price_variation, 2)}
            })
    
    return entries


# Base hourly prices for interpolation into 15-minute intervals
BASE_PRICES_SE3 = [34.61, 32.82, 31.15, 31.36, 30.98, 31.91, 35.22, 32.70, 20.65, 1.41, 
                   -1.12, -3.86, -9.40, -14.63, -16.60, -8.14, -0.15, 5.46, 33.82, 42.45, 
                   53.20, 56.33, 33.63, 32.43]

BASE_PRICES_FI = [36.61, 34.82, 33.15, 33.36, 32.98, 33.91, 37.22, 34.70, 22.65, 3.41,
                  0.88, -1.86, -7.40, -12.63, -14.60, -6.14, 1.85, 7.46, 35.82, 44.45,
                  55.20, 58.33, 35.63, 34.43]

BASE_PRICES_NO1 = [30.61, 28.82, 27.15, 27.36, 26.98, 27.91, 31.22, 28.70, 16.65, -2.59,
                   -5.12, -7.86, -13.40, -18.63, -20.60, -12.14, -4.15, 1.46, 29.82, 38.45,
                   49.20, 52.33, 29.63, 28.43]

BASE_PRICES_DK1 = [32.61, 30.82, 29.15, 29.36, 28.98, 29.91, 33.22, 30.70, 18.65, -0.59,
                   -3.12, -5.86, -11.40, -16.63, -18.60, -10.14, -2.15, 3.46, 31.82, 40.45,
                   51.20, 54.33, 31.63, 30.43]

# Generate 15-minute interval mock data (96 intervals per day)
# Using October 2025 dates to match current test date context
SAMPLE_NORDPOOL_RESPONSES = {
    "SE3": {
        "deliveryDateCET": "2025-10-02",
        "version": 2,
        "updatedAt": "2025-10-01T10:55:58.9728151Z",
        "deliveryAreas": ["SE3"],
        "market": "DayAhead",
        "multiAreaEntries": generate_15min_intervals("2025-10-02", BASE_PRICES_SE3, "SE3"),
        "currency": "EUR",
        "exchangeRate": 1,
        "areaStates": [{"state": "Final", "areas": ["SE3"]}],
        "areaAverages": [{"areaCode": "SE3", "price": 20.26}]
    },
    "FI": {
        "deliveryDateCET": "2025-10-02",
        "version": 2,
        "updatedAt": "2025-10-01T10:55:58.9728151Z",
        "deliveryAreas": ["FI"],
        "market": "DayAhead",
        "multiAreaEntries": generate_15min_intervals("2025-10-02", BASE_PRICES_FI, "FI"),
        "currency": "EUR",
        "exchangeRate": 1,
        "areaStates": [{"state": "Final", "areas": ["FI"]}],
        "areaAverages": [{"areaCode": "FI", "price": 21.26}]
    },
    "NO1": {
        "deliveryDateCET": "2025-10-02",
        "version": 2,
        "updatedAt": "2025-10-01T10:55:58.9728151Z",
        "deliveryAreas": ["NO1"],
        "market": "DayAhead",
        "multiAreaEntries": generate_15min_intervals("2025-10-02", BASE_PRICES_NO1, "NO1"),
        "currency": "EUR",
        "exchangeRate": 1,
        "areaStates": [{"state": "Final", "areas": ["NO1"]}],
        "areaAverages": [{"areaCode": "NO1", "price": 15.26}]
    },
    "DK1": {
        "deliveryDateCET": "2025-10-02",
        "version": 2,
        "updatedAt": "2025-10-01T10:55:58.9728151Z",
        "deliveryAreas": ["DK1"],
        "market": "DayAhead",
        "multiAreaEntries": generate_15min_intervals("2025-10-02", BASE_PRICES_DK1, "DK1"),
        "currency": "EUR",
        "exchangeRate": 1,
        "areaStates": [{"state": "Final", "areas": ["DK1"]}],
        "areaAverages": [{"areaCode": "DK1", "price": 18.26}]
    }
}

# Tomorrow's data (also with 96 15-minute intervals)
BASE_PRICES_TOMORROW = [28.65, 27.36, 26.98, 27.91, 30.22, 31.70, 35.65, 40.41, 41.12, 40.86,
                        39.40, 38.63, 36.60, 35.14, 34.15, 35.46, 43.82, 48.45, 50.20, 47.33,
                        43.63, 40.43, 38.21, 36.82]

SAMPLE_NORDPOOL_TOMORROW_RESPONSES = {
    "SE3": {
        "deliveryDateCET": "2025-10-03",
        "version": 2,
        "updatedAt": "2025-10-02T13:10:22.1234567Z",
        "deliveryAreas": ["SE3"],
        "market": "DayAhead",
        "multiAreaEntries": generate_15min_intervals("2025-10-03", BASE_PRICES_TOMORROW, "SE3"),
        "currency": "EUR",
        "exchangeRate": 1,
        "areaStates": [{"state": "Final", "areas": ["SE3"]}],
        "areaAverages": [{"areaCode": "SE3", "price": 36.71}]
    }
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
@pytest.mark.parametrize("area", ["FI", "SE3", "NO1", "DK1"])  # Test key Nordic market areas
async def test_nordpool_live_fetch_parse(area, monkeypatch):
    """Tests fetching and parsing Nordpool data for various Nordic areas.
    This test uses mocked responses injected directly into the API client.
    """
    logger.info(f"Testing Nordpool API for area: {area}...")
    
    # Create a modified version of fetch_raw_data that returns our mock data
    async def mock_fetch_raw_data(self, area, **kwargs):
        # Create a mock response structure matching what the real API returns
        response = {
            "raw_data": {
                "today": SAMPLE_NORDPOOL_RESPONSES.get(area, SAMPLE_NORDPOOL_RESPONSES["SE3"]),
                "tomorrow": SAMPLE_NORDPOOL_TOMORROW_RESPONSES.get("SE3"),  # Use SE3 as default
            },
            "timezone": "Europe/Oslo",  # Nordpool uses Central European Time
            "currency": "EUR",
            "area": area,
            "source": Source.NORDPOOL,
            "fetched_at": datetime.now().isoformat(),
        }
        return response
    
    # Patch the method in the NordpoolAPI class
    monkeypatch.setattr(NordpoolAPI, "fetch_raw_data", mock_fetch_raw_data)
    
    # Patch the exchange rate service to avoid real external calls
    async def mock_get_rates(self, force_refresh=False):
        return MOCK_EXCHANGE_RATES
    
    async def mock_convert(self, amount, from_currency, to_currency):
        # Simple conversion using our mocked rates
        if from_currency == to_currency:
            return amount
        
        from_rate = MOCK_EXCHANGE_RATES["rates"].get(from_currency, 1.0)
        to_rate = MOCK_EXCHANGE_RATES["rates"].get(to_currency, 1.0)
        
        # Convert to base currency then to target
        return amount * (to_rate / from_rate)
    
    monkeypatch.setattr(ExchangeRateService, "get_rates", mock_get_rates)
    monkeypatch.setattr(ExchangeRateService, "convert", mock_convert)
    
    # Initialize the API client
    api = NordpoolAPI()

    try:
        # Act: Fetch Raw Data - using mocked responses
        raw_data = await api.fetch_raw_data(area=area)
        
        # Assert: Raw Data Structure (strict validation)
        assert raw_data is not None, f"Raw data for {area} should not be None"
        assert isinstance(raw_data, dict), f"Raw data should be a dictionary, got {type(raw_data)}"
        
        # Validate wrapper structure
        assert "raw_data" in raw_data, "Required field 'raw_data' missing from response"
        raw_api_response = raw_data.get("raw_data")
        assert isinstance(raw_api_response, dict), f"raw_data should be a dictionary, got {type(raw_api_response)}"
        
        # Validate Nordpool-specific structure within raw_data
        assert "today" in raw_api_response, "Required field 'today' missing from raw_data"
        assert isinstance(raw_api_response.get("today"), dict), f"today should be a dictionary, got {type(raw_api_response.get('today'))}"
        
        # Validate source and area information
        assert raw_data.get("source") == Source.NORDPOOL, f"Source should be {Source.NORDPOOL}, got {raw_data.get('source')}"
        assert raw_data.get("area") == area, f"Area should be {area}, got {raw_data.get('area')}"
        
        # Timezone validation - Nordpool uses Oslo time
        assert raw_data.get("timezone") == "Europe/Oslo", f"Timezone should be Europe/Oslo, got {raw_data.get('timezone')}"
        
        # Validate today data structure
        today_data = raw_api_response.get("today", {})
        assert "multiAreaEntries" in today_data, "multiAreaEntries missing from today data"
        assert isinstance(today_data.get("multiAreaEntries"), list), f"multiAreaEntries should be a list, got {type(today_data.get('multiAreaEntries'))}"
        
        # Real-world validation: Nordpool should return price entries
        multi_area_entries = today_data.get("multiAreaEntries", [])
        assert len(multi_area_entries) > 0, f"No multiAreaEntries found for {area} - this indicates a real issue with the API"
        
        # Validate first entry structure
        if multi_area_entries:
            first_entry = multi_area_entries[0]
            assert isinstance(first_entry, dict), f"Entry should be a dictionary, got {type(first_entry)}"
            assert "deliveryStart" in first_entry, "Required field 'deliveryStart' missing from entry"
            assert "entryPerArea" in first_entry, "Required field 'entryPerArea' missing from entry"
            
            # Check if area is in entryPerArea (it should be if query is valid)
            entry_per_area = first_entry.get("entryPerArea", {})
            assert area in entry_per_area, f"Area {area} not found in entryPerArea"
        
        logger.info(f"Raw data contains {len(multi_area_entries)} price entries")
        
        # Act: Parse Raw Data using the modern parser architecture
        # The API returns a wrapper with 'raw_data', but parser expects the wrapper format
        parsed_data = api.parser.parse(raw_data)        # Assert: Parsed Data Structure (strict validation)
        assert parsed_data is not None, f"Parsed data for {area} should not be None"
        assert isinstance(parsed_data, dict), f"Parsed data should be a dictionary, got {type(parsed_data)}"
        
        # Required fields validation
        assert parsed_data.get("source") == Source.NORDPOOL, f"Source should be {Source.NORDPOOL}, got {parsed_data.get('source')}"
        assert parsed_data.get("area") == area, f"Area should be {area}, got {parsed_data.get('area')}"
        
        # Currency validation - Nordpool typically uses EUR for Nordic markets
        assert parsed_data.get("currency") == Currency.EUR, f"Currency should be {Currency.EUR}, got {parsed_data.get('currency')}"
        
        # Timezone validation
        assert parsed_data.get("timezone") == "Europe/Oslo", f"Timezone should be Europe/Oslo, got {parsed_data.get('timezone')}"
        
        # Interval prices validation (15-minute intervals from realistic mock data)
        assert "interval_raw" in parsed_data, "interval_raw missing from parsed_data"
        interval_prices = parsed_data.get("interval_raw", {})
        assert isinstance(interval_prices, dict), f"interval_raw should be a dictionary, got {type(interval_prices)}"
        
        # Validate price data - should have 96 intervals per day (15-min intervals)
        # Account for today+tomorrow (192 intervals) and potential partial data
        min_expected = 80  # At least 80 intervals (partial day)
        max_expected = 200  # Up to 200 intervals (2 days + buffer)
        assert min_expected <= len(interval_prices) <= max_expected, f"Expected {min_expected}-{max_expected} interval prices (15-minute data), got {len(interval_prices)}"
        
        # Validate timestamp format and price values
        for timestamp, price in interval_prices.items():
            # Validate timestamp format
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                
                # Check timestamp is within reasonable range (not too old/future)
                now = datetime.now().astimezone()
                yesterday = now - timedelta(days=2)  # More flexible
                tomorrow = now + timedelta(days=5)  # More flexible
                assert yesterday <= dt <= tomorrow, f"Timestamp {timestamp} is outside reasonable range for {area}"
            except ValueError:
                pytest.fail(f"Invalid timestamp format: '{timestamp}' for {area}")
            
            # Price validation
            assert isinstance(price, float), f"Price should be a float, got {type(price)} for timestamp {timestamp}"
            
            # Real-world price range validation for Nordic electricity market
            # Nordic prices typically range from negative values to several hundred EUR/MWh
            assert -500 <= price <= 3000, f"Price {price} EUR/MWh for {timestamp} is outside reasonable range for {area}"
        
        # Check for sequential 15-minute intervals
        timestamps = sorted(interval_prices.keys())
        interval_diffs = []
        for i in range(1, min(97, len(timestamps))):  # Check first 96 intervals (1 day of 15-min data)
            prev_dt = datetime.fromisoformat(timestamps[i-1].replace("Z", "+00:00"))
            curr_dt = datetime.fromisoformat(timestamps[i].replace("Z", "+00:00"))
            interval_diff = (curr_dt - prev_dt).total_seconds() / 60  # Minutes
            interval_diffs.append(interval_diff)
            
            # NordPool now provides 15-minute intervals
            valid_interval = abs(interval_diff - 15.0) < 1.0  # Within 1 minute of 15 minutes
            assert valid_interval, f"Unexpected time gap between {timestamps[i-1]} and {timestamps[i]} for {area}: {interval_diff} minutes (expected 15)"
        
        logger.info(f"Nordpool Test ({area}): PASS - Found {len(interval_prices)} interval prices. "
                  f"Range: {min(interval_prices.values()):.2f} to {max(interval_prices.values()):.2f} {parsed_data.get('currency')}/MWh")

    except AssertionError as ae:
        # Let assertion errors propagate - these are test failures that should be fixed in the code, not the test
        logger.error(f"Nordpool Test ({area}): ASSERTION FAILED - {str(ae)}")
        raise
    except Exception as e:
        # Don't catch exceptions - let the test fail to expose real issues
        logger.error(f"Nordpool Test ({area}): EXCEPTION - {str(e)}")
        raise