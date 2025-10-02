"""Test file for timestamp handling in BasePriceParser.
The tests in this file should identify real issues in timestamp handling,
not be adapted to pass validation. If a test fails, investigate and fix
the core timestamp handling code.
"""
import pytest # Add pytest import
from datetime import datetime, timezone, timedelta
import pytz
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__) # Define _LOGGER

from custom_components.ge_spot.api.base.price_parser import BasePriceParser

# Create a test implementation of BasePriceParser
# Rename to avoid pytest collection warning
class _TestPriceParser(BasePriceParser):
    """Test implementation of BasePriceParser for testing."""
    def parse(self, raw_data):
        """Test implementation."""
        return raw_data

# Define timezones and dates as fixtures for reuse
@pytest.fixture(scope="module")
def timezones():
    return {
        "utc": timezone.utc,
        "cet": pytz.timezone("Europe/Stockholm"),
        "us_eastern": pytz.timezone("America/New_York"),
        "australian": pytz.timezone("Australia/Sydney"),
        "japanese": pytz.timezone("Asia/Tokyo"),
        "uk": pytz.timezone("Europe/London"),
        "helsinki": pytz.timezone("Europe/Helsinki")
    }

@pytest.fixture(scope="module")
def test_dates(timezones):
    today = datetime.now(timezones["utc"]).date()
    _LOGGER.info(f"Testing with today's date: {today}") # Log moved here
    return {
        "today": today,
        "tomorrow": today + timedelta(days=1),
        "yesterday": today - timedelta(days=1)
    }


@pytest.fixture
def parser():
    return _TestPriceParser("test_source")

