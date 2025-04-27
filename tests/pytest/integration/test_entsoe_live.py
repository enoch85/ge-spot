import pytest
import os
from datetime import datetime, timedelta
import logging

from custom_components.ge_spot.api.entsoe import EntsoeAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.config import Config
from custom_components.ge_spot.const.time import TimeFormat

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mark all tests in this file as live API tests
pytestmark = pytest.mark.liveapi

# Get ENTSO-E token from environment variable
ENTSOE_TOKEN = os.environ.get("ENTSOE_TOKEN")

# Skip all tests in this file if the token is not set
pytestmark = pytest.mark.skipif(not ENTSOE_TOKEN, reason="ENTSOE_TOKEN environment variable not set")

@pytest.fixture
def entsoe_api():
    """Provides an EntsoeAPI instance configured with the token."""
    config = {Config.API_TOKEN: ENTSOE_TOKEN}
    return EntsoeAPI(config=config)

@pytest.mark.asyncio
@pytest.mark.parametrize("area", ["DE-LU", "FR", "ES", "FI"]) # Test a few diverse areas
async def test_entsoe_live_fetch_parse(entsoe_api, area):
    """Tests fetching and parsing live ENTSO-E data for a given area."""
    logger.info(f"Testing ENTSO-E live API for area: {area}...")
    try:
        # Act: Fetch Raw Data
        parsed_data = await entsoe_api.fetch_day_ahead_prices(area=area)

        # Assert: Parsed Data Structure (strict validation)
        assert parsed_data is not None, f"Parsed data for {area} should not be None"
        assert isinstance(parsed_data, dict), f"Parsed data for {area} should be a dictionary"
        assert parsed_data.get("source") == Source.ENTSOE, f"Source should be {Source.ENTSOE}, got {parsed_data.get('source')}"
        assert parsed_data.get("area") == area, f"Area should be {area}, got {parsed_data.get('area')}"
        
        # Stricter validation of required fields
        required_fields = ["currency", "api_timezone", "hourly_prices"]
        for field in required_fields:
            assert field in parsed_data, f"Required field '{field}' missing from parsed data for {area}"
        
        assert isinstance(parsed_data["hourly_prices"], dict), f"hourly_prices should be a dictionary, got {type(parsed_data['hourly_prices'])}"

        # Validate hourly prices content
        hourly_prices = parsed_data["hourly_prices"]
        
        # Check for expected data presence
        assert hourly_prices, f"No hourly prices found for {area} - this is a real issue that should be investigated"
        
        # Validate number of hours - should typically have 24 hours of data at a minimum
        # Don't adapt the test - if there are fewer hours, it's a real issue to investigate
        min_expected_hours = 24
        assert len(hourly_prices) >= min_expected_hours, f"Expected at least {min_expected_hours} hours of data, got {len(hourly_prices)} for {area}"
        
        # Verify all timestamps follow ISO format
        for timestamp, price in hourly_prices.items():
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                # Validate the timestamp is within reasonable range (not too far in past or future)
                now = datetime.now().astimezone()
                three_days_ago = now - timedelta(days=3)
                five_days_ahead = now + timedelta(days=5)
                assert three_days_ago <= dt <= five_days_ahead, f"Timestamp {timestamp} is outside reasonable range for {area}"
            except ValueError:
                pytest.fail(f"Invalid timestamp format: '{timestamp}' for {area}")
            
            # Price validation
            assert isinstance(price, float), f"Price should be a float, got {type(price)} for timestamp {timestamp}"
            assert -1000 <= price <= 5000, f"Price {price} for {timestamp} is outside reasonable range for {area}"
        
        # Verify timestamps are contiguous and hourly
        timestamps = sorted(hourly_prices.keys())
        for i in range(1, len(timestamps)):
            prev_dt = datetime.fromisoformat(timestamps[i-1].replace("Z", "+00:00"))
            curr_dt = datetime.fromisoformat(timestamps[i].replace("Z", "+00:00"))
            hour_diff = (curr_dt - prev_dt).total_seconds() / 3600
            assert abs(hour_diff - 1.0) < 0.1, f"Non-hourly gap between {timestamps[i-1]} and {timestamps[i]} for {area}"
        
        # Validate currency is appropriate for the area
        currency = parsed_data["currency"]
        # Real-world validation: ENTSO-E should return EUR for European countries
        assert currency in ["EUR"], f"Expected currency EUR for {area}, got {currency}"
        
        logger.info(f"ENTSO-E Live Test ({area}): PASS - Found {len(hourly_prices)} prices. Range: {min(hourly_prices.values()):.2f} to {max(hourly_prices.values()):.2f} {currency}")

    except AssertionError as ae:
        # Let assertion errors propagate - these are test failures that should be fixed in the code, not the test
        logger.error(f"ENTSO-E Live Test ({area}): ASSERTION FAILED - {str(ae)}")
        raise
    except Exception as e:
        logger.error(f"ENTSO-E Live Test ({area}): EXCEPTION - {str(e)}")
        # Don't catch the exception - let the test fail so we fix the real issue
        raise
    finally:
        # Close session if created internally
        if hasattr(entsoe_api, 'session') and entsoe_api.session:
             await entsoe_api.session.close()