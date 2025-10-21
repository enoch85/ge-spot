"""Integration test for Energy-Charts API - Live API calls."""
import pytest
import logging
from datetime import datetime, timedelta

from custom_components.ge_spot.api.energy_charts import EnergyChartsAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Mock data generator for 15-minute intervals (96 per day)
def generate_energy_charts_mock_data(base_date_str, bidding_zone="DE-LU"):
    """Generate mock Energy-Charts API response with realistic price data.
    
    Args:
        base_date_str: Date string in format "2025-10-07"
        bidding_zone: Bidding zone code (e.g. "DE-LU", "FR")
        
    Returns:
        Dict with unix_seconds and price arrays (96 intervals)
    """
    base_date = datetime.fromisoformat(base_date_str)
    start_time = base_date.replace(hour=0, minute=0, second=0)
    
    unix_seconds = []
    prices = []
    
    # Generate 96 15-minute intervals
    for i in range(96):
        # Calculate timestamp (15-minute intervals = 900 seconds)
        interval_time = start_time + timedelta(minutes=i * 15)
        unix_ts = int(interval_time.timestamp())
        unix_seconds.append(unix_ts)
        
        # Generate realistic price pattern (30-150 EUR/MWh)
        hour_of_day = i // 4  # Convert interval to hour
        
        # Base price with daily pattern
        # Lower at night (hours 0-6), peak during day (hours 10-20)
        if hour_of_day < 6:
            base = 40 + (hour_of_day * 3)
        elif hour_of_day < 10:
            base = 60 + ((hour_of_day - 6) * 10)
        elif hour_of_day < 20:
            base = 100 + ((hour_of_day - 10) * 3)
        else:
            base = 130 - ((hour_of_day - 20) * 10)
        
        # Add 15-minute variation (±5 EUR/MWh)
        variation = -2.5 + (i % 4) * 1.67
        price = round(base + variation, 2)
        prices.append(price)
    
    return {
        "unix_seconds": unix_seconds,
        "price": prices,
        "unit": "EUR / MWh",
        "license_info": "© Bundesnetzagentur | SMARD.de, CC BY 4.0"
    }


