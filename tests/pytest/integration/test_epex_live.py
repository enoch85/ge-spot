import pytest
import logging
from datetime import datetime, timedelta

from custom_components.ge_spot.api.epex import EpexAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mark all tests in this file as live API tests
pytestmark = pytest.mark.liveapi

@pytest.mark.asyncio
@pytest.mark.parametrize("area", ["FR", "DE-LU"]) # EPEX covers FR, DE-LU, AT, BE, CH, GB, NL
async def test_epex_live_fetch_parse(area):
    """Tests fetching and parsing live EPEX data for a given area.
    This test makes actual API calls and verifies real responses.
    If it fails, investigate and fix the core code rather than modifying the test.
    """
    logger.info(f"Testing EPEX Spot live API for area: {area}...")
    # Arrange
    api = EpexAPI()

    try:
        # Act: Fetch Raw Data - don't catch exceptions, let test fail to expose real issues
        raw_data = await api.fetch_raw_data(area=area)

        # Assert: Raw Data Structure (Strict validation)
        assert raw_data is not None, f"Raw data for {area} should not be None"
        assert isinstance(raw_data, list), f"EPEX raw data should be a list, got {type(raw_data)}"

        # Real-world validation: EPEX should return data entries
        assert len(raw_data) > 0, f"EPEX should return data entries for {area}, got empty list"

        # Log raw data structure for debugging
        logger.info(f"Raw data for {area} contains {len(raw_data)} entries")

        # Act: Parse Raw Data
        parsed_data = await api.parse_raw_data(raw_data)

        # Assert: Parsed Data Structure (Strict validation)
        assert parsed_data is not None, f"Parsed data for {area} should not be None"
        assert isinstance(parsed_data, dict), f"Parsed data should be a dictionary, got {type(parsed_data)}"

        # Required fields validation
        assert parsed_data.get("source") == Source.EPEX, f"Source should be {Source.EPEX}, got {parsed_data.get('source')}"
        assert parsed_data.get("area") == area, f"Area should be {area}, got {parsed_data.get('area')}"

        # Currency validation - EPEX uses EUR for European markets
        assert parsed_data.get("currency") == Currency.EUR, f"Currency should be {Currency.EUR}, got {parsed_data.get('currency')}"

        # Timezone validation
        assert "api_timezone" in parsed_data, "api_timezone missing from parsed data"
        assert parsed_data.get("api_timezone"), f"api_timezone should have a value, got {parsed_data.get('api_timezone')}"

        # Interval prices validation (15-minute intervals)
        assert "interval_raw" in parsed_data, "interval_raw missing from parsed data"
        assert isinstance(parsed_data["interval_raw"], dict), f"interval_raw should be a dictionary, got {type(parsed_data.get('interval_raw'))}"

        # Validate interval prices - real data should be available
        interval_prices = parsed_data["interval_raw"]
        assert interval_prices, f"No interval prices found for {area} - this indicates a real issue with the API or parser"

        # Real-world validation: EPEX provides 15-minute intervals (96 per day)
        min_expected_intervals = 50  # At minimum, should have partial day data
        assert len(interval_prices) >= min_expected_intervals, f"Expected at least {min_expected_intervals} interval entries, got {len(interval_prices)}"

        # Validate timestamp format and price values
        for timestamp, price in interval_prices.items():
            # Validate timestamp format
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

                # Check timestamp is within reasonable range (not too old/future)
                now = datetime.now().astimezone()
                five_days_ago = now - timedelta(days=5)
                three_days_ahead = now + timedelta(days=3)
                assert five_days_ago <= dt <= three_days_ahead, f"Timestamp {timestamp} is outside reasonable range for {area}"
            except ValueError:
                pytest.fail(f"Invalid timestamp format: '{timestamp}' for {area}")

            # Price validation
            assert isinstance(price, float), f"Price should be a float, got {type(price)} for timestamp {timestamp}"

            # Real-world price range validation - EPEX prices can range widely but should be within reason
            # Historical EPEX price range is approximately -500 to 3000 EUR/MWh in extreme events
            assert -1000 <= price <= 5000, f"Price {price} for {timestamp} is outside reasonable range for {area}"

        # Check for sequential 15-minute intervals
        timestamps = sorted(interval_prices.keys())
        for i in range(1, min(97, len(timestamps))):  # Check first 96 intervals (1 day)
            prev_dt = datetime.fromisoformat(timestamps[i-1].replace("Z", "+00:00"))
            curr_dt = datetime.fromisoformat(timestamps[i].replace("Z", "+00:00"))
            interval_diff = (curr_dt - prev_dt).total_seconds() / 60  # Minutes

            # EPEX provides 15-minute intervals
            valid_interval = abs(interval_diff - 15.0) < 1.0  # Within 1 minute of 15 minutes
            assert valid_interval, f"Unexpected time gap between {timestamps[i-1]} and {timestamps[i]} for {area}: {interval_diff} minutes (expected 15)"

        logger.info(f"EPEX Live Test ({area}): PASS - Found {len(interval_prices)} interval prices. "
                 f"Range: {min(interval_prices.values()):.2f} to {max(interval_prices.values()):.2f} {parsed_data.get('currency')}")

    except AssertionError as ae:
        # Let assertion errors propagate - these are test failures that should be fixed in the code, not the test
        logger.error(f"EPEX Live Test ({area}): ASSERTION FAILED - {str(ae)}")
        raise
    except Exception as e:
        # Don't catch exceptions - let the test fail to expose real issues
        logger.error(f"EPEX Live Test ({area}): EXCEPTION - {str(e)}")
        raise
    finally:
        if hasattr(api, 'session') and api.session:
             await api.session.close()