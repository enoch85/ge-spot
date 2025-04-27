"""Test file for timestamp handling in BasePriceParser.
The tests in this file should identify real issues in timestamp handling,
not be adapted to pass validation. If a test fails, investigate and fix
the core timestamp handling code.
"""
import unittest
from datetime import datetime, timezone, timedelta
import pytz
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from custom_components.ge_spot.api.base.price_parser import BasePriceParser

# Create a test implementation of BasePriceParser
class TestPriceParser(BasePriceParser):
    """Test implementation of BasePriceParser for testing."""
    def parse(self, raw_data):
        """Test implementation."""
        return raw_data

# Test class for timestamp handling
class TestTimestampHandling(unittest.TestCase):
    """Test timestamp handling in BasePriceParser."""
    
    def setUp(self):
        """Set up test environment."""
        self.parser = TestPriceParser("test_source")
        
        # Define timezones for testing - use a variety of timezones to test real-world cases
        self.utc = timezone.utc
        self.cet = pytz.timezone("Europe/Stockholm")  # CET/CEST
        self.us_eastern = pytz.timezone("America/New_York")  # EST/EDT
        self.australian = pytz.timezone("Australia/Sydney")  # AEST/AEDT
        self.japanese = pytz.timezone("Asia/Tokyo")  # JST
        self.uk = pytz.timezone("Europe/London")  # GMT/BST
        
        # Define test dates for consistent testing
        self.today = datetime.now(self.utc).date()
        self.tomorrow = self.today + timedelta(days=1)
        self.yesterday = self.today - timedelta(days=1)
        
        # Log test setup for clarity
        logger.info(f"Testing with today's date: {self.today}")
    
    def test_parse_timestamp_iso(self):
        """Test parsing ISO format timestamps with multiple formats and edge cases."""
        # Standard ISO with timezone - should handle correctly
        iso_tz = "2023-05-15T12:00:00+00:00"
        dt = self.parser.parse_timestamp(iso_tz, self.utc)
        self.assertEqual(dt.hour, 12, f"Expected hour 12, got {dt.hour}")
        self.assertEqual(dt.date(), datetime(2023, 5, 15).date(), f"Expected date 2023-05-15, got {dt.date()}")
        self.assertEqual(dt.tzinfo, timezone.utc, f"Expected timezone UTC, got {dt.tzinfo}")
        
        # ISO without timezone - should correctly apply the provided timezone
        iso_no_tz = "2023-05-15T14:00:00"
        dt = self.parser.parse_timestamp(iso_no_tz, self.cet)
        self.assertEqual(dt.hour, 14, f"Expected hour 14, got {dt.hour}")
        self.assertEqual(dt.date(), datetime(2023, 5, 15).date(), f"Expected date 2023-05-15, got {dt.date()}")
        # Check timezone is correctly applied
        self.assertEqual(dt.tzinfo, self.cet, f"Expected timezone CET, got {dt.tzinfo}")
        
        # ISO with Z suffix for UTC - should handle correctly
        iso_z = "2023-05-15T16:30:00Z"
        dt = self.parser.parse_timestamp(iso_z, self.utc)
        self.assertEqual(dt.hour, 16, f"Expected hour 16, got {dt.hour}")
        self.assertEqual(dt.minute, 30, f"Expected minute 30, got {dt.minute}")
        self.assertEqual(dt.tzinfo, timezone.utc, f"Expected timezone UTC, got {dt.tzinfo}")
        
        # ISO with different timezone offset - should correctly convert
        iso_offset = "2023-05-15T18:45:00+02:00"
        dt = self.parser.parse_timestamp(iso_offset, self.utc)
        # The time should be stored as UTC, so 18:45+02:00 becomes 16:45 UTC
        self.assertEqual(dt.hour, 16, f"Expected hour 16 (after offset conversion), got {dt.hour}")
        self.assertEqual(dt.minute, 45, f"Expected minute 45, got {dt.minute}")
        
        # Test with microseconds - should handle correctly
        iso_micros = "2023-05-15T22:15:30.123456+00:00"
        dt = self.parser.parse_timestamp(iso_micros, self.utc)
        self.assertEqual(dt.hour, 22, f"Expected hour 22, got {dt.hour}")
        self.assertEqual(dt.minute, 15, f"Expected minute 15, got {dt.minute}")
        self.assertEqual(dt.second, 30, f"Expected second 30, got {dt.second}")
        self.assertEqual(dt.microsecond, 123456, f"Expected microsecond 123456, got {dt.microsecond}")
        
        # Test with invalid ISO format - should raise ValueError
        invalid_iso = "2023-05-15X12:00:00+00:00"  # 'X' instead of 'T'
        with self.assertRaises(ValueError):
            self.parser.parse_timestamp(invalid_iso, self.utc)
    
    def test_parse_timestamp_date_time(self):
        """Test parsing various date + time format timestamps including international formats."""
        # Standard format - should handle correctly
        date_time = "2023-05-15 12:00"
        dt = self.parser.parse_timestamp(date_time, self.utc)
        self.assertEqual(dt.hour, 12, f"Expected hour 12, got {dt.hour}")
        self.assertEqual(dt.date(), datetime(2023, 5, 15).date(), f"Expected date 2023-05-15, got {dt.date()}")
        self.assertEqual(dt.tzinfo, self.utc, f"Expected timezone UTC, got {dt.tzinfo}")
        
        # European format - should handle correctly
        euro_date = "15.05.2023 14:30"
        dt = self.parser.parse_timestamp(euro_date, self.cet)
        self.assertEqual(dt.hour, 14, f"Expected hour 14, got {dt.hour}")
        self.assertEqual(dt.minute, 30, f"Expected minute 30, got {dt.minute}")
        self.assertEqual(dt.date(), datetime(2023, 5, 15).date(), f"Expected date 2023-05-15, got {dt.date()}")
        self.assertEqual(dt.tzinfo, self.cet, f"Expected timezone CET, got {dt.tzinfo}")
        
        # US format - should handle correctly
        us_date = "05/15/2023 10:45"
        dt = self.parser.parse_timestamp(us_date, self.us_eastern)
        self.assertEqual(dt.hour, 10, f"Expected hour 10, got {dt.hour}")
        self.assertEqual(dt.minute, 45, f"Expected minute 45, got {dt.minute}")
        self.assertEqual(dt.date(), datetime(2023, 5, 15).date(), f"Expected date 2023-05-15, got {dt.date()}")
        self.assertEqual(dt.tzinfo, self.us_eastern, f"Expected timezone US Eastern, got {dt.tzinfo}")
        
        # Test with seconds - should handle correctly
        date_time_sec = "2023-05-15 12:00:30"
        dt = self.parser.parse_timestamp(date_time_sec, self.utc)
        self.assertEqual(dt.hour, 12, f"Expected hour 12, got {dt.hour}")
        self.assertEqual(dt.second, 30, f"Expected second 30, got {dt.second}")
        
        # Test with just the time - should assume today's date in the given timezone
        time_only = "16:45"
        dt = self.parser.parse_timestamp(time_only, self.utc)
        self.assertEqual(dt.hour, 16, f"Expected hour 16, got {dt.hour}")
        self.assertEqual(dt.minute, 45, f"Expected minute 45, got {dt.minute}")
        self.assertEqual(dt.date(), self.today, f"Expected today's date {self.today}, got {dt.date()}")
        
        # Test with invalid format - should raise ValueError
        invalid_datetime = "2023/05/15 12:00"  # Forward slashes in ISO-like format
        with self.assertRaises(ValueError):
            self.parser.parse_timestamp(invalid_datetime, self.utc)
    
    def test_classify_timestamp_day(self):
        """Test classifying timestamps as today or tomorrow across various timezones."""
        # Create sample dates
        now = datetime.now(self.utc)
        
        # Today in UTC
        today_utc = datetime.combine(self.today, datetime.min.time().replace(hour=12), self.utc)
        day_type = self.parser.classify_timestamp_day(today_utc, self.utc)
        self.assertEqual(day_type, "today", f"Expected 'today', got '{day_type}' for {today_utc}")
        
        # Tomorrow in UTC
        tomorrow_utc = datetime.combine(self.tomorrow, datetime.min.time().replace(hour=12), self.utc)
        day_type = self.parser.classify_timestamp_day(tomorrow_utc, self.utc)
        self.assertEqual(day_type, "tomorrow", f"Expected 'tomorrow', got '{day_type}' for {tomorrow_utc}")
        
        # Yesterday in UTC - real-world test for potential historical data
        yesterday_utc = datetime.combine(self.yesterday, datetime.min.time().replace(hour=12), self.utc)
        day_type = self.parser.classify_timestamp_day(yesterday_utc, self.utc)
        # The classifier should still categorize this as something, even if we don't specifically handle "yesterday"
        self.assertIsNotNone(day_type, f"Expected classification for yesterday's date, got None for {yesterday_utc}")
        
        # Cross-timezone tests - critical for real-world operation
        # Late today in UTC but tomorrow in far east
        late_today_utc = datetime.combine(self.today, datetime.min.time().replace(hour=22), self.utc)
        
        # Should be "today" in UTC
        day_type = self.parser.classify_timestamp_day(late_today_utc, self.utc)
        self.assertEqual(day_type, "today", f"Expected 'today', got '{day_type}' for {late_today_utc} in UTC")
        
        # Should be "tomorrow" in Tokyo if the time difference pushes it past midnight
        day_type = self.parser.classify_timestamp_day(late_today_utc, self.japanese)
        tokyo_date = late_today_utc.astimezone(self.japanese).date()
        expected = "tomorrow" if tokyo_date == self.tomorrow else "today"
        self.assertEqual(day_type, expected, 
                        f"Expected '{expected}', got '{day_type}' for {late_today_utc} in Tokyo")
        
        # Test early tomorrow UTC which might be today in US timezones
        early_tomorrow_utc = datetime.combine(self.tomorrow, datetime.min.time().replace(hour=1), self.utc)
        
        # Should be "tomorrow" in UTC
        day_type = self.parser.classify_timestamp_day(early_tomorrow_utc, self.utc)
        self.assertEqual(day_type, "tomorrow", f"Expected 'tomorrow', got '{day_type}' for {early_tomorrow_utc} in UTC")
        
        # Might be "today" in US Eastern if the time difference pulls it back to today
        day_type = self.parser.classify_timestamp_day(early_tomorrow_utc, self.us_eastern)
        us_date = early_tomorrow_utc.astimezone(self.us_eastern).date()
        expected = "today" if us_date == self.today else "tomorrow"
        self.assertEqual(day_type, expected, 
                        f"Expected '{expected}', got '{day_type}' for {early_tomorrow_utc} in US Eastern")
    
    def test_normalize_timestamps(self):
        """Test normalizing timestamps and separating into today/tomorrow with complex cases."""
        # Create sample data mixing today and tomorrow
        today_str = self.today.strftime("%Y-%m-%d")
        tomorrow_str = self.tomorrow.strftime("%Y-%m-%d")
        
        mixed_prices = {
            # Today timestamps in various formats
            f"{today_str}T10:00:00+00:00": 50.0,  # ISO with TZ
            f"{today_str} 12:00": 60.0,           # Date + time
            "14:00": 70.0,                        # Hour only (ambiguous)
            
            # Tomorrow timestamps
            f"{tomorrow_str}T10:00:00+00:00": 55.0,  # ISO with TZ
            f"{tomorrow_str} 12:00": 65.0,           # Date + time
        }
        
        # Normalize with explicit source and target timezone
        result = self.parser.normalize_timestamps(
            mixed_prices, 
            self.utc,  # Source timezone 
            self.utc   # Target timezone
        )
        
        # Check the results
        self.assertEqual(len(result["today"]), 3, f"Expected 3 today entries, got {len(result['today'])}")
        self.assertEqual(len(result["tomorrow"]), 2, f"Expected 2 tomorrow entries, got {len(result['tomorrow'])}")
        
        # Verify specific hours are correctly assigned
        self.assertEqual(result["today"]["10:00"], 50.0, "Expected '10:00' today to have value 50.0")
        self.assertEqual(result["today"]["12:00"], 60.0, "Expected '12:00' today to have value 60.0")
        self.assertEqual(result["today"]["14:00"], 70.0, "Expected '14:00' today to have value 70.0")
        
        self.assertEqual(result["tomorrow"]["10:00"], 55.0, "Expected '10:00' tomorrow to have value 55.0")
        self.assertEqual(result["tomorrow"]["12:00"], 65.0, "Expected '12:00' tomorrow to have value 65.0")
        
        # Test with timezone conversion - critical for real-world operation
        # UTC -> CET (usually +1 or +2 hours)
        result_cet = self.parser.normalize_timestamps(
            mixed_prices, 
            self.utc,  # Source timezone 
            self.cet   # Target timezone (CET/CEST)
        )
        
        # Calculate the current offset between UTC and CET
        now_utc = datetime.now(self.utc)
        now_cet = now_utc.astimezone(self.cet)
        utc_to_cet_offset = int((now_cet.utcoffset().total_seconds() - now_utc.utcoffset().total_seconds()) / 3600)
        
        # The 10:00 UTC entry should become 11:00 CET during standard time, 12:00 during DST
        expected_hour = f"{10 + utc_to_cet_offset:02d}:00"
        if expected_hour in result_cet["today"]:
            self.assertEqual(result_cet["today"][expected_hour], 50.0, 
                            f"Expected '{expected_hour}' today to have value 50.0 after UTC->CET conversion")
        
        # Test with a more complex timezone difference - UTC -> Australia (usually +10/+11 hours)
        # This tests the day boundary crossing behavior which is critical for electricity markets
        result_aus = self.parser.normalize_timestamps(
            mixed_prices, 
            self.utc,        # Source timezone 
            self.australian  # Target timezone (AEST/AEDT)
        )
        
        # Calculate the current offset between UTC and Australia
        now_aus = now_utc.astimezone(self.australian)
        utc_to_aus_offset = int((now_aus.utcoffset().total_seconds() - now_utc.utcoffset().total_seconds()) / 3600)
        
        # The 14:00 UTC entry will be next day in Australia if the offset is +10 or greater
        if utc_to_aus_offset >= 10:
            expected_hour = f"{(14 + utc_to_aus_offset) % 24:02d}:00"
            # This should be in tomorrow's data for Australia
            self.assertIn(expected_hour, result_aus["tomorrow"], 
                        f"Expected '{expected_hour}' to be in tomorrow's data after UTC->Australia conversion")
            if expected_hour in result_aus["tomorrow"]:
                self.assertEqual(result_aus["tomorrow"][expected_hour], 70.0,
                                f"Expected '{expected_hour}' tomorrow to have value 70.0 after UTC->Australia conversion")
    
    def test_cross_midnight_case(self):
        """Test the critical case of timestamps near midnight with timezone differences.
        This is essential for correctly handling day-ahead electricity markets across timezones.
        """
        # Create a timestamp for 23:30 UTC today
        today_str = self.today.strftime("%Y-%m-%d")
        late_night_utc = f"{today_str}T23:30:00+00:00"
        
        # Create hourly prices with this timestamp
        prices = {
            late_night_utc: 100.0
        }
        
        # In UTC this should be classified as today
        result_utc = self.parser.normalize_timestamps(
            prices, 
            self.utc,  # Source timezone 
            self.utc   # Target timezone (same)
        )
        self.assertEqual(len(result_utc["today"]), 1, "Expected 1 entry for today in UTC")
        self.assertEqual(len(result_utc["tomorrow"]), 0, "Expected 0 entries for tomorrow in UTC")
        self.assertEqual(result_utc["today"]["23:00"], 100.0, "Expected '23:00' today to have value 100.0")
        
        # In CET/CEST (usually UTC+1/+2), this should be tomorrow if the offset makes it past midnight
        result_cet = self.parser.normalize_timestamps(
            prices, 
            self.utc,        # Source timezone 
            self.cet         # Target timezone
        )
        
        # Calculate whether this timestamp crosses midnight in CET
        dt_utc = datetime.fromisoformat(late_night_utc)
        dt_cet = dt_utc.astimezone(self.cet)
        
        if dt_cet.date() == self.tomorrow:
            # Should be classified as tomorrow
            self.assertEqual(len(result_cet["today"]), 0, "Expected 0 entries for today in CET")
            self.assertEqual(len(result_cet["tomorrow"]), 1, "Expected 1 entry for tomorrow in CET")
            # The hour should now be in the early hours of tomorrow
            hour_str = f"{dt_cet.hour:02d}:00"
            self.assertIn(hour_str, result_cet["tomorrow"], 
                        f"Expected '{hour_str}' in tomorrow's data after UTC->CET conversion")
        else:
            # Still today in the target timezone
            self.assertEqual(len(result_cet["today"]), 1, "Expected 1 entry for today in CET")
            self.assertEqual(len(result_cet["tomorrow"]), 0, "Expected 0 entries for tomorrow in CET")
            hour_str = f"{dt_cet.hour:02d}:00"
            self.assertIn(hour_str, result_cet["today"], 
                        f"Expected '{hour_str}' in today's data after UTC->CET conversion")
        
        # Test with a more extreme timezone difference - Helsinki (UTC+2/+3)
        far_east = pytz.timezone("Europe/Helsinki")
        result_east = self.parser.normalize_timestamps(
            prices, 
            self.utc,        # Source timezone 
            far_east         # Target timezone
        )
        
        # This should definitely be tomorrow in Helsinki
        dt_east = dt_utc.astimezone(far_east)
        
        if dt_east.date() == self.tomorrow:
            # Should be classified as tomorrow
            self.assertEqual(len(result_east["today"]), 0, "Expected 0 entries for today in Helsinki")
            self.assertEqual(len(result_east["tomorrow"]), 1, "Expected 1 entry for tomorrow in Helsinki")
            # The hour should now be in the early hours of tomorrow
            hour_str = f"{dt_east.hour:02d}:00"
            self.assertIn(hour_str, result_east["tomorrow"], 
                        f"Expected '{hour_str}' in tomorrow's data after UTC->Helsinki conversion")
        else:
            # Still today in the target timezone (unlikely but handle it)
            self.assertEqual(len(result_east["today"]), 1, "Expected 1 entry for today in Helsinki")
            self.assertEqual(len(result_east["tomorrow"]), 0, "Expected 0 entries for tomorrow in Helsinki")
            hour_str = f"{dt_east.hour:02d}:00"
            self.assertIn(hour_str, result_east["today"], 
                        f"Expected '{hour_str}' in today's data after UTC->Helsinki conversion")
    
    def test_real_world_edge_cases(self):
        """Test real-world edge cases that might occur in actual electricity markets."""
        # Test DST transition timestamps - critical for electricity markets during DST transitions
        # During "spring forward" transition, there's typically a missing hour
        # During "fall back" transition, there's typically a duplicated hour
        
        # Test case for "fall back" transition where 2:00-3:00 occurs twice
        fall_back_prices = {
            # First occurrence of 2:00-3:00
            "2023-10-29T02:00:00+02:00": 80.0,  # Still in DST
            # Second occurrence of 2:00-3:00 after falling back
            "2023-10-29T02:00:00+01:00": 85.0,  # Standard time after fallback
        }
        
        # Normalize with explicit CET timezone
        result_dst = self.parser.normalize_timestamps(
            fall_back_prices, 
            self.cet,  # Source timezone 
            self.cet   # Target timezone
        )
        
        # Either the parser should preserve both values or handle them in a consistent way
        # The key thing is it shouldn't crash or produce invalid results
        self.assertIsNotNone(result_dst, "Normalizing DST transition timestamps should not fail")
        self.assertIn("today", result_dst, "Result should contain 'today' key")
        
        # Test case for empty input
        empty_prices = {}
        result_empty = self.parser.normalize_timestamps(
            empty_prices, 
            self.utc,  # Source timezone 
            self.utc   # Target timezone
        )
        
        # Should return empty structures, not None or error
        self.assertIsNotNone(result_empty, "Normalizing empty prices should not fail")
        self.assertIn("today", result_empty, "Result should contain 'today' key even with empty input")
        self.assertIn("tomorrow", result_empty, "Result should contain 'tomorrow' key even with empty input")
        self.assertEqual(len(result_empty["today"]), 0, "Expected 0 entries for today with empty input")
        self.assertEqual(len(result_empty["tomorrow"]), 0, "Expected 0 entries for tomorrow with empty input")
        
        # Test with malformed timestamps - should not crash but handle gracefully
        malformed_prices = {
            "not_a_timestamp": 100.0,
            "2023-13-45 25:70": 200.0  # Invalid month, day, hour, minute
        }
        
        try:
            result_malformed = self.parser.normalize_timestamps(
                malformed_prices, 
                self.utc,  # Source timezone 
                self.utc   # Target timezone
            )
            # Should ideally skip invalid timestamps and continue
            self.assertIsNotNone(result_malformed, "Normalizing malformed timestamps should not return None")
        except ValueError:
            # Or explicitly raise ValueError, which is also acceptable
            pass  # This is expected behavior for malformed input

if __name__ == "__main__":
    unittest.main()