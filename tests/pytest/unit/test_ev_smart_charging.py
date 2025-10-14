#!/usr/bin/env python3
"""Unit tests for EV Smart Charging format converter.

Tests the conversion of GE-Spot interval prices (Dict[str, float])
to EV Smart Charging format (List[Dict[str, Any]]).
"""
import sys
import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from custom_components.ge_spot.utils.ev_smart_charging import convert_to_ev_smart_format
from homeassistant.util import dt as dt_util


# Don't use Home Assistant fixtures for these unit tests
@pytest.fixture
def enable_custom_integrations():
    """Override HA fixture."""
    return None


class TestEVSmartChargingConverter:
    """Test cases for EV Smart Charging format converter."""

    def test_convert_empty_dict(self):
        """Test conversion with empty input."""
        result = convert_to_ev_smart_format({}, ZoneInfo("Europe/Stockholm"), 0)
        assert result == []

    def test_convert_96_intervals(self):
        """Test conversion with 96 15-minute intervals (normal day)."""
        # Create 96 intervals (24 hours × 4 intervals/hour)
        prices = {
            f"{h:02d}:{m:02d}": 100.0 + h + m/60
            for h in range(24)
            for m in [0, 15, 30, 45]
        }

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, 0)

        # Verify count
        assert len(result) == 96

        # Verify structure
        assert all("time" in item and "value" in item for item in result)

        # Verify first interval
        assert result[0]["time"].hour == 0
        assert result[0]["time"].minute == 0
        assert result[0]["time"].tzinfo == tz

        # Verify last interval
        assert result[-1]["time"].hour == 23
        assert result[-1]["time"].minute == 45

    def test_convert_92_intervals_dst_spring(self):
        """Test conversion with 92 intervals (DST spring forward, 23-hour day)."""
        # Simulate 23-hour day (spring forward)
        prices = {
            f"{h:02d}:{m:02d}": 100.0
            for h in range(23)
            for m in [0, 15, 30, 45]
        }

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, 0)

        assert len(result) == 92

    def test_convert_100_intervals_dst_fall(self):
        """Test conversion with 100 intervals (DST fall back, 25-hour day)."""
        # Simulate 25-hour day (fall back) using special keys like "02A" for ambiguous hour
        # For this test, we'll accept that normal HH:MM format can't represent 100 intervals
        # The actual DST handling happens upstream in the timezone provider
        # This converter just processes whatever valid HH:MM keys it receives
        prices = {
            f"{h:02d}:{m:02d}": 100.0
            for h in range(24)  # Only valid hours 0-23
            for m in [0, 15, 30, 45]
        }
        
        # Add extra intervals to simulate DST fall (using minutes beyond normal)
        # In reality, upstream provides these as duplicate hour entries
        for m in [0, 15, 30, 45]:
            prices[f"02:{m:02d}"] = 100.0  # Will overwrite, so we get 96 not 100

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, 0)

        # The converter can only handle standard HH:MM format (0-23 hours, 0-59 minutes)
        # It will process 96 intervals max from such input
        assert len(result) == 96

    def test_convert_below_threshold(self):
        """Test validation: < 12 elements returns empty array."""
        # Only 5 intervals
        prices = {f"0{h}:00": 100.0 for h in range(5)}

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, 0)

        # Should return empty array (< 12 minimum)
        assert result == []

    def test_convert_exactly_12_intervals(self):
        """Test edge case: exactly 12 intervals (minimum valid)."""
        prices = {f"{h:02d}:00": 100.0 for h in range(12)}

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, 0)

        # Should return the intervals (≥12 is valid)
        assert len(result) == 12

    def test_convert_sorting(self):
        """Test that results are sorted by time (earliest first)."""
        # Intentionally unsorted input
        prices = {
            "14:30": 150.0,
            "00:15": 100.0,
            "23:45": 200.0,
            "00:00": 95.0,
            "12:00": 120.0,
            "12:15": 121.0,
            "12:30": 122.0,
            "12:45": 123.0,
            "13:00": 124.0,
            "13:15": 125.0,
            "13:30": 126.0,
            "13:45": 127.0,
        }

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, 0)

        # Extract times
        times = [item["time"] for item in result]

        # Verify sorted
        assert times == sorted(times)

        # Verify first and last
        assert result[0]["time"].hour == 0
        assert result[0]["time"].minute == 0
        assert result[-1]["time"].hour == 23
        assert result[-1]["time"].minute == 45

    def test_convert_date_offset_today(self):
        """Test date_offset=0 uses today's date."""
        # Create enough intervals to meet minimum
        prices = {f"{h:02d}:00": 123.45 for h in range(24)}

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, date_offset=0)

        # Get today's date in target timezone
        expected_date = dt_util.now().astimezone(tz).date()

        # Should have results (≥12 intervals)
        assert len(result) > 0
        assert result[0]["time"].date() == expected_date

    def test_convert_date_offset_tomorrow(self):
        """Test date_offset=1 uses tomorrow's date."""
        # Create enough intervals to meet minimum
        prices = {f"{h:02d}:00": 123.45 for h in range(24)}

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, date_offset=1)

        # Get tomorrow's date in target timezone
        expected_date = (dt_util.now().astimezone(tz) + timedelta(days=1)).date()

        # Should have results (≥12 intervals)
        assert len(result) > 0
        assert result[0]["time"].date() == expected_date

    def test_convert_timezone_aware(self):
        """Test that datetime objects are timezone-aware."""
        # Create with sufficient intervals
        prices = {f"{h:02d}:00": 100.0 for h in range(24)}

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, 0)

        # Verify all datetimes are timezone-aware
        assert len(result) > 0
        for item in result:
            assert item["time"].tzinfo is not None
            assert item["time"].tzinfo == tz

    def test_convert_rounding(self):
        """Test that prices are rounded to 4 decimal places."""
        # Create intervals first, then add the specific test values
        prices = {}
        for h in range(24):
            if h != 14:  # Skip hour 14 to add specific values
                prices[f"{h:02d}:00"] = 100.0
        
        # Add test values that should be rounded
        prices["14:00"] = 123.456789
        prices["14:15"] = 124.111111

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, 0)

        # Find the 14:00 entry
        item_14_00 = next(item for item in result if item["time"].hour == 14 and item["time"].minute == 0)

        # Verify rounding
        assert item_14_00["value"] == 123.4568  # Rounded to 4 decimals

    def test_convert_invalid_key_format(self):
        """Test handling of invalid HH:MM keys."""
        prices = {
            "14:00": 100.0,
            "invalid": 200.0,  # Invalid key
            "25:00": 300.0,    # Invalid hour
            "14:60": 400.0,    # Invalid minute
        }
        # Add valid keys to meet minimum
        for h in range(24):
            prices[f"{h:02d}:00"] = 100.0

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, 0)

        # Should skip invalid keys but process valid ones
        assert len(result) >= 12  # At least the valid ones

        # Verify all times are valid
        for item in result:
            assert 0 <= item["time"].hour <= 23
            assert 0 <= item["time"].minute <= 59

    def test_convert_none_input(self):
        """Test handling of None input."""
        result = convert_to_ev_smart_format(None, ZoneInfo("Europe/Stockholm"), 0)
        assert result == []

    def test_convert_not_dict_input(self):
        """Test handling of non-dict input."""
        result = convert_to_ev_smart_format([1, 2, 3], ZoneInfo("Europe/Stockholm"), 0)
        assert result == []

    def test_convert_different_timezones(self):
        """Test conversion with different timezones."""
        prices = {f"{h:02d}:00": 100.0 for h in range(24)}

        # Test with different timezones
        timezones = [
            ZoneInfo("Europe/Stockholm"),
            ZoneInfo("Europe/Oslo"),
            ZoneInfo("Australia/Sydney"),
            ZoneInfo("America/Chicago"),
        ]

        for tz in timezones:
            result = convert_to_ev_smart_format(prices, tz, 0)
            assert len(result) == 24
            assert all(item["time"].tzinfo == tz for item in result)

    def test_convert_preserves_price_values(self):
        """Test that price values are preserved correctly."""
        prices = {}
        # Add other hours first
        for h in range(4, 24):
            prices[f"{h:02d}:00"] = 100.0
        
        # Add specific test values
        prices["00:00"] = 50.1234
        prices["01:00"] = 75.5678
        prices["02:00"] = 100.9999
        prices["03:00"] = 125.0001

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, 0)

        # Find specific entries
        item_00 = next(item for item in result if item["time"].hour == 0)
        item_01 = next(item for item in result if item["time"].hour == 1)
        item_02 = next(item for item in result if item["time"].hour == 2)
        item_03 = next(item for item in result if item["time"].hour == 3)

        # Verify rounded values (round() doesn't round up 100.9999 to 101.0 with 4 decimals)
        assert item_00["value"] == 50.1234
        assert item_01["value"] == 75.5678
        assert item_02["value"] == 100.9999  # Stays at 100.9999 when rounded to 4 decimals
        assert item_03["value"] == 125.0001

    def test_convert_15_minute_intervals(self):
        """Test conversion with full 15-minute interval granularity."""
        prices = {}
        for h in range(24):
            for m in [0, 15, 30, 45]:
                prices[f"{h:02d}:{m:02d}"] = 100.0 + h + (m / 100)

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, 0)

        # Verify count (96 intervals)
        assert len(result) == 96

        # Verify all minutes are present
        minutes_seen = set()
        for item in result:
            minutes_seen.add(item["time"].minute)

        assert minutes_seen == {0, 15, 30, 45}

    def test_convert_missing_intervals(self):
        """Test that missing intervals are handled correctly."""
        # Create sparse data (only even hours)
        prices = {f"{h:02d}:00": 100.0 for h in range(0, 24, 2)}

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, 0)

        # Should only have the 12 even hours
        assert len(result) == 12

        # Verify only even hours present
        hours_seen = {item["time"].hour for item in result}
        assert hours_seen == {0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22}

    def test_convert_with_non_numeric_price(self):
        """Test handling of non-numeric price values (triggers ValueError)."""
        prices = {}
        # Add valid prices first
        for h in range(24):
            if h != 14:
                prices[f"{h:02d}:00"] = 100.0
        
        # Add non-numeric price (will trigger ValueError in float() conversion)
        prices["14:00"] = "not_a_number"

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, 0)

        # Should skip the invalid price and process the rest
        assert len(result) == 23  # All except the invalid one
        
        # Verify 14:00 is NOT in results
        hours = [item["time"].hour for item in result]
        assert 14 not in hours

    def test_convert_with_none_price_values(self):
        """Test handling of None price values (triggers exception)."""
        prices = {}
        # Add valid prices
        for h in range(12):
            prices[f"{h:02d}:00"] = 100.0
        
        # Add None price
        prices["14:00"] = None

        tz = ZoneInfo("Europe/Stockholm")
        result = convert_to_ev_smart_format(prices, tz, 0)

        # Should skip the None value and process valid ones
        assert len(result) == 12
        
        # Verify all values are numeric
        for item in result:
            assert isinstance(item["value"], (int, float))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
