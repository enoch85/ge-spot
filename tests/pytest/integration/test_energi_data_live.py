import pytest
import logging
from datetime import datetime, timedelta

from custom_components.ge_spot.api.energi_data import EnergiDataAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mark all tests in this file as live API tests
pytestmark = pytest.mark.liveapi

@pytest.mark.asyncio
@pytest.mark.parametrize("area", ["DK1", "DK2"]) # Energi Data Service is for Denmark
async def test_energi_data_live_fetch_parse(area):
    """Tests fetching and parsing live Energi Data Service data for a given area.
    This test makes actual API calls and verifies real responses.
    If it fails, investigate and fix the core code rather than modifying the test.
    """
    logger.info(f"Testing Energi Data Service live API for area: {area}...")
    # Arrange - allow failures during setup to find real issues
    api = EnergiDataAPI()

    try:
        # Act: Fetch Raw Data - no exception handling to expose real issues
        raw_data = await api.fetch_raw_data(area=area)
        
        # Assert: Raw Data Structure (strict validation)
        assert raw_data is not None, f"Raw data for {area} should not be None"
        assert isinstance(raw_data, dict), f"Raw data should be a dictionary, got {type(raw_data)}"
        
        # Validate API-specific structure
        assert "records" in raw_data, "Required field 'records' missing from raw data"
        assert isinstance(raw_data["records"], list), f"records should be a list, got {type(raw_data.get('records'))}"
        
        # Real-world validation: Energi Data Service should return data records
        assert len(raw_data["records"]) > 0, f"No records returned from Energi Data Service API for {area} - this indicates a real issue"
        
        # Validate structure of first record to ensure it has the expected fields
        if raw_data["records"]:
            first_record = raw_data["records"][0]
            assert isinstance(first_record, dict), f"Record should be a dictionary, got {type(first_record)}"
            
            # Check for required fields based on known Energi Data Service API structure
            # These fields must be present for correct parsing
            required_record_fields = ["HourDK", "SpotPriceDKK"]
            for field in required_record_fields:
                assert field in first_record, f"Required field '{field}' missing from record"
        
        logger.info(f"Raw data contains {len(raw_data['records'])} records")

        # Act: Parse Raw Data
        parsed_data = await api.parse_raw_data(raw_data)
        
        # Assert: Parsed Data Structure (strict validation)
        assert parsed_data is not None, f"Parsed data for {area} should not be None"
        assert isinstance(parsed_data, dict), f"Parsed data should be a dictionary, got {type(parsed_data)}"
        
        # Required fields validation
        assert parsed_data.get("source") == Source.ENERGI_DATA_SERVICE, f"Source should be {Source.ENERGI_DATA_SERVICE}, got {parsed_data.get('source')}"
        assert parsed_data.get("area") == area, f"Area should be {area}, got {parsed_data.get('area')}"
        
        # Currency validation - Energi Data Service uses DKK for Danish markets
        assert parsed_data.get("currency") == Currency.DKK, f"Currency should be {Currency.DKK}, got {parsed_data.get('currency')}"
        
        # Timezone validation
        api_timezone = parsed_data.get("api_timezone")
        assert api_timezone is not None and api_timezone, f"api_timezone should have a value, got {api_timezone}"
        # Danish timezone should be Europe/Copenhagen or CET/CEST
        assert "Europe" in api_timezone or "CET" in api_timezone or "UTC" in api_timezone, f"Expected European timezone, got {api_timezone}"
        
        # Hourly prices validation
        assert "hourly_prices" in parsed_data, "hourly_prices missing from parsed data"
        hourly_prices = parsed_data["hourly_prices"]
        assert isinstance(hourly_prices, dict), f"hourly_prices should be a dictionary, got {type(hourly_prices)}"
        
        # Real-world validation: Energi Data Service should return price data
        assert hourly_prices, f"No hourly prices found for {area} - this indicates a real issue with the API or parser"
        
        # Real-world validation: Energi Data Service typically provides at least 24 hours of data
        min_expected_hours = 12  # At minimum, should have half a day of data
        assert len(hourly_prices) >= min_expected_hours, f"Expected at least {min_expected_hours} hourly prices, got {len(hourly_prices)}"
        
        # Validate timestamp format and price values
        for timestamp, price in hourly_prices.items():
            # Validate timestamp format
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                
                # Check timestamp is within reasonable range (not too old/future)
                now = datetime.now().astimezone()
                seven_days_ago = now - timedelta(days=7)  # Energi Data Service can provide historical data
                three_days_ahead = now + timedelta(days=3)  # And some future data (day-ahead market)
                assert seven_days_ago <= dt <= three_days_ahead, f"Timestamp {timestamp} is outside reasonable range for {area}"
            except ValueError:
                pytest.fail(f"Invalid timestamp format: '{timestamp}' for {area}")
            
            # Price validation
            assert isinstance(price, float), f"Price should be a float, got {type(price)} for timestamp {timestamp}"
            
            # Real-world price range validation for Danish electricity market
            # Danish prices typically range from negative values to several hundred DKK/MWh
            # The price range in DKK/MWh is typically between -500 and 3000
            assert -500 <= price <= 5000, f"Price {price} DKK/MWh for {timestamp} is outside reasonable range for {area}"
        
        # Check for sequential hourly timestamps
        timestamps = sorted(hourly_prices.keys())
        for i in range(1, len(timestamps)):
            prev_dt = datetime.fromisoformat(timestamps[i-1].replace("Z", "+00:00"))
            curr_dt = datetime.fromisoformat(timestamps[i].replace("Z", "+00:00"))
            hour_diff = (curr_dt - prev_dt).total_seconds() / 3600
            
            # Danish market data should be hourly
            assert abs(hour_diff - 1.0) < 0.1, f"Non-hourly gap between {timestamps[i-1]} and {timestamps[i]} for {area}: {hour_diff} hours"
        
        logger.info(f"Energi Data Service Live Test ({area}): PASS - Found {len(hourly_prices)} prices. "
                  f"Range: {min(hourly_prices.values()):.2f} to {max(hourly_prices.values()):.2f} {parsed_data.get('currency')}/MWh")

    except AssertionError as ae:
        # Let assertion errors propagate - these are test failures that should be fixed in the code, not the test
        logger.error(f"Energi Data Service Live Test ({area}): ASSERTION FAILED - {str(ae)}")
        raise
    except Exception as e:
        # Don't catch exceptions - let the test fail to expose real issues
        logger.error(f"Energi Data Service Live Test ({area}): EXCEPTION - {str(e)}")
        raise
    finally:
        if hasattr(api, 'session') and api.session:
             await api.session.close()