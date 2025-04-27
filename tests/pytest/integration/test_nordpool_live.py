import pytest
import logging
from datetime import datetime, timedelta

from custom_components.ge_spot.api.nordpool import NordpoolAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mark all tests in this file as live API tests
pytestmark = pytest.mark.liveapi

@pytest.mark.asyncio
@pytest.mark.parametrize("area", ["FI", "SE3", "NO1", "DK1"])  # Test key Nordic market areas
async def test_nordpool_live_fetch_parse(area):
    """Tests fetching and parsing live Nordpool data for various Nordic areas.
    This test makes actual API calls and validates real responses.
    If it fails, investigate and fix the core code rather than modifying the test.
    """
    logger.info(f"Testing Nordpool live API for area: {area}...")
    # Arrange - don't catch exceptions during setup
    api = NordpoolAPI()

    try:
        # Act: Fetch Raw Data - no exception handling to expose real issues
        raw_data = await api.fetch_raw_data(area=area)
        
        # Assert: Raw Data Structure (strict validation)
        assert raw_data is not None, f"Raw data for {area} should not be None"
        assert isinstance(raw_data, dict), f"Raw data should be a dictionary, got {type(raw_data)}"
        
        # Validate Nordpool-specific structure
        assert "today" in raw_data, "Required field 'today' missing from raw data"
        assert isinstance(raw_data.get("today"), dict), f"today should be a dictionary, got {type(raw_data.get('today'))}"
        
        # Validate source and area information
        assert raw_data.get("source") == Source.NORDPOOL, f"Source should be {Source.NORDPOOL}, got {raw_data.get('source')}"
        assert raw_data.get("area") == area, f"Area should be {area}, got {raw_data.get('area')}"
        
        # Timezone validation - Nordpool uses Oslo time
        assert raw_data.get("api_timezone") == "Europe/Oslo", f"Timezone should be Europe/Oslo, got {raw_data.get('api_timezone')}"
        
        # Validate today data structure
        today_data = raw_data.get("today", {})
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
            # Some areas like SE3 might be mapped to SE.03 in the API
            mapped_area = area
            if area == "SE3":
                mapped_area = "SE.03"
            elif area == "SE4":
                mapped_area = "SE.04"
            
            # Either the exact area or a mapped version should be present
            assert area in entry_per_area or mapped_area in entry_per_area, f"Area {area} not found in entryPerArea"
        
        logger.info(f"Raw data contains {len(multi_area_entries)} price entries")

        # Act: Parse Raw Data
        parsed_data = await api.parse_raw_data(raw_data)
        
        # Assert: Parsed Data Structure (strict validation)
        assert parsed_data is not None, f"Parsed data for {area} should not be None"
        assert isinstance(parsed_data, dict), f"Parsed data should be a dictionary, got {type(parsed_data)}"
        
        # Required fields validation
        assert parsed_data.get("source") == Source.NORDPOOL, f"Source should be {Source.NORDPOOL}, got {parsed_data.get('source')}"
        assert parsed_data.get("area") == area, f"Area should be {area}, got {parsed_data.get('area')}"
        
        # Currency validation - Nordpool typically uses EUR for Nordic markets
        assert parsed_data.get("currency") == Currency.EUR, f"Currency should be {Currency.EUR}, got {parsed_data.get('currency')}"
        
        # Timezone validation
        assert parsed_data.get("api_timezone") == "Europe/Oslo", f"Timezone should be Europe/Oslo, got {parsed_data.get('api_timezone')}"
        
        # Hourly prices validation
        assert "hourly_prices" in parsed_data, "hourly_prices missing from parsed data"
        hourly_prices = parsed_data.get("hourly_prices", {})
        assert isinstance(hourly_prices, dict), f"hourly_prices should be a dictionary, got {type(hourly_prices)}"
        
        # If we're running the test at a time when prices are published, we should have data
        # Nordpool typically publishes prices around 13:00 CET for the next day
        now = datetime.now()
        prices_should_be_available = now.hour >= 14  # After 14:00 local time, prices should be available
        
        if prices_should_be_available:
            # Real-world validation: Nordpool should return price data after publication time
            assert hourly_prices, f"No hourly prices found for {area} after publication time - this indicates a real issue"
            
            # Validate price data - should have 24 hours (or 23/25 during DST changes)
            valid_hour_counts = [23, 24, 25]  # Account for DST changes
            assert len(hourly_prices) in valid_hour_counts, f"Expected 23-25 hourly prices, got {len(hourly_prices)}"
            
            # Validate timestamp format and price values
            for timestamp, price in hourly_prices.items():
                # Validate timestamp format
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    
                    # Check timestamp is within reasonable range (not too old/future)
                    now = datetime.now().astimezone()
                    yesterday = now - timedelta(days=1)
                    tomorrow = now + timedelta(days=1)
                    assert yesterday <= dt <= tomorrow, f"Timestamp {timestamp} is outside reasonable range for {area}"
                except ValueError:
                    pytest.fail(f"Invalid timestamp format: '{timestamp}' for {area}")
                
                # Price validation
                assert isinstance(price, float), f"Price should be a float, got {type(price)} for timestamp {timestamp}"
                
                # Real-world price range validation for Nordic electricity market
                # Nordic prices typically range from negative values to several hundred EUR/MWh
                assert -500 <= price <= 3000, f"Price {price} EUR/MWh for {timestamp} is outside reasonable range for {area}"
            
            # Check for sequential hourly timestamps
            timestamps = sorted(hourly_prices.keys())
            for i in range(1, len(timestamps)):
                prev_dt = datetime.fromisoformat(timestamps[i-1].replace("Z", "+00:00"))
                curr_dt = datetime.fromisoformat(timestamps[i].replace("Z", "+00:00"))
                hour_diff = (curr_dt - prev_dt).total_seconds() / 3600
                
                # Nordic market data should be hourly, except during DST changes
                valid_hour_diff = abs(hour_diff - 1.0) < 0.1 or abs(hour_diff - 2.0) < 0.1 or abs(hour_diff - 0.0) < 0.1
                assert valid_hour_diff, f"Unexpected time gap between {timestamps[i-1]} and {timestamps[i]} for {area}: {hour_diff} hours"
            
            logger.info(f"Nordpool Live Test ({area}): PASS - Found {len(hourly_prices)} prices. "
                      f"Range: {min(hourly_prices.values()):.2f} to {max(hourly_prices.values()):.2f} {parsed_data.get('currency')}/MWh")
        else:
            # If running before publication time, we might not have prices yet, but the structure should be valid
            logger.info(f"Nordpool Live Test ({area}): NOTE - No hourly prices yet (before publication time)")

    except AssertionError as ae:
        # Let assertion errors propagate - these are test failures that should be fixed in the code, not the test
        logger.error(f"Nordpool Live Test ({area}): ASSERTION FAILED - {str(ae)}")
        raise
    except Exception as e:
        # Don't catch exceptions - let the test fail to expose real issues
        logger.error(f"Nordpool Live Test ({area}): EXCEPTION - {str(e)}")
        raise