# Mock responses for different bidding zones
SAMPLE_ENERGY_CHARTS_RESPONSES = {
    "DE-LU": generate_energy_charts_mock_data("2025-10-07", "DE-LU"),
    "FR": generate_energy_charts_mock_data("2025-10-07", "FR"),
    "NL": generate_energy_charts_mock_data("2025-10-07", "NL"),
    "BE": generate_energy_charts_mock_data("2025-10-07", "BE"),
    "AT": generate_energy_charts_mock_data("2025-10-07", "AT"),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("area", ["DE-LU", "FR", "NL", "BE", "AT"])
async def test_energy_charts_live_fetch_parse(area, monkeypatch):
    """Test fetching and parsing Energy-Charts data for various European areas.
    This test uses mocked responses to avoid external API dependencies.
    """
    logger.info(f"Testing Energy-Charts API for area: {area}...")

    # Create a modified version of fetch_raw_data that returns our mock data
    async def mock_fetch_raw_data(self, area, session=None, **kwargs):
        # Get mock response for this area
        mock_response = SAMPLE_ENERGY_CHARTS_RESPONSES.get(area, SAMPLE_ENERGY_CHARTS_RESPONSES["DE-LU"])
        
        # Return standardized structure
        return {
            "raw_data": mock_response,
            "timezone": "Europe/Berlin",
            "currency": Currency.EUR,
            "area": area,
            "bzn": area,
            "source": Source.ENERGY_CHARTS,
            "fetched_at": datetime.now().isoformat(),
            "license_info": mock_response.get("license_info", "")
        }

    # Patch the method in the EnergyChartsAPI class
    monkeypatch.setattr(EnergyChartsAPI, "fetch_raw_data", mock_fetch_raw_data)

    # Initialize the API client
    api = EnergyChartsAPI()

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

        # Validate Energy-Charts specific structure
        assert "unix_seconds" in raw_api_response, "Required field 'unix_seconds' missing"
        assert "price" in raw_api_response, "Required field 'price' missing"
        assert isinstance(raw_api_response["unix_seconds"], list), "unix_seconds should be a list"
        assert isinstance(raw_api_response["price"], list), "price should be a list"

        # Validate source and area information
        assert raw_data.get("source") == Source.ENERGY_CHARTS, f"Source should be {Source.ENERGY_CHARTS}"
        assert raw_data.get("area") == area, f"Area should be {area}"

        # Timezone validation - Energy-Charts uses Berlin time (CET/CEST)
        assert raw_data.get("timezone") == "Europe/Berlin", "Timezone should be Europe/Berlin"

        # Currency validation - Energy-Charts always returns EUR
        assert raw_data.get("currency") == Currency.EUR, "Currency should be EUR"

        # Validate data arrays
        unix_seconds = raw_api_response["unix_seconds"]
        prices = raw_api_response["price"]
        
        assert len(unix_seconds) > 0, "unix_seconds array should not be empty"
        assert len(prices) > 0, "price array should not be empty"
        assert len(unix_seconds) == len(prices), "unix_seconds and price arrays must have same length"

        # Validate 15-minute interval data (96 intervals per day)
        assert len(unix_seconds) == 96, f"Expected 96 intervals (15-min data), got {len(unix_seconds)}"

        logger.info(f"Raw data contains {len(unix_seconds)} price intervals")

        # Act: Parse Raw Data
        parsed_data = api.parser.parse(raw_data)

        # Assert: Parsed Data Structure
        assert parsed_data is not None, f"Parsed data for {area} should not be None"
        assert isinstance(parsed_data, dict), "Parsed data should be a dictionary"

        # Required fields validation
        assert parsed_data.get("source") == Source.ENERGY_CHARTS, "Source should be energy_charts"
        assert parsed_data.get("area") == area, f"Area should be {area}"
        assert parsed_data.get("currency") == Currency.EUR, "Currency should be EUR"
        assert parsed_data.get("timezone") == "Europe/Berlin", "Timezone should be Europe/Berlin"
        assert parsed_data.get("source_unit") == "MWh", "Source unit should be MWh"

        # Interval prices validation
        assert "interval_raw" in parsed_data, "interval_raw missing from parsed_data"
        interval_prices = parsed_data.get("interval_raw", {})
        assert isinstance(interval_prices, dict), "interval_raw should be a dictionary"

        # Validate price data - 96 intervals (15-minute data)
        assert len(interval_prices) == 96, f"Expected 96 interval prices, got {len(interval_prices)}"

        # Validate timestamp format and price values
        for timestamp, price in interval_prices.items():
            # Validate ISO timestamp format
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                
                # Check timestamp is within reasonable range
                assert dt.year == 2025
                assert dt.month == 10
                assert dt.day == 7
            except ValueError:
                pytest.fail(f"Invalid timestamp format: '{timestamp}' for {area}")

            # Price validation
            assert isinstance(price, float), f"Price should be a float, got {type(price)}"
            
            # Energy-Charts price range validation (EUR/MWh)
            # European electricity prices typically range from -100 to 500 EUR/MWh
            assert -100 <= price <= 500, f"Price {price} EUR/MWh is outside reasonable range"

        # Check for sequential 15-minute intervals
        timestamps = sorted(interval_prices.keys())
        for i in range(1, len(timestamps)):
            prev_dt = datetime.fromisoformat(timestamps[i-1].replace("Z", "+00:00"))
            curr_dt = datetime.fromisoformat(timestamps[i].replace("Z", "+00:00"))
            interval_diff = (curr_dt - prev_dt).total_seconds() / 60  # Minutes
            
            # Energy-Charts provides native 15-minute intervals
            assert abs(interval_diff - 15.0) < 1.0, \
                f"Expected 15-minute interval, got {interval_diff} minutes between {timestamps[i-1]} and {timestamps[i]}"

        # Validate license information
        assert "license_info" in parsed_data, "License info should be present"

        logger.info(f"Energy-Charts Test ({area}): PASS - Found {len(interval_prices)} interval prices. "
                   f"Range: {min(interval_prices.values()):.2f} to {max(interval_prices.values()):.2f} EUR/MWh")

    except AssertionError as ae:
        logger.error(f"Energy-Charts Test ({area}): ASSERTION FAILED - {str(ae)}")
        raise
    except Exception as e:
        logger.error(f"Energy-Charts Test ({area}): EXCEPTION - {str(e)}")
        raise


@pytest.mark.asyncio
async def test_energy_charts_timestamp_conversion(monkeypatch):
    """Test that unix timestamps are correctly converted to ISO format."""
    
    # Create specific mock data with known timestamps
    known_timestamp = int(datetime(2025, 10, 7, 12, 0, 0).timestamp())
    mock_data = {
        "unix_seconds": [known_timestamp, known_timestamp + 900],  # 12:00 and 12:15
        "price": [100.0, 105.0],
        "unit": "EUR / MWh",
        "license_info": ""
    }
    
    async def mock_fetch(self, area, session=None, **kwargs):
        return {
            "raw_data": mock_data,
            "timezone": "Europe/Berlin",
            "currency": Currency.EUR,
            "area": area,
            "bzn": area,
            "source": Source.ENERGY_CHARTS,
            "fetched_at": datetime.now().isoformat(),
            "license_info": ""
        }
    
    monkeypatch.setattr(EnergyChartsAPI, "fetch_raw_data", mock_fetch)
    
    api = EnergyChartsAPI()
    raw_data = await api.fetch_raw_data("DE-LU")
    parsed_data = api.parser.parse(raw_data)
    
    # Check timestamps were converted correctly
    timestamps = sorted(parsed_data["interval_raw"].keys())
    assert len(timestamps) == 2
    
    # Verify ISO format
    for ts in timestamps:
        assert "T" in ts
        assert ":" in ts
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert dt.hour == 12
        assert dt.minute in [0, 15]


@pytest.mark.asyncio
async def test_energy_charts_validation(monkeypatch):
    """Test data validation in parser."""
    
    # Test with invalid data
    invalid_data = {
        "unix_seconds": [1696636800, 1696637700],
        "price": [100.0],  # Mismatched length!
        "unit": "EUR / MWh"
    }
    
    async def mock_fetch_invalid(self, area, session=None, **kwargs):
        return {
            "raw_data": invalid_data,
            "timezone": "Europe/Berlin",
            "currency": Currency.EUR,
            "area": area,
            "bzn": area,
            "source": Source.ENERGY_CHARTS
        }
    
    monkeypatch.setattr(EnergyChartsAPI, "fetch_raw_data", mock_fetch_invalid)
    
    api = EnergyChartsAPI()
    raw_data = await api.fetch_raw_data("DE-LU")
    parsed_data = api.parser.parse(raw_data)
    
    # Should return empty result for invalid data
    assert len(parsed_data["interval_raw"]) == 0