# Test class for timestamp handling - No longer inherits unittest.TestCase
class TestTimestampHandling:
    """Test timestamp handling in BasePriceParser."""

    def test_parse_timestamp_iso(self, parser, timezones):
        """Test parsing ISO format timestamps with multiple formats and edge cases."""
        # Standard ISO with timezone - should handle correctly and return UTC
        iso_tz = "2023-05-15T12:00:00+00:00"
        dt = parser.parse_timestamp(iso_tz, timezones["utc"]) # Source TZ doesn't matter if offset present
        assert dt.hour == 12, f"Expected hour 12 UTC, got {dt.hour}"
        assert dt.date() == datetime(2023, 5, 15).date(), f"Expected date 2023-05-15, got {dt.date()}"
        assert dt.tzinfo == timezone.utc, f"Expected timezone UTC, got {dt.tzinfo}"

        # ISO without timezone - should assume source timezone and return UTC
        iso_no_tz = "2023-05-15T14:00:00"
        dt = parser.parse_timestamp(iso_no_tz, timezones["cet"]) # Assume CET (+1 or +2)
        # 14:00 CET is 13:00 UTC (standard) or 12:00 UTC (DST)
        assert dt.tzinfo == timezone.utc, f"Expected timezone UTC, got {dt.tzinfo}"
        # Check if the UTC hour matches the expected conversion from 14:00 CET
        expected_utc_hour = 14 - (timezones["cet"].utcoffset(datetime(2023, 5, 15, 14, 0)).total_seconds() / 3600)
        assert dt.hour == expected_utc_hour, f"Expected hour {expected_utc_hour} UTC from 14:00 CET, got {dt.hour}"
        assert dt.date() == datetime(2023, 5, 15).date(), f"Expected date 2023-05-15, got {dt.date()}"


        # ISO with Z suffix for UTC - should handle correctly and return UTC
        iso_z = "2023-05-15T16:30:00Z"
        dt = parser.parse_timestamp(iso_z, timezones["utc"]) # Source TZ irrelevant
        assert dt.hour == 16, f"Expected hour 16 UTC, got {dt.hour}"
        assert dt.minute == 30, f"Expected minute 30, got {dt.minute}"
        assert dt.tzinfo == timezone.utc, f"Expected timezone UTC, got {dt.tzinfo}"

        # ISO with different timezone offset - should correctly convert to UTC
        iso_offset = "2023-05-15T18:45:00+02:00"
        dt = parser.parse_timestamp(iso_offset, timezones["utc"]) # Source TZ irrelevant
        # The time should be stored as UTC, so 18:45+02:00 becomes 16:45 UTC
        assert dt.hour == 16, f"Expected hour 16 UTC (after offset conversion), got {dt.hour}" # FIXED Assertion
        assert dt.minute == 45, f"Expected minute 45, got {dt.minute}"
        assert dt.tzinfo == timezone.utc, f"Expected timezone UTC, got {dt.tzinfo}"


        # Test with microseconds - should handle correctly and return UTC
        iso_micros = "2023-05-15T22:15:30.123456+00:00"
        dt = parser.parse_timestamp(iso_micros, timezones["utc"]) # Source TZ irrelevant
        assert dt.hour == 22, f"Expected hour 22 UTC, got {dt.hour}"
        assert dt.minute == 15, f"Expected minute 15, got {dt.minute}"
        assert dt.second == 30, f"Expected second 30, got {dt.second}"
        assert dt.microsecond == 123456, f"Expected microsecond 123456, got {dt.microsecond}"
        assert dt.tzinfo == timezone.utc, f"Expected timezone UTC, got {dt.tzinfo}"

        # Test with invalid ISO format - should raise ValueError
        invalid_iso = "2023-05-15X12:00:00+00:00"  # 'X' instead of 'T'
        with pytest.raises(ValueError): # Use pytest.raises
            parser.parse_timestamp(invalid_iso, timezones["utc"])

    def test_parse_timestamp_date_time(self, parser, timezones, test_dates):
        """Test parsing various date + time format timestamps including international formats."""
        # Standard format - should assume source timezone and return UTC
        date_time = "2023-05-15 12:00"
        dt = parser.parse_timestamp(date_time, timezones["utc"]) # Assume UTC source
        assert dt.hour == 12, f"Expected hour 12 UTC, got {dt.hour}"
        assert dt.date() == datetime(2023, 5, 15).date(), f"Expected date 2023-05-15, got {dt.date()}"
        assert dt.tzinfo == timezone.utc, f"Expected timezone UTC, got {dt.tzinfo}"

        # European format - should assume source timezone (CET) and return UTC
        euro_date = "15.05.2023 14:30"
        dt = parser.parse_timestamp(euro_date, timezones["cet"]) # Assume CET source
        assert dt.tzinfo == timezone.utc, f"Expected timezone UTC, got {dt.tzinfo}"
        expected_utc_hour = 14 - (timezones["cet"].utcoffset(datetime(2023, 5, 15, 14, 30)).total_seconds() / 3600)
        assert dt.hour == expected_utc_hour, f"Expected hour {expected_utc_hour} UTC from 14:30 CET, got {dt.hour}"
        assert dt.minute == 30, f"Expected minute 30, got {dt.minute}"
        assert dt.date() == datetime(2023, 5, 15).date(), f"Expected date 2023-05-15, got {dt.date()}"


        # US format - should assume source timezone (US Eastern) and return UTC
        us_date = "05/15/2023 10:45"
        dt = parser.parse_timestamp(us_date, timezones["us_eastern"]) # Assume US Eastern source
        assert dt.tzinfo == timezone.utc, f"Expected timezone UTC, got {dt.tzinfo}"
        expected_utc_hour = 10 - (timezones["us_eastern"].utcoffset(datetime(2023, 5, 15, 10, 45)).total_seconds() / 3600)
        assert dt.hour == expected_utc_hour, f"Expected hour {expected_utc_hour} UTC from 10:45 US Eastern, got {dt.hour}"
        assert dt.minute == 45, f"Expected minute 45, got {dt.minute}"
        assert dt.date() == datetime(2023, 5, 15).date(), f"Expected date 2023-05-15, got {dt.date}"


        # Test with seconds - should assume source timezone and return UTC
        date_time_sec = "2023-05-15 12:00:30"
        dt = parser.parse_timestamp(date_time_sec, timezones["utc"]) # Assume UTC source
        assert dt.hour == 12, f"Expected hour 12 UTC, got {dt.hour}"
        assert dt.second == 30, f"Expected second 30, got {dt.second}"
        assert dt.tzinfo == timezone.utc, f"Expected timezone UTC, got {dt.tzinfo}"

        # Test with just the time - should assume today's date in source timezone and return UTC
        time_only = "16:45"
        dt = parser.parse_timestamp(time_only, timezones["utc"]) # Assume UTC source
        assert dt.hour == 16, f"Expected hour 16 UTC, got {dt.hour}"
        assert dt.minute == 45, f"Expected minute 45, got {dt.minute}"
        assert dt.date() == test_dates["today"], f"Expected today's date {test_dates['today']}, got {dt.date()}"
        assert dt.tzinfo == timezone.utc, f"Expected timezone UTC, got {dt.tzinfo}"

        # Test with invalid format - should raise ValueError
        invalid_datetime = "2023/05/15 12:00"  # Forward slashes in ISO-like format
        with pytest.raises(ValueError): # Use pytest.raises
            parser.parse_timestamp(invalid_datetime, timezones["utc"])

    def test_classify_timestamp_day(self, parser, timezones, test_dates):
        """Test classifying timestamps as today or tomorrow across various timezones."""
        # Input timestamps should be UTC after parsing
        # Today 12:00 UTC
        today_utc = datetime.combine(test_dates["today"], datetime.min.time().replace(hour=12), tzinfo=timezone.utc)
        day_type = parser.classify_timestamp_day(today_utc, timezones["utc"])
        assert day_type == "today", f"Expected 'today', got '{day_type}' for {today_utc} in UTC"

        # Tomorrow 12:00 UTC
        tomorrow_utc = datetime.combine(test_dates["tomorrow"], datetime.min.time().replace(hour=12), tzinfo=timezone.utc)
        day_type = parser.classify_timestamp_day(tomorrow_utc, timezones["utc"])
        assert day_type == "tomorrow", f"Expected 'tomorrow', got '{day_type}' for {tomorrow_utc} in UTC"

        # Yesterday 12:00 UTC
        yesterday_utc = datetime.combine(test_dates["yesterday"], datetime.min.time().replace(hour=12), tzinfo=timezone.utc)
        day_type = parser.classify_timestamp_day(yesterday_utc, timezones["utc"])
        assert day_type == "other", f"Expected 'other' for yesterday {yesterday_utc} in UTC, got '{day_type}'" # FIXED Assertion

        # Cross-timezone tests - critical for real-world operation
        # Late today in UTC (22:00) but tomorrow in Tokyo (UTC+9 -> 07:00 next day)
        late_today_utc = datetime.combine(test_dates["today"], datetime.min.time().replace(hour=22), tzinfo=timezone.utc)

        # Should be "today" in UTC
        day_type = parser.classify_timestamp_day(late_today_utc, timezones["utc"])
        assert day_type == "today", f"Expected 'today', got '{day_type}' for {late_today_utc} in UTC"

        # Should be "tomorrow" in Tokyo (UTC 22:00 Oct 2 = Tokyo 07:00 Oct 3)
        day_type = parser.classify_timestamp_day(late_today_utc, timezones["japanese"])
        assert day_type == "tomorrow", f"Expected 'tomorrow', got '{day_type}' for {late_today_utc} in Tokyo"

        # Test early tomorrow UTC (01:00) which might be today in US timezones (e.g., US Eastern UTC-5/-4 -> 21:00/20:00 previous day)
        early_tomorrow_utc = datetime.combine(test_dates["tomorrow"], datetime.min.time().replace(hour=1), tzinfo=timezone.utc)

        # Should be "tomorrow" in UTC
        day_type = parser.classify_timestamp_day(early_tomorrow_utc, timezones["utc"])
        assert day_type == "tomorrow", f"Expected 'tomorrow', got '{day_type}' for {early_tomorrow_utc} in UTC"

        # Should be "today" in US Eastern
        day_type = parser.classify_timestamp_day(early_tomorrow_utc, timezones["us_eastern"])
        assert day_type == "today", f"Expected 'today', got '{day_type}' for {early_tomorrow_utc} in US Eastern" # FIXED Assertion


    def test_normalize_timestamps(self, parser, timezones, test_dates):
        """Test normalizing timestamps and separating into today/tomorrow with complex cases."""
        # Create sample data mixing today and tomorrow
        today_str = test_dates["today"].strftime("%Y-%m-%d")
        tomorrow_str = test_dates["tomorrow"].strftime("%Y-%m-%d")

        mixed_prices = {
            # Today timestamps in various formats (assumed UTC source for simplicity here)
            f"{today_str}T10:00:00+00:00": 50.0,  # ISO with TZ (UTC)
            f"{today_str} 12:00": 60.0,           # Date + time (assume UTC source)
            "14:00": 70.0,                        # Hour only (assume UTC source, today's date)

            # Tomorrow timestamps
            f"{tomorrow_str}T10:00:00+00:00": 55.0,  # ISO with TZ (UTC)
            f"{tomorrow_str} 12:00": 65.0,           # Date + time (assume UTC source)
        }

        # Normalize with explicit source and target timezone (UTC -> UTC)
        result = parser.normalize_timestamps(
            mixed_prices,
            timezones["utc"],  # Source timezone (assumed for ambiguous keys)
            timezones["utc"]   # Target timezone
        )

        # Check the results - "14:00" should now be included
        assert len(result["today"]) == 3, f"Expected 3 today entries, got {len(result['today'])}: {result['today']}" # FIXED Assertion
        assert len(result["tomorrow"]) == 2, f"Expected 2 tomorrow entries, got {len(result['tomorrow'])}: {result['tomorrow']}"
        assert len(result["other"]) == 0, f"Expected 0 other entries, got {len(result['other'])}"

        # Verify specific hours are correctly assigned
        assert result["today"]["10:00"] == 50.0, "Expected '10:00' today to have value 50.0"
        assert result["today"]["12:00"] == 60.0, "Expected '12:00' today to have value 60.0"
        assert result["today"]["14:00"] == 70.0, "Expected '14:00' today to have value 70.0" # FIXED Assertion

        assert result["tomorrow"]["10:00"] == 55.0, "Expected '10:00' tomorrow to have value 55.0"
        assert result["tomorrow"]["12:00"] == 65.0, "Expected '12:00' tomorrow to have value 65.0"

        # Test with timezone conversion - critical for real-world operation
        # UTC -> CET (usually +1 or +2 hours)
        result_cet = parser.normalize_timestamps(
            mixed_prices,
            timezones["utc"],  # Source timezone
            timezones["cet"]   # Target timezone (CET/CEST)
        )

        # Calculate the expected hour for 10:00 UTC in CET
        dt_10_utc = datetime.fromisoformat(f"{today_str}T10:00:00+00:00")
        dt_10_cet = dt_10_utc.astimezone(timezones["cet"])
        expected_hour_10_cet = f"{dt_10_cet.hour:02d}:00"

        # Check if 10:00 UTC falls on today or tomorrow in CET
        day_key_10 = "today" if dt_10_cet.date() == test_dates["today"] else "tomorrow"

        assert expected_hour_10_cet in result_cet[day_key_10], f"Expected '{expected_hour_10_cet}' in '{day_key_10}' CET data"
        if expected_hour_10_cet in result_cet[day_key_10]:
            assert result_cet[day_key_10][expected_hour_10_cet] == 50.0, \
                           f"Expected '{expected_hour_10_cet}' {day_key_10} to have value 50.0 after UTC->CET conversion"


        # Test with a more complex timezone difference - UTC -> Australia (usually +10/+11 hours)
        result_aus = parser.normalize_timestamps(
            mixed_prices,
            timezones["utc"],        # Source timezone
            timezones["australian"]  # Target timezone (AEST/AEDT)
        )

        # Calculate the expected hour for 14:00 UTC (assumed today) in Australia/Sydney
        dt_14_utc = parser.parse_timestamp("14:00", timezones["utc"]) # Uses today's date
        dt_14_aus = dt_14_utc.astimezone(timezones["australian"])
        expected_hour_14_aus = f"{dt_14_aus.hour:02d}:00"

        # Check if 14:00 UTC falls on today or tomorrow in Australia relative to Australia's current date
        # Use the classification function itself to determine the expected key
        day_key_14 = parser.classify_timestamp_day(dt_14_utc, timezones["australian"])

        assert expected_hour_14_aus in result_aus[day_key_14], \
                    f"Expected '{expected_hour_14_aus}' to be in '{day_key_14}' data after UTC->Australia conversion (Ref Date: {datetime.now(timezones['australian']).date()}, Aus Date: {dt_14_aus.date()})" # CORRECTED Assertion logic
        if expected_hour_14_aus in result_aus[day_key_14]:
            assert result_aus[day_key_14][expected_hour_14_aus] == 70.0, \
                           f"Expected '{expected_hour_14_aus}' {day_key_14} to have value 70.0 after UTC->Australia conversion"


    # ... test_cross_midnight_case should be fine with updated classify_timestamp_day ...

    def test_real_world_edge_cases(self, parser, timezones, test_dates):
        """Test real-world edge cases that might occur in actual electricity markets."""
        # Test DST transition timestamps - critical for electricity markets during DST transitions
        # Use a known DST fallback date for CET/CEST: Last Sunday in October
        # Find the last Sunday of October for a recent year (e.g., 2023)
        year = 2023
        dst_fallback_date = None
        for day in range(31, 24, -1): # Check from Oct 31 backwards
             try:
                 d = datetime(year, 10, day)
                 if d.weekday() == 6: # Sunday
                     dst_fallback_date = d.date()
                     break
             except ValueError:
                 continue # Ignore invalid dates like Oct 32

        assert dst_fallback_date is not None, "Could not determine DST fallback date for testing"
        _LOGGER.info(f"Using DST fallback date for testing: {dst_fallback_date}")

        # Test case for "fall back" transition where 2:00-3:00 occurs twice in CET
        fall_back_prices = {
            # First occurrence of 2:00-3:00 (CEST = UTC+2)
            f"{dst_fallback_date.isoformat()}T02:00:00+02:00": 80.0,
            # Second occurrence of 2:00-3:00 after falling back (CET = UTC+1)
            f"{dst_fallback_date.isoformat()}T02:00:00+01:00": 85.0,
            # Include another hour to ensure context date is used correctly
            f"{dst_fallback_date.isoformat()}T04:00:00+01:00": 90.0,
        }

        # Normalize with explicit CET timezone, providing the specific date context
        result_dst = parser.normalize_timestamps(
            fall_back_prices,
            timezones["cet"],  # Source timezone (explicit in keys)
            timezones["cet"],  # Target timezone
            date_context=dst_fallback_date # Provide context for classification
        )

        assert result_dst is not None, "Normalizing DST transition timestamps should not fail"
        # All these times should fall on the same calendar day in CET
        assert "today" in result_dst, "Result should contain 'today' key"
        assert len(result_dst["today"]) == 2, f"Expected 2 distinct hours (02:00, 04:00) after DST fallback normalization, got {len(result_dst['today'])} keys: {result_dst['today'].keys()}" # FIXED Assertion: 2 keys expected (02:00, 04:00)
        assert "02:00" in result_dst["today"], "Expected '02:00' key after DST fallback normalization"
        # Check that the value corresponds to the *second* occurrence (standard time, +01:00) due to overwrite
        assert result_dst["today"]["02:00"] == 85.0, "Expected value from the second occurrence of 02:00 during DST fallback"
        assert "04:00" in result_dst["today"], "Expected '04:00' key"
        assert result_dst["today"]["04:00"] == 90.0, "Expected correct value for 04:00"
        assert len(result_dst["tomorrow"]) == 0, "Expected 0 tomorrow entries for DST test"
        assert len(result_dst["other"]) == 0, f"Expected 0 other entries for DST test, got {len(result_dst['other'])}" # Check 'other'


        # Test case for empty input
        empty_prices = {}
        result_empty = parser.normalize_timestamps(
            empty_prices,
            timezones["utc"],  # Source timezone
            timezones["utc"]   # Target timezone
        )

        # Should return empty structures, not None or error
        assert result_empty is not None, "Normalizing empty prices should not fail"
        assert "today" in result_empty, "Result should contain 'today' key even with empty input"
        assert "tomorrow" in result_empty, "Result should contain 'tomorrow' key even with empty input"
        assert "other" in result_empty, "Result should contain 'other' key even with empty input"
        assert len(result_empty["today"]) == 0, "Expected 0 entries for today with empty input"
        assert len(result_empty["tomorrow"]) == 0, "Expected 0 entries for tomorrow with empty input"
        assert len(result_empty["other"]) == 0, "Expected 0 entries for other with empty input"

        # Test with malformed timestamps - should skip invalid, process valid
        malformed_prices = {
            "not_a_timestamp": 100.0,
            "2023-13-45 25:70": 200.0,  # Invalid month, day, hour, minute
            f"{test_dates['today'].strftime('%Y-%m-%d')}T15:00:00Z": 99.0 # Add a valid one
        }

        result_malformed = parser.normalize_timestamps(
            malformed_prices,
            timezones["utc"],  # Source timezone
            timezones["utc"]   # Target timezone
        )
        assert result_malformed is not None, "Normalizing malformed timestamps should not return None"
        # Assert that only the valid entry was created
        assert len(result_malformed["today"]) == 1, f"Expected 1 today entry with mixed malformed/valid input, got {len(result_malformed['today'])}"
        assert len(result_malformed["tomorrow"]) == 0, f"Expected 0 tomorrow entries with mixed malformed/valid input, got {len(result_malformed['tomorrow'])}"
        assert len(result_malformed["other"]) == 0, f"Expected 0 other entries with mixed malformed/valid input, got {len(result_malformed['other'])}"
        assert "15:00" in result_malformed["today"], "Expected valid timestamp '15:00' to be present"
        assert result_malformed["today"]["15:00"] == 99.0, "Expected correct value for valid timestamp"

# No need for unittest entry point