import pytest
import logging
from datetime import datetime, timedelta
import asyncio

from custom_components.ge_spot.api.energi_data import EnergiDataAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.const.time import TimeInterval

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mark all tests in this file as live API tests
pytestmark = [pytest.mark.liveapi, pytest.mark.skip(reason="Live API test - requires network access, skip by default")]

@pytest.mark.asyncio
@pytest.mark.parametrize("area", ["DK1", "DK2"]) # Energi Data Service is for Denmark
async def test_energi_data_live_fetch_parse(area):
    """Tests fetching and parsing live Energi Data Service data for a given area.
    
    Since Sept 30, 2025, Energi Data Service provides native 15-minute intervals
    from the DayAheadPrices dataset (96 intervals per day).
    
    This test makes actual API calls and verifies real responses.
    If it fails, investigate and fix the core code rather than modifying the test.
    """
    logger.info(f"Testing Energi Data Service live API for area: {area}...")
    # Arrange - allow failures during setup to find real issues
    api = EnergiDataAPI()
    session_closed = False

    try:
        # Act: Fetch Raw Data - no exception handling to expose real issues
        raw_data = await api.fetch_raw_data(area=area)

        # Assert: Raw Data Structure (strict validation)
        assert raw_data is not None, f"Raw data for {area} should not be None"
        assert isinstance(raw_data, dict), f"Raw data should be a dictionary, got {type(raw_data)}"

        # Validate API-specific structure - fetch_raw_data returns processed data with interval_raw
        assert "interval_raw" in raw_data, "Required field 'interval_raw' missing from raw data"
        assert isinstance(raw_data["interval_raw"], dict), f"interval_raw should be a dict, got {type(raw_data.get('interval_raw'))}"

        # Real-world validation: Energi Data Service should return interval prices
        interval_raw = raw_data["interval_raw"]
        assert len(interval_raw) > 0, f"No interval prices returned from Energi Data Service API for {area} - this indicates a real issue"

        logger.info(f"Received {len(interval_raw)} native 15-minute intervals from DayAheadPrices")

        # The fetch_raw_data now returns already-parsed data with interval_raw
        # So we use it directly instead of calling parse_raw_data
        parsed_data = raw_data

        # Assert: Parsed Data Structure (strict validation)
        assert parsed_data is not None, f"Parsed data for {area} should not be None"
        assert isinstance(parsed_data, dict), f"Parsed data should be a dictionary, got {type(parsed_data)}"

        # Currency validation - Energi Data Service uses DKK for Danish markets
        assert parsed_data.get("currency") == Currency.DKK, f"Currency should be {Currency.DKK}, got {parsed_data.get('currency')}"

        # Timezone validation
        api_timezone = parsed_data.get("timezone")
        assert api_timezone is not None and api_timezone, f"timezone should have a value, got {api_timezone}"
        # Danish timezone should be Europe/Copenhagen
        assert "Europe/Copenhagen" in api_timezone or "CET" in api_timezone, f"Expected Copenhagen timezone, got {api_timezone}"

        # Interval prices validation
        interval_prices = interval_raw
        assert isinstance(interval_prices, dict), f"interval_prices should be a dictionary, got {type(interval_prices)}"

        # Real-world validation: Native 15-minute intervals from DayAheadPrices
        # Expect 96 intervals per day (4 per hour × 24 hours)
        # Should have at least 48 intervals (half day)
        min_expected_intervals = 48
        expected_per_day = TimeInterval.get_intervals_per_day()  # 96
        
        assert len(interval_prices) >= min_expected_intervals, f"Expected at least {min_expected_intervals} interval prices (15-min native), got {len(interval_prices)}"
        
        # Log if we have full day(s) of data
        if len(interval_prices) >= expected_per_day:
            days = len(interval_prices) / expected_per_day
            logger.info(f"Received ~{days:.1f} day(s) of data ({len(interval_prices)} intervals)")

        # Validate timestamp format and price values
        for timestamp, price in interval_prices.items():
            # Validate timestamp format
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

                # Check timestamp is within reasonable range (not too old/future)
                now = datetime.now().astimezone()
                seven_days_ago = now - timedelta(days=7)  # Energi Data Service can provide historical data
                three_days_ahead = now + timedelta(days=3)  # And some future data (day-ahead market)
                assert seven_days_ago <= dt <= three_days_ahead, f"Timestamp {timestamp} is outside reasonable range for {area}"
            except ValueError:
                raise AssertionError(f"Invalid timestamp format: '{timestamp}' for {area}")

            # Price validation
            assert isinstance(price, (int, float)), f"Price should be numeric, got {type(price)} for timestamp {timestamp}"

            # Real-world price range validation for Danish electricity market
            # Danish prices typically range from negative values to several hundred DKK/MWh
            # The price range in DKK/MWh is typically between -500 and 3000
            assert -500 <= price <= 5000, f"Price {price} DKK/MWh for {timestamp} is outside reasonable range for {area}"

        # Check for sequential 15-minute timestamps
        timestamps = sorted(interval_prices.keys())
        correct_spacing = 0
        total_checks = 0
        
        for i in range(1, min(len(timestamps), 20)):  # Check first 20 intervals
            prev_dt = datetime.fromisoformat(timestamps[i-1].replace("Z", "+00:00"))
            curr_dt = datetime.fromisoformat(timestamps[i].replace("Z", "+00:00"))
            time_diff_minutes = (curr_dt - prev_dt).total_seconds() / 60
            
            total_checks += 1
            if time_diff_minutes == 15:
                correct_spacing += 1
            else:
                logger.warning(f"Unexpected time gap of {time_diff_minutes} minutes between {timestamps[i-1]} and {timestamps[i]}")

        # Most intervals should be 15 minutes apart
        spacing_pct = (correct_spacing / total_checks * 100) if total_checks > 0 else 0
        assert spacing_pct >= 80, f"Expected mostly 15-minute intervals, got {spacing_pct:.1f}% correct spacing"

        logger.info(f"Energi Data Service Live Test ({area}): PASS - Found {len(interval_prices)} prices. "
                  f"Range: {min(interval_prices.values()):.2f} to {max(interval_prices.values()):.2f} {parsed_data.get('currency')}/MWh. "
                  f"Spacing: {spacing_pct:.1f}% correct (15-min intervals)")

    except AssertionError as ae:
        # Let assertion errors propagate - these are test failures that should be fixed in the code, not the test
        logger.error(f"Energi Data Service Live Test ({area}): ASSERTION FAILED - {str(ae)}")
        raise
    except Exception as e:
        # Don't catch exceptions - let the test fail to expose real issues
        logger.error(f"Energi Data Service Live Test ({area}): EXCEPTION - {str(e)}")
        raise
    finally:
        # Proper async cleanup
        if hasattr(api, 'session') and api.session and not session_closed:
            try:
                await api.session.close()
                session_closed = True
                # Give a moment for the session to fully close
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.warning(f"Error closing session: {e}")