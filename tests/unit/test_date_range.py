#!/usr/bin/env python3
"""Unit tests for the date range utility.

This script tests the date range utility with different parameters to ensure
it works correctly in various scenarios.
"""
import sys
import os
import unittest
import logging
from datetime import datetime, timezone, timedelta

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
    """Unit tests for the date range utility."""

    def setUp(self):
        """Set up test fixtures."""
        # Use a fixed reference time for consistent testing
        self.reference_time = datetime(2025, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
        logger.info(f"Using reference time: {self.reference_time.isoformat()}")
        
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
        
        # Should generate 4 date ranges by default
        self.assertEqual(len(date_ranges), 4)
        
        # First range should be today to tomorrow
        self.assertEqual(date_ranges[0][0].date(), self.reference_time.date())
        self.assertEqual(date_ranges[0][1].date(), (self.reference_time + timedelta(days=1)).date())
        
        # Second range should be yesterday to today
        self.assertEqual(date_ranges[1][0].date(), (self.reference_time - timedelta(days=1)).date())
        self.assertEqual(date_ranges[1][1].date(), self.reference_time.date())
        
        # Third range should be today to day after tomorrow
        self.assertEqual(date_ranges[2][0].date(), self.reference_time.date())
        self.assertEqual(date_ranges[2][1].date(), (self.reference_time + timedelta(days=2)).date())
        
        # Fourth range should be 2 days ago to 2 days ahead
        self.assertEqual(date_ranges[3][0].date(), (self.reference_time - timedelta(days=2)).date())
        self.assertEqual(date_ranges[3][1].date(), (self.reference_time + timedelta(days=2)).date())

    def test_entsoe_source(self):
        """Test the date range utility with ENTSO-E source."""
        date_ranges = generate_date_ranges(self.reference_time, Source.ENTSOE)
        self._log_date_ranges(date_ranges, "API-specific Parameters", Source.ENTSOE)
        
        # Should generate 5 date ranges for ENTSO-E
        self.assertEqual(len(date_ranges), 5)
        
        # Check that the extra range is included (today to max_days_forward)
        self.assertEqual(date_ranges[3][0].date(), self.reference_time.date())
        self.assertEqual(date_ranges[3][1].date(), (self.reference_time + timedelta(days=2)).date())

    def test_aemo_source(self):
        """Test the date range utility with AEMO source (5-minute intervals)."""
        date_ranges = generate_date_ranges(self.reference_time, Source.AEMO)
        self._log_date_ranges(date_ranges, "API-specific Parameters", Source.AEMO)
        
        # Should generate 5 date ranges for AEMO
        self.assertEqual(len(date_ranges), 5)
        
        # Check that the times are rounded to 5-minute intervals
        for start, end in date_ranges:
            self.assertEqual(start.minute % 5, 0)
            self.assertEqual(start.second, 0)
            self.assertEqual(start.microsecond, 0)
            self.assertEqual(end.minute % 5, 0)
            self.assertEqual(end.second, 0)
            self.assertEqual(end.microsecond, 0)

    def test_comed_source(self):
        """Test the date range utility with ComEd source (5-minute intervals)."""
        date_ranges = generate_date_ranges(self.reference_time, Source.COMED)
        self._log_date_ranges(date_ranges, "API-specific Parameters", Source.COMED)
        
        # Should generate 5 date ranges for ComEd
        self.assertEqual(len(date_ranges), 5)
        
        # Check that the times are rounded to 5-minute intervals
        for start, end in date_ranges:
            self.assertEqual(start.minute % 5, 0)
            self.assertEqual(start.second, 0)
            self.assertEqual(start.microsecond, 0)
            self.assertEqual(end.minute % 5, 0)
            self.assertEqual(end.second, 0)
            self.assertEqual(end.microsecond, 0)

    def test_quarter_hourly_interval(self):
        """Test the date range utility with quarter-hourly interval."""
        date_ranges = generate_date_ranges(self.reference_time, interval=TimeInterval.QUARTER_HOURLY)
        self._log_date_ranges(date_ranges, "Quarter-hourly Interval")
        
        # Should generate 4 date ranges by default
        self.assertEqual(len(date_ranges), 4)
        
        # Check that the times are rounded to 15-minute intervals
        for start, end in date_ranges:
            self.assertEqual(start.minute % 15, 0)
            self.assertEqual(start.second, 0)
            self.assertEqual(start.microsecond, 0)
            self.assertEqual(end.minute % 15, 0)
            self.assertEqual(end.second, 0)
            self.assertEqual(end.microsecond, 0)

    def test_custom_parameters(self):
        """Test the date range utility with custom parameters."""
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
        self.assertEqual(len(date_ranges), 5)
        
        # Check that the wider range uses the custom max_days parameters
        self.assertEqual(date_ranges[4][0].date(), (self.reference_time - timedelta(days=3)).date())
        self.assertEqual(date_ranges[4][1].date(), (self.reference_time + timedelta(days=3)).date())

    def test_no_historical(self):
        """Test the date range utility with no historical data."""
        date_ranges = generate_date_ranges(
            self.reference_time,
            include_historical=False
        )
        self._log_date_ranges(date_ranges, "No Historical Data")
        
        # Should generate 3 date ranges without historical data
        # (standard, future, and wider range)
        self.assertEqual(len(date_ranges), 3)
        
        # First range should be today to tomorrow (standard)
        self.assertEqual(date_ranges[0][0].date(), self.reference_time.date())
        self.assertEqual(date_ranges[0][1].date(), (self.reference_time + timedelta(days=1)).date())
        
        # Second range should be today to day after tomorrow (future)
        self.assertEqual(date_ranges[1][0].date(), self.reference_time.date())
        self.assertEqual(date_ranges[1][1].date(), (self.reference_time + timedelta(days=2)).date())
        
        # Third range should be the wider range (still includes historical data)
        self.assertEqual(date_ranges[2][0].date(), (self.reference_time - timedelta(days=2)).date())
        self.assertEqual(date_ranges[2][1].date(), (self.reference_time + timedelta(days=2)).date())

    def test_no_future(self):
        """Test the date range utility with no future data."""
        date_ranges = generate_date_ranges(
            self.reference_time,
            include_future=False
        )
        self._log_date_ranges(date_ranges, "No Future Data")
        
        # Should generate 3 date ranges without future data
        # (standard, historical, and wider range)
        self.assertEqual(len(date_ranges), 3)
        
        # First range should be today to tomorrow (standard)
        self.assertEqual(date_ranges[0][0].date(), self.reference_time.date())
        self.assertEqual(date_ranges[0][1].date(), (self.reference_time + timedelta(days=1)).date())
        
        # Second range should be yesterday to today (historical)
        self.assertEqual(date_ranges[1][0].date(), (self.reference_time - timedelta(days=1)).date())
        self.assertEqual(date_ranges[1][1].date(), self.reference_time.date())
        
        # Third range should be the wider range (still includes future data)
        self.assertEqual(date_ranges[2][0].date(), (self.reference_time - timedelta(days=2)).date())
        self.assertEqual(date_ranges[2][1].date(), (self.reference_time + timedelta(days=2)).date())

if __name__ == "__main__":
    unittest.main()
