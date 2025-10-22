import pytest
import os
import logging
from datetime import datetime, timedelta

from custom_components.ge_spot.api.amber import AmberAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mark all tests in this file as live API tests
pytestmark = pytest.mark.liveapi

# Amber requires an API key, skip if not available in environment
skip_reason = "AMBER_API_KEY environment variable not set"


@pytest.mark.skipif(not os.environ.get("AMBER_API_KEY"), reason=skip_reason)
@pytest.mark.asyncio
async def test_amber_live_fetch_parse():
    """Tests fetching and parsing live Amber data for the Australian market.
    This test makes actual API calls to verify real responses.
    If it fails, investigate and fix the core code rather than modifying the test.
    """
    logger.info("Testing Amber live API...")
    # Arrange - don't catch exceptions during setup
    api = AmberAPI()

    try:
        # Act: Fetch Raw Data - let exceptions propagate to find real issues
        raw_data = await api.fetch_raw_data()

        # Assert: Raw Data Structure (strict validation)
        assert raw_data is not None, "Raw data should not be None"
        assert isinstance(
            raw_data, list
        ), f"Raw data should be a list, got {type(raw_data)}"

        # Real-world validation: Amber should return data points
        assert (
            len(raw_data) > 0
        ), "No data returned from Amber API - this indicates a real issue"

        # Validate structure of raw data items (these fields must be present for correct parsing)
        first_item = raw_data[0]
        assert isinstance(
            first_item, dict
        ), f"Raw data items should be dictionaries, got {type(first_item)}"

        # Essential fields that must be present in raw data
        required_fields = ["period", "spotPerKwh"]
        for field in required_fields:
            assert (
                field in first_item
            ), f"Required field '{field}' missing from raw data"

        # Additional validation for period field format
        assert isinstance(
            first_item["period"], str
        ), f"Period should be string, got {type(first_item['period'])}"
        assert isinstance(
            first_item["spotPerKwh"], (float, int)
        ), f"spotPerKwh should be numeric, got {type(first_item['spotPerKwh'])}"

        logger.info(f"Raw data contains {len(raw_data)} price points")

        # Act: Parse Raw Data
        parsed_data = await api.parse_raw_data(raw_data)

        # Assert: Parsed Data Structure (strict validation)
        assert parsed_data is not None, "Parsed data should not be None"
        assert isinstance(
            parsed_data, dict
        ), f"Parsed data should be a dictionary, got {type(parsed_data)}"

        # Required fields validation
        assert (
            parsed_data.get("source") == Source.AMBER
        ), f"Source should be {Source.AMBER}, got {parsed_data.get('source')}"

        # Area validation - Amber serves Australian market
        area = parsed_data.get("area")
        assert area is not None and area, f"Area should be specified, got {area}"
        assert isinstance(area, str), f"Area should be a string, got {type(area)}"

        # Currency validation - Amber uses AUD for Australian market
        assert (
            parsed_data.get("currency") == Currency.AUD
        ), f"Currency should be {Currency.AUD}, got {parsed_data.get('currency')}"

        # Timezone validation
        api_timezone = parsed_data.get("api_timezone")
        assert (
            api_timezone is not None and api_timezone
        ), f"api_timezone should have a value, got {api_timezone}"
        assert (
            "Australia" in api_timezone or "UTC" in api_timezone
        ), f"Expected Australian timezone or UTC, got {api_timezone}"

        # Interval prices validation
        assert "interval_raw" in parsed_data, "interval_raw missing from parsed data"
        interval_prices = parsed_data["interval_raw"]
        assert isinstance(
            interval_prices, dict
        ), f"interval_raw should be a dictionary, got {type(interval_prices)}"

        # Real-world validation: Amber should return price data
        assert (
            interval_prices
        ), "No interval prices found - this indicates a real issue with the API or parser"

        # Real-world validation: Amber should provide reasonable number of price entries
        # Amber may provide various interval data (5-min, 15-min, 30-min depending on API)
        min_expected_entries = 6  # At minimum, expecting a few intervals of data
        assert (
            len(interval_prices) >= min_expected_entries
        ), f"Expected at least {min_expected_entries} interval entries, got {len(interval_prices)}"

        # Validate timestamp format and price values
        for timestamp, price in interval_prices.items():
            # Validate timestamp format
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

                # Check timestamp is within reasonable range (not too old/future)
                now = datetime.now().astimezone()
                three_days_ago = now - timedelta(days=3)
                one_day_ahead = now + timedelta(
                    days=1
                )  # Amber typically has less future data than other providers
                assert (
                    three_days_ago <= dt <= one_day_ahead
                ), f"Timestamp {timestamp} is outside reasonable range"
            except ValueError:
                pytest.fail(f"Invalid timestamp format: '{timestamp}'")

            # Price validation
            assert isinstance(
                price, float
            ), f"Price should be a float, got {type(price)} for timestamp {timestamp}"

            # Real-world price range validation for Australian electricity market
            # Australian prices can spike extremely high in rare cases (up to $15,000/MWh)
            # but typical range is -100 to 500 AUD/MWh
            # Converting to cents/kWh, which is how Amber reports:
            assert (
                -50 <= price <= 1500
            ), f"Price {price} cents/kWh for {timestamp} is outside reasonable range"

        # Check for sequential timestamps (Amber may have 5-minute, 15-minute or 30-minute intervals)
        timestamps = sorted(interval_prices.keys())
        for i in range(1, len(timestamps)):
            prev_dt = datetime.fromisoformat(timestamps[i - 1].replace("Z", "+00:00"))
            curr_dt = datetime.fromisoformat(timestamps[i].replace("Z", "+00:00"))
            minutes_diff = (curr_dt - prev_dt).total_seconds() / 60

            # Valid intervals are multiples of 5 minutes (up to 60 minutes)
            valid_intervals = [5, 10, 15, 30, 60]
            is_valid = any(
                abs(minutes_diff - interval) < 1 for interval in valid_intervals
            )
            assert (
                is_valid
            ), f"Unexpected time gap between {timestamps[i-1]} and {timestamps[i]}: {minutes_diff} minutes"

        logger.info(
            f"Amber Live Test: PASS - Found {len(interval_prices)} interval prices. "
            f"Range: {min(interval_prices.values()):.2f} to {max(interval_prices.values()):.2f} cents/kWh"
        )

    except AssertionError as ae:
        # Let assertion errors propagate - these are test failures that should be fixed in the code, not the test
        logger.error(f"Amber Live Test: ASSERTION FAILED - {str(ae)}")
        raise
    except Exception as e:
        # Don't catch exceptions - let the test fail to expose real issues
        logger.error(f"Amber Live Test: EXCEPTION - {str(e)}")
        raise
    finally:
        if hasattr(api, "session") and api.session:
            await api.session.close()
