#!/usr/bin/env python3
"""Unit tests for the date range utility.

This script tests the date range utility with different parameters to ensure
it works correctly in various real-world scenarios. These tests should identify
actual issues in the date range code rather than being adapted to pass validation.
If a test fails, investigate and fix the core code.
"""
import sys
import os
import unittest
import logging
from datetime import datetime, timezone, timedelta
import pytz

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path so we can import the custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from custom_components.ge_spot.utils.date_range import generate_date_ranges
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.time import TimeInterval

class DateRangeUtilityTests(unittest.TestCase):
    """Unit tests for the date range utility to identify real issues."""

    def setUp(self):
        """Set up test fixtures with real-world scenarios."""
        # Fixed reference time for consistent testing
        self.reference_time = datetime(2025, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
        logger.info(f"Using reference time: {self.reference_time.isoformat()}")
        
        # Add additional reference times for edge cases
        self.reference_time_midnight = datetime(2025, 4, 17, 0, 0, 0, tzinfo=timezone.utc)
        self.reference_time_almost_midnight = datetime(2025, 4, 17, 23, 59, 59, tzinfo=timezone.utc)
        
        # Reference time with non-UTC timezone for testing timezone handling
        self.cet_tz = pytz.timezone("Europe/Stockholm")
        self.reference_time_cet = datetime(2025, 4, 17, 12, 0, 0, tzinfo=self.cet_tz)
        
    def _log_date_ranges(self, date_ranges, test_name, source=None):
        """Log date ranges for debugging."""
        source_str = f" for {source}" if source else ""
        logger.info(f"Test: {test_name}{source_str} - Generated {len(date_ranges)} date ranges:")
        for i, (start, end) in enumerate(date_ranges):
            logger.info(f"  Range {i+1}: {start.isoformat()} to {end.isoformat()}")

    def test_default_parameters(self):
        """Test the date range utility with default parameters."""
        date_ranges = generate_date_ranges(self.reference_time)
        self._log_date_ranges(date_ranges, "Default Parameters")
        
        # Validate number of date ranges
        self.assertEqual(len(date_ranges), 4, 
                        f"Expected 4 date ranges with default parameters, got {len(date_ranges)}")
        
        # Validate first range - today to tomorrow
        first_range_start, first_range_end = date_ranges[0]
        self.assertEqual(first_range_start.date(), self.reference_time.date(), 
                        f"First range start should be today ({self.reference_time.date()}), got {first_range_start.date()}")
        self.assertEqual(first_range_end.date(), (self.reference_time + timedelta(days=1)).date(), 
                        f"First range end should be tomorrow ({(self.reference_time + timedelta(days=1)).date()}), got {first_range_end.date()}")
        
        # Validate second range - yesterday to today
        second_range_start, second_range_end = date_ranges[1]
        self.assertEqual(second_range_start.date(), (self.reference_time - timedelta(days=1)).date(), 
                        f"Second range start should be yesterday ({(self.reference_time - timedelta(days=1)).date()}), got {second_range_start.date()}")
        self.assertEqual(second_range_end.date(), self.reference_time.date(), 
                        f"Second range end should be today ({self.reference_time.date()}), got {second_range_end.date()}")
        
        # Validate third range - today to day after tomorrow
        third_range_start, third_range_end = date_ranges[2]
        self.assertEqual(third_range_start.date(), self.reference_time.date(), 
                        f"Third range start should be today ({self.reference_time.date()}), got {third_range_start.date()}")
        self.assertEqual(third_range_end.date(), (self.reference_time + timedelta(days=2)).date(), 
                        f"Third range end should be day after tomorrow ({(self.reference_time + timedelta(days=2)).date()}), got {third_range_end.date()}")
        
        # Validate fourth range - 2 days ago to 2 days ahead
        fourth_range_start, fourth_range_end = date_ranges[3]
        self.assertEqual(fourth_range_start.date(), (self.reference_time - timedelta(days=2)).date(), 
                        f"Fourth range start should be 2 days ago ({(self.reference_time - timedelta(days=2)).date()}), got {fourth_range_start.date()}")
        self.assertEqual(fourth_range_end.date(), (self.reference_time + timedelta(days=2)).date(), 
                        f"Fourth range end should be 2 days ahead ({(self.reference_time + timedelta(days=2)).date()}), got {fourth_range_end.date()}")

    def test_entsoe_source(self):
        """Test the date range utility with ENTSO-E source for real-world operation."""
        date_ranges = generate_date_ranges(self.reference_time, Source.ENTSOE)
        self._log_date_ranges(date_ranges, "API-specific Parameters", Source.ENTSOE)
        
        # ENTSO-E needs specific data ranges for day-ahead market data
        # Should generate 5 date ranges for ENTSO-E
        self.assertEqual(len(date_ranges), 5, 
                        f"Expected 5 date ranges for ENTSO-E, got {len(date_ranges)}")
        
        # Check each range has the correct structure
        for i, (start, end) in enumerate(date_ranges):
            # Verify ranges are properly structured (end is after start)
            self.assertLess(start, end, 
                           f"Range {i+1}: start time ({start}) should be before end time ({end})")
            
            # Verify each date range preserves the timezone
            self.assertEqual(start.tzinfo, self.reference_time.tzinfo, 
                           f"Range {i+1}: start timezone ({start.tzinfo}) should match reference timezone ({self.reference_time.tzinfo})")
            self.assertEqual(end.tzinfo, self.reference_time.tzinfo, 
                           f"Range {i+1}: end timezone ({end.tzinfo}) should match reference timezone ({self.reference_time.tzinfo})")
        
        # Check that the extra range is included (today to max_days_forward)
        # This is critical for ENTSO-E which provides day-ahead data
        fourth_range_start, fourth_range_end = date_ranges[3]
        self.assertEqual(fourth_range_start.date(), self.reference_time.date(), 
                        f"Fourth range start should be today ({self.reference_time.date()}), got {fourth_range_start.date()}")
        self.assertEqual(fourth_range_end.date(), (self.reference_time + timedelta(days=2)).date(), 
                        f"Fourth range end should be 2 days ahead ({(self.reference_time + timedelta(days=2)).date()}), got {fourth_range_end.date()}")

    def test_aemo_source(self):
        """Test the date range utility with AEMO source (5-minute intervals) for Australian market."""
        date_ranges = generate_date_ranges(self.reference_time, Source.AEMO)
        self._log_date_ranges(date_ranges, "API-specific Parameters", Source.AEMO)
        
        # Should generate 5 date ranges for AEMO
        self.assertEqual(len(date_ranges), 5, 
                        f"Expected 5 date ranges for AEMO, got {len(date_ranges)}")
        
        # Check that the times are rounded to 5-minute intervals
        # This is critical for AEMO which operates on 5-minute settlement periods
        for i, (start, end) in enumerate(date_ranges):
            self.assertEqual(start.minute % 5, 0, 
                           f"Range {i+1}: start minute ({start.minute}) should be a multiple of 5")
            self.assertEqual(start.second, 0, 
                           f"Range {i+1}: start second ({start.second}) should be 0")
            self.assertEqual(start.microsecond, 0, 
                           f"Range {i+1}: start microsecond ({start.microsecond}) should be 0")
            self.assertEqual(end.minute % 5, 0, 
                           f"Range {i+1}: end minute ({end.minute}) should be a multiple of 5")
            self.assertEqual(end.second, 0, 
                           f"Range {i+1}: end second ({end.second}) should be 0")
            self.assertEqual(end.microsecond, 0, 
                           f"Range {i+1}: end microsecond ({end.microsecond}) should be 0")

    def test_comed_source(self):
        """Test the date range utility with ComEd source (5-minute intervals) for US market."""
        date_ranges = generate_date_ranges(self.reference_time, Source.COMED)
        self._log_date_ranges(date_ranges, "API-specific Parameters", Source.COMED)
        
        # Should generate 5 date ranges for ComEd
        self.assertEqual(len(date_ranges), 5, 
                        f"Expected 5 date ranges for ComEd, got {len(date_ranges)}")
        
        # Check that the times are rounded to 5-minute intervals
        # This is critical for ComEd which provides 5-minute pricing data
        for i, (start, end) in enumerate(date_ranges):
            self.assertEqual(start.minute % 5, 0, 
                           f"Range {i+1}: start minute ({start.minute}) should be a multiple of 5")
            self.assertEqual(start.second, 0, 
                           f"Range {i+1}: start second ({start.second}) should be 0")
            self.assertEqual(start.microsecond, 0, 
                           f"Range {i+1}: start microsecond ({start.microsecond}) should be 0")
            self.assertEqual(end.minute % 5, 0, 
                           f"Range {i+1}: end minute ({end.minute}) should be a multiple of 5")
            self.assertEqual(end.second, 0, 
                           f"Range {i+1}: end second ({end.second}) should be 0")
            self.assertEqual(end.microsecond, 0, 
                           f"Range {i+1}: end microsecond ({end.microsecond}) should be 0")

    def test_quarter_hourly_interval(self):
        """Test the date range utility with quarter-hourly interval for European markets."""
        date_ranges = generate_date_ranges(self.reference_time, interval=TimeInterval.QUARTER_HOURLY)
        self._log_date_ranges(date_ranges, "Quarter-hourly Interval")
        
        # Should generate 4 date ranges by default
        self.assertEqual(len(date_ranges), 4, 
                        f"Expected 4 date ranges with quarter-hourly interval, got {len(date_ranges)}")
        
        # Check that the times are rounded to 15-minute intervals
        # This is critical for markets with 15-minute settlement periods like some European markets
        for i, (start, end) in enumerate(date_ranges):
            self.assertEqual(start.minute % 15, 0, 
                           f"Range {i+1}: start minute ({start.minute}) should be a multiple of 15")
            self.assertEqual(start.second, 0, 
                           f"Range {i+1}: start second ({start.second}) should be 0")
            self.assertEqual(start.microsecond, 0, 
                           f"Range {i+1}: start microsecond ({start.microsecond}) should be 0")
            self.assertEqual(end.minute % 15, 0, 
                           f"Range {i+1}: end minute ({end.minute}) should be a multiple of 15")
            self.assertEqual(end.second, 0, 
                           f"Range {i+1}: end second ({end.second}) should be 0")
            self.assertEqual(end.microsecond, 0, 
                           f"Range {i+1}: end microsecond ({end.microsecond}) should be 0")

    def test_custom_parameters(self):
        """Test the date range utility with custom parameters for specific market needs."""
        date_ranges = generate_date_ranges(
            self.reference_time,
            Source.NORDPOOL,
            include_historical=True,
            include_future=True,
            max_days_back=3,
            max_days_forward=3
        )
        self._log_date_ranges(date_ranges, "Custom Parameters", Source.NORDPOOL)
        
        # Should generate 5 date ranges for Nordpool with custom parameters
        self.assertEqual(len(date_ranges), 5, 
                        f"Expected 5 date ranges for Nordpool with custom parameters, got {len(date_ranges)}")
        
        # Check that the wider range uses the custom max_days parameters
        # This is important for retrieving longer historical or future data
        fifth_range_start, fifth_range_end = date_ranges[4]
        self.assertEqual(fifth_range_start.date(), (self.reference_time - timedelta(days=3)).date(), 
                        f"Fifth range start should be 3 days ago ({(self.reference_time - timedelta(days=3)).date()}), got {fifth_range_start.date()}")
        self.assertEqual(fifth_range_end.date(), (self.reference_time + timedelta(days=3)).date(), 
                        f"Fifth range end should be 3 days ahead ({(self.reference_time + timedelta(days=3)).date()}), got {fifth_range_end.date()}")

    def test_no_historical(self):
        """Test the date range utility with no historical data for future-only APIs."""
        date_ranges = generate_date_ranges(
            self.reference_time,
            include_historical=False
        )
        self._log_date_ranges(date_ranges, "No Historical Data")
        
        # Should generate 3 date ranges without historical data
        # (standard, future, and wider range)
        self.assertEqual(len(date_ranges), 3, 
                        f"Expected 3 date ranges without historical data, got {len(date_ranges)}")
        
        # Validate each range
        first_range_start, first_range_end = date_ranges[0]
        second_range_start, second_range_end = date_ranges[1]
        third_range_start, third_range_end = date_ranges[2]
        
        # First range should be today to tomorrow (standard)
        self.assertEqual(first_range_start.date(), self.reference_time.date(), 
                        f"First range start should be today ({self.reference_time.date()}), got {first_range_start.date()}")
        self.assertEqual(first_range_end.date(), (self.reference_time + timedelta(days=1)).date(), 
                        f"First range end should be tomorrow ({(self.reference_time + timedelta(days=1)).date()}), got {first_range_end.date()}")
        
        # Second range should be today to day after tomorrow (future)
        self.assertEqual(second_range_start.date(), self.reference_time.date(), 
                        f"Second range start should be today ({self.reference_time.date()}), got {second_range_start.date()}")
        self.assertEqual(second_range_end.date(), (self.reference_time + timedelta(days=2)).date(), 
                        f"Second range end should be day after tomorrow ({(self.reference_time + timedelta(days=2)).date()}), got {second_range_end.date()}")
        
        # Third range should be the wider range (should include some historical data for context)
        # This tests that the wider range still works as expected
        self.assertEqual(third_range_start.date(), (self.reference_time - timedelta(days=2)).date(), 
                        f"Third range start should be 2 days ago ({(self.reference_time - timedelta(days=2)).date()}), got {third_range_start.date()}")
        self.assertEqual(third_range_end.date(), (self.reference_time + timedelta(days=2)).date(), 
                        f"Third range end should be 2 days ahead ({(self.reference_time + timedelta(days=2)).date()}), got {third_range_end.date()}")

    def test_no_future(self):
        """Test the date range utility with no future data for historical-only APIs."""
        date_ranges = generate_date_ranges(
            self.reference_time,
            include_future=False
        )
        self._log_date_ranges(date_ranges, "No Future Data")
        
        # Should generate 3 date ranges without future data
        # (standard, historical, and wider range)
        self.assertEqual(len(date_ranges), 3, 
                        f"Expected 3 date ranges without future data, got {len(date_ranges)}")
        
        # Validate each range
        first_range_start, first_range_end = date_ranges[0]
        second_range_start, second_range_end = date_ranges[1]
        third_range_start, third_range_end = date_ranges[2]
        
        # First range should be today to tomorrow (standard)
        self.assertEqual(first_range_start.date(), self.reference_time.date(), 
                        f"First range start should be today ({self.reference_time.date()}), got {first_range_start.date()}")
        self.assertEqual(first_range_end.date(), (self.reference_time + timedelta(days=1)).date(), 
                        f"First range end should be tomorrow ({(self.reference_time + timedelta(days=1)).date()}), got {first_range_end.date()}")
        
        # Second range should be yesterday to today (historical)
        self.assertEqual(second_range_start.date(), (self.reference_time - timedelta(days=1)).date(), 
                        f"Second range start should be yesterday ({(self.reference_time - timedelta(days=1)).date()}), got {second_range_start.date()}")
        self.assertEqual(second_range_end.date(), self.reference_time.date(), 
                        f"Second range end should be today ({self.reference_time.date()}), got {second_range_end.date()}")
        
        # Third range should be the wider range (still includes future data for context)
        # This tests that the wider range still works as expected
        self.assertEqual(third_range_start.date(), (self.reference_time - timedelta(days=2)).date(), 
                        f"Third range start should be 2 days ago ({(self.reference_time - timedelta(days=2)).date()}), got {third_range_start.date()}")
        self.assertEqual(third_range_end.date(), (self.reference_time + timedelta(days=2)).date(), 
                        f"Third range end should be 2 days ahead ({(self.reference_time + timedelta(days=2)).date()}), got {third_range_end.date()}")

    def test_edge_case_midnight(self):
        """Test with reference time at midnight - important edge case for day boundaries."""
        date_ranges = generate_date_ranges(self.reference_time_midnight)
        self._log_date_ranges(date_ranges, "Midnight Reference Time")
        
        # Validate number of date ranges
        self.assertEqual(len(date_ranges), 4, 
                        f"Expected 4 date ranges with midnight reference time, got {len(date_ranges)}")
        
        # First range should still be today to tomorrow even at midnight
        first_range_start, first_range_end = date_ranges[0]
        self.assertEqual(first_range_start.date(), self.reference_time_midnight.date(), 
                        f"First range start should be today ({self.reference_time_midnight.date()}), got {first_range_start.date()}")
        self.assertEqual(first_range_end.date(), (self.reference_time_midnight + timedelta(days=1)).date(), 
                        f"First range end should be tomorrow ({(self.reference_time_midnight + timedelta(days=1)).date()}), got {first_range_end.date()}")

    def test_edge_case_almost_midnight(self):
        """Test with reference time just before midnight - important edge case for day boundaries."""
        date_ranges = generate_date_ranges(self.reference_time_almost_midnight)
        self._log_date_ranges(date_ranges, "Almost Midnight Reference Time")
        
        # Validate number of date ranges
        self.assertEqual(len(date_ranges), 4, 
                        f"Expected 4 date ranges with almost midnight reference time, got {len(date_ranges)}")
        
        # First range should still be today to tomorrow even at 23:59:59
        first_range_start, first_range_end = date_ranges[0]
        self.assertEqual(first_range_start.date(), self.reference_time_almost_midnight.date(), 
                        f"First range start should be today ({self.reference_time_almost_midnight.date()}), got {first_range_start.date()}")
        self.assertEqual(first_range_end.date(), (self.reference_time_almost_midnight + timedelta(days=1)).date(), 
                        f"First range end should be tomorrow ({(self.reference_time_almost_midnight + timedelta(days=1)).date()}), got {first_range_end.date()}")

    def test_different_timezone(self):
        """Test with reference time in different timezone - critical for international markets."""
        date_ranges = generate_date_ranges(self.reference_time_cet)
        self._log_date_ranges(date_ranges, "CET Timezone Reference Time")
        
        # Validate number of date ranges
        self.assertEqual(len(date_ranges), 4, 
                        f"Expected 4 date ranges with CET reference time, got {len(date_ranges)}")
        
        # First range should preserve the original timezone
        first_range_start, first_range_end = date_ranges[0]
        
        # Check that timezone is preserved
        self.assertEqual(first_range_start.tzinfo, self.reference_time_cet.tzinfo, 
                        f"First range start timezone should be {self.reference_time_cet.tzinfo}, got {first_range_start.tzinfo}")
        self.assertEqual(first_range_end.tzinfo, self.reference_time_cet.tzinfo, 
                        f"First range end timezone should be {self.reference_time_cet.tzinfo}, got {first_range_end.tzinfo}")
        
        # Dates should still be correct in the local timezone
        self.assertEqual(first_range_start.date(), self.reference_time_cet.date(), 
                        f"First range start should be today in CET ({self.reference_time_cet.date()}), got {first_range_start.date()}")
        self.assertEqual(first_range_end.date(), (self.reference_time_cet + timedelta(days=1)).date(), 
                        f"First range end should be tomorrow in CET ({(self.reference_time_cet + timedelta(days=1)).date()}), got {first_range_end.date()}")

if __name__ == "__main__":
    unittest.main()
