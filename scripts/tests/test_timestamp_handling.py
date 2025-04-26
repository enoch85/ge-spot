"""Test file for timestamp handling in BasePriceParser."""
import unittest
from datetime import datetime, timezone, timedelta
import pytz

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
        
        # Define timezones for testing
        self.utc = timezone.utc
        self.cet = pytz.timezone("Europe/Stockholm")  # CET/CEST
        self.us_eastern = pytz.timezone("America/New_York")  # EST/EDT
        
        # Define test dates
        self.today = datetime.now(self.utc).date()
        self.tomorrow = self.today + timedelta(days=1)
    
    def test_parse_timestamp_iso(self):
        """Test parsing ISO format timestamps."""
        # ISO with timezone
        iso_tz = f"2023-05-15T12:00:00+00:00"
        dt = self.parser.parse_timestamp(iso_tz, self.utc)
        self.assertEqual(dt.hour, 12)
        self.assertEqual(dt.date(), datetime(2023, 5, 15).date())
        self.assertEqual(dt.tzinfo, timezone.utc)
        
        # ISO without timezone
        iso_no_tz = f"2023-05-15T14:00:00"
        dt = self.parser.parse_timestamp(iso_no_tz, self.cet)
        self.assertEqual(dt.hour, 14)
        self.assertEqual(dt.date(), datetime(2023, 5, 15).date())
        self.assertEqual(dt.tzinfo, self.cet)
    
    def test_parse_timestamp_date_time(self):
        """Test parsing date + time format timestamps."""
        # Standard format
        date_time = "2023-05-15 12:00"
        dt = self.parser.parse_timestamp(date_time, self.utc)
        self.assertEqual(dt.hour, 12)
        self.assertEqual(dt.date(), datetime(2023, 5, 15).date())
        self.assertEqual(dt.tzinfo, self.utc)
        
        # European format
        euro_date = "15.05.2023 14:30"
        dt = self.parser.parse_timestamp(euro_date, self.cet)
        self.assertEqual(dt.hour, 14)
        self.assertEqual(dt.minute, 30)
        self.assertEqual(dt.date(), datetime(2023, 5, 15).date())
        self.assertEqual(dt.tzinfo, self.cet)
        
        # US format
        us_date = "05/15/2023 10:45"
        dt = self.parser.parse_timestamp(us_date, self.us_eastern)
        self.assertEqual(dt.hour, 10)
        self.assertEqual(dt.minute, 45)
        self.assertEqual(dt.date(), datetime(2023, 5, 15).date())
        self.assertEqual(dt.tzinfo, self.us_eastern)
    
    def test_classify_timestamp_day(self):
        """Test classifying timestamps as today or tomorrow."""
        # Create sample dates
        now = datetime.now(self.utc)
        
        # Today in UTC
        today_utc = datetime.combine(self.today, datetime.min.time().replace(hour=12), self.utc)
        day_type = self.parser.classify_timestamp_day(today_utc, self.utc)
        self.assertEqual(day_type, "today")
        
        # Tomorrow in UTC
        tomorrow_utc = datetime.combine(self.tomorrow, datetime.min.time().replace(hour=12), self.utc)
        day_type = self.parser.classify_timestamp_day(tomorrow_utc, self.utc)
        self.assertEqual(day_type, "tomorrow")
        
        # Cross-timezone tests - late today in UTC but tomorrow in far east
        late_today_utc = datetime.combine(self.today, datetime.min.time().replace(hour=22), self.utc)
        
        # Should be "today" in UTC
        day_type = self.parser.classify_timestamp_day(late_today_utc, self.utc)
        self.assertEqual(day_type, "today")
        
        # Should be "tomorrow" in Tokyo (+9)
        tokyo = pytz.timezone("Asia/Tokyo")
        day_type = self.parser.classify_timestamp_day(late_today_utc, tokyo)
        # This might be "tomorrow" if Tokyo is already in the next day
        tokyo_date = late_today_utc.astimezone(tokyo).date()
        expected = "tomorrow" if tokyo_date == self.tomorrow else "today"
        self.assertEqual(day_type, expected)
    
    def test_normalize_timestamps(self):
        """Test normalizing timestamps and separating into today/tomorrow."""
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
        self.assertEqual(len(result["today"]), 3)
        self.assertEqual(len(result["tomorrow"]), 2)
        
        # Verify specific hours
        self.assertEqual(result["today"]["10:00"], 50.0)
        self.assertEqual(result["today"]["12:00"], 60.0)
        self.assertEqual(result["today"]["14:00"], 70.0)
        
        self.assertEqual(result["tomorrow"]["10:00"], 55.0)
        self.assertEqual(result["tomorrow"]["12:00"], 65.0)
        
        # Test with different target timezone
        result_cet = self.parser.normalize_timestamps(
            mixed_prices, 
            self.utc,  # Source timezone 
            self.cet   # Target timezone (CET/CEST)
        )
        
        # Hours should be shifted by timezone difference
        # UTC+0 10:00 -> CET+1 11:00
        if "11:00" in result_cet["today"]:
            self.assertEqual(result_cet["today"]["11:00"], 50.0)
        
    def test_cross_midnight_case(self):
        """Test the critical case of timestamps near midnight with timezone differences."""
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
        self.assertEqual(len(result_utc["today"]), 1)
        self.assertEqual(len(result_utc["tomorrow"]), 0)
        self.assertEqual(result_utc["today"]["23:00"], 100.0)
        
        # In a timezone +2 or more ahead of UTC, this should be tomorrow
        far_east = pytz.timezone("Europe/Helsinki")  # UTC+2/3
        result_east = self.parser.normalize_timestamps(
            prices, 
            self.utc,        # Source timezone 
            far_east         # Target timezone (ahead of UTC)
        )
        
        # Should be tomorrow in Helsinki if the time difference pushes it to 01:30
        # Check the correct classification first
        dt_utc = datetime.fromisoformat(late_night_utc)
        dt_east = dt_utc.astimezone(far_east)
        
        if dt_east.date() == self.tomorrow:
            # Should be classified as tomorrow
            self.assertEqual(len(result_east["today"]), 0)
            self.assertEqual(len(result_east["tomorrow"]), 1)
            # The hour should now be in the early hours of tomorrow
            self.assertIn(f"{dt_east.hour:02d}:00", result_east["tomorrow"])
        else:
            # Still today in the target timezone
            self.assertEqual(len(result_east["today"]), 1)
            self.assertEqual(len(result_east["tomorrow"]), 0)
            self.assertIn(f"{dt_east.hour:02d}:00", result_east["today"])

if __name__ == "__main__":
    unittest.main() 