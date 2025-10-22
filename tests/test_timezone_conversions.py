"""Comprehensive timezone conversion tests.

Tests all timezone operations to ensure 100% correctness:
- Forward conversions (local → UTC)
- Backward conversions (UTC → local)
- DST transitions (spring forward, fall back)
- Multiple timezones used in the integration
- Error handling for invalid configurations
"""

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import pytest


class TestTimezoneBasics:
    """Test basic timezone conversion operations."""

    def test_zoneinfo_available(self):
        """Verify ZoneInfo is available and works."""
        tz = ZoneInfo("Europe/Copenhagen")
        assert tz is not None
        assert str(tz) == "Europe/Copenhagen"

    def test_naive_to_aware_conversion(self):
        """Test converting naive datetime to timezone-aware."""
        naive_dt = datetime(2025, 10, 12, 13, 0, 0)
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # Localize to Copenhagen
        aware_dt = naive_dt.replace(tzinfo=copenhagen_tz)

        assert aware_dt.tzinfo is not None
        assert aware_dt.tzinfo == copenhagen_tz
        # October 12, 2025 is CEST (UTC+2)
        assert aware_dt.strftime("%z") == "+0200"

    def test_aware_to_utc_conversion(self):
        """Test converting timezone-aware datetime to UTC."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # 13:00 Copenhagen time (CEST = UTC+2)
        local_dt = datetime(2025, 10, 12, 13, 0, 0, tzinfo=copenhagen_tz)

        # Convert to UTC
        utc_dt = local_dt.astimezone(timezone.utc)

        assert utc_dt.hour == 11  # 13:00 - 2 hours = 11:00 UTC
        assert utc_dt.tzinfo == timezone.utc


class TestForwardConversions:
    """Test conversions from local time to UTC (forward)."""

    def test_copenhagen_to_utc_summer(self):
        """Copenhagen summer time (CEST, UTC+2) to UTC."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # July 15, 2025 13:00 CEST
        local_dt = datetime(2025, 7, 15, 13, 0, 0, tzinfo=copenhagen_tz)
        utc_dt = local_dt.astimezone(timezone.utc)

        assert utc_dt == datetime(2025, 7, 15, 11, 0, 0, tzinfo=timezone.utc)
        assert local_dt.strftime("%z") == "+0200"  # CEST

    def test_copenhagen_to_utc_winter(self):
        """Copenhagen winter time (CET, UTC+1) to UTC."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # December 15, 2025 13:00 CET
        local_dt = datetime(2025, 12, 15, 13, 0, 0, tzinfo=copenhagen_tz)
        utc_dt = local_dt.astimezone(timezone.utc)

        assert utc_dt == datetime(2025, 12, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert local_dt.strftime("%z") == "+0100"  # CET

    def test_adelaide_to_utc(self):
        """Adelaide (ACDT, UTC+10:30) to UTC."""
        adelaide_tz = ZoneInfo("Australia/Adelaide")

        # October 12, 2025 23:00 ACDT
        local_dt = datetime(2025, 10, 12, 23, 0, 0, tzinfo=adelaide_tz)
        utc_dt = local_dt.astimezone(timezone.utc)

        assert utc_dt == datetime(2025, 10, 12, 12, 30, 0, tzinfo=timezone.utc)
        assert local_dt.strftime("%z") == "+1030"  # ACDT

    def test_madrid_to_utc(self):
        """Madrid (CEST, UTC+2) to UTC."""
        madrid_tz = ZoneInfo("Europe/Madrid")

        # October 12, 2025 13:00 CEST
        local_dt = datetime(2025, 10, 12, 13, 0, 0, tzinfo=madrid_tz)
        utc_dt = local_dt.astimezone(timezone.utc)

        assert utc_dt == datetime(2025, 10, 12, 11, 0, 0, tzinfo=timezone.utc)


class TestBackwardConversions:
    """Test conversions from UTC to local time (backward)."""

    def test_utc_to_copenhagen_summer(self):
        """UTC to Copenhagen summer time (CEST, UTC+2)."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # July 15, 2025 11:00 UTC
        utc_dt = datetime(2025, 7, 15, 11, 0, 0, tzinfo=timezone.utc)
        local_dt = utc_dt.astimezone(copenhagen_tz)

        assert local_dt.hour == 13  # 11:00 + 2 hours = 13:00 CEST
        assert local_dt.strftime("%z") == "+0200"

    def test_utc_to_copenhagen_winter(self):
        """UTC to Copenhagen winter time (CET, UTC+1)."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # December 15, 2025 12:00 UTC
        utc_dt = datetime(2025, 12, 15, 12, 0, 0, tzinfo=timezone.utc)
        local_dt = utc_dt.astimezone(copenhagen_tz)

        assert local_dt.hour == 13  # 12:00 + 1 hour = 13:00 CET
        assert local_dt.strftime("%z") == "+0100"

    def test_utc_to_adelaide(self):
        """UTC to Adelaide (ACDT, UTC+10:30)."""
        adelaide_tz = ZoneInfo("Australia/Adelaide")

        # October 12, 2025 12:30 UTC
        utc_dt = datetime(2025, 10, 12, 12, 30, 0, tzinfo=timezone.utc)
        local_dt = utc_dt.astimezone(adelaide_tz)

        assert local_dt.hour == 23  # 12:30 + 10:30 = 23:00
        assert local_dt.minute == 0
        assert local_dt.strftime("%z") == "+1030"

    def test_utc_to_multiple_timezones(self):
        """Single UTC time converts correctly to multiple local timezones."""
        utc_dt = datetime(2025, 10, 12, 11, 0, 0, tzinfo=timezone.utc)

        timezones = {
            "Europe/Copenhagen": (13, 0, "+0200"),
            "Europe/Madrid": (13, 0, "+0200"),
            "Europe/Warsaw": (13, 0, "+0200"),
            "Europe/Stockholm": (13, 0, "+0200"),
            "Australia/Adelaide": (21, 30, "+1030"),
        }

        for tz_name, (expected_hour, expected_min, expected_offset) in timezones.items():
            tz = ZoneInfo(tz_name)
            local_dt = utc_dt.astimezone(tz)

            assert (
                local_dt.hour == expected_hour
            ), f"{tz_name}: Expected hour {expected_hour}, got {local_dt.hour}"
            assert (
                local_dt.minute == expected_min
            ), f"{tz_name}: Expected minute {expected_min}, got {local_dt.minute}"
            assert (
                local_dt.strftime("%z") == expected_offset
            ), f"{tz_name}: Expected offset {expected_offset}, got {local_dt.strftime('%z')}"


class TestRoundTripConversions:
    """Test that conversions are reversible (local → UTC → local)."""

    def test_copenhagen_roundtrip(self):
        """Copenhagen → UTC → Copenhagen should be identical."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        original = datetime(2025, 10, 12, 13, 0, 0, tzinfo=copenhagen_tz)
        utc = original.astimezone(timezone.utc)
        back_to_local = utc.astimezone(copenhagen_tz)

        assert original == back_to_local
        assert original.hour == back_to_local.hour
        assert original.minute == back_to_local.minute

    def test_adelaide_roundtrip(self):
        """Adelaide → UTC → Adelaide should be identical."""
        adelaide_tz = ZoneInfo("Australia/Adelaide")

        original = datetime(2025, 10, 12, 23, 0, 0, tzinfo=adelaide_tz)
        utc = original.astimezone(timezone.utc)
        back_to_local = utc.astimezone(adelaide_tz)

        assert original == back_to_local

    def test_utc_roundtrip(self):
        """UTC → Local → UTC should be identical."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        original_utc = datetime(2025, 10, 12, 11, 0, 0, tzinfo=timezone.utc)
        to_local = original_utc.astimezone(copenhagen_tz)
        back_to_utc = to_local.astimezone(timezone.utc)

        assert original_utc == back_to_utc


class TestDSTTransitions:
    """Test Daylight Saving Time transitions."""

    def test_spring_forward_copenhagen(self):
        """Test spring DST transition (last Sunday of March 2025 - March 30)."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # Before transition: March 30, 2025 01:00 CET (UTC+1)
        before = datetime(2025, 3, 30, 1, 0, 0, tzinfo=copenhagen_tz)

        # After transition: March 30, 2025 03:00 CEST (UTC+2) - clocks jump from 2:00 to 3:00
        after = datetime(2025, 3, 30, 3, 0, 0, tzinfo=copenhagen_tz)

        # Convert to UTC
        before_utc = before.astimezone(timezone.utc)
        after_utc = after.astimezone(timezone.utc)

        # Before: 01:00 CET = 00:00 UTC
        assert before_utc.hour == 0
        assert before.strftime("%z") == "+0100"

        # After: 03:00 CEST = 01:00 UTC (only 1 hour passed in UTC)
        assert after_utc.hour == 1
        assert after.strftime("%z") == "+0200"

    def test_fall_back_copenhagen(self):
        """Test fall DST transition (last Sunday of October 2025 - October 26)."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # Before transition: October 26, 2025 01:00 CEST (UTC+2)
        before = datetime(2025, 10, 26, 1, 0, 0, tzinfo=copenhagen_tz)

        # After transition: October 26, 2025 03:00 CET (UTC+1)
        after = datetime(2025, 10, 26, 3, 0, 0, tzinfo=copenhagen_tz)

        before_utc = before.astimezone(timezone.utc)
        after_utc = after.astimezone(timezone.utc)

        # Verify offset changed
        assert before.strftime("%z") == "+0200"
        assert after.strftime("%z") == "+0100"

    def test_dst_naive_timestamp_handling(self):
        """Test handling of naive timestamps during DST transition."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # Create naive timestamps around DST transition
        naive_before = datetime(2025, 10, 26, 1, 0, 0)  # Before transition
        naive_after = datetime(2025, 10, 26, 3, 0, 0)  # After transition

        # Localize to Copenhagen
        aware_before = naive_before.replace(tzinfo=copenhagen_tz)
        aware_after = naive_after.replace(tzinfo=copenhagen_tz)

        # Convert to UTC
        utc_before = aware_before.astimezone(timezone.utc)
        utc_after = aware_after.astimezone(timezone.utc)

        # Verify they're different times in UTC
        assert utc_before != utc_after


class TestISOFormatKeys:
    """Test ISO format key generation (for Issue #3)."""

    def test_iso_key_has_timezone(self):
        """Verify ISO format keys include timezone information."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # Naive timestamp
        naive_dt = datetime(2025, 10, 12, 13, 0, 0)

        # Localize to Copenhagen
        aware_dt = naive_dt.replace(tzinfo=copenhagen_tz)

        # Convert to UTC
        utc_dt = aware_dt.astimezone(timezone.utc)

        # Generate ISO key
        iso_key = utc_dt.isoformat()

        # Verify key has timezone info
        assert "+" in iso_key or "Z" in iso_key
        assert iso_key == "2025-10-12T11:00:00+00:00"

    def test_iso_keys_consistent_format(self):
        """Verify all ISO keys have consistent format."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        timestamps = [
            "2025-10-12T00:00:00",
            "2025-10-12T00:15:00",
            "2025-10-12T13:00:00",
            "2025-10-12T23:45:00",
        ]

        keys = []
        for ts in timestamps:
            dt = datetime.fromisoformat(ts)
            aware = dt.replace(tzinfo=copenhagen_tz)
            utc = aware.astimezone(timezone.utc)
            key = utc.isoformat()
            keys.append(key)

        # All keys should have timezone
        assert all("+" in k or "Z" in k for k in keys)

        # All keys should end with +00:00 (UTC)
        assert all(k.endswith("+00:00") for k in keys)

    def test_already_aware_timestamp(self):
        """Test that already timezone-aware timestamps convert correctly."""
        # Timestamp already has timezone
        aware_str = "2025-10-12T13:00:00+02:00"
        dt = datetime.fromisoformat(aware_str)

        # Convert to UTC
        utc_dt = dt.astimezone(timezone.utc)
        iso_key = utc_dt.isoformat()

        assert iso_key == "2025-10-12T11:00:00+00:00"


class TestMultipleIntervals:
    """Test processing multiple 15-minute intervals."""

    def test_15_minute_intervals_copenhagen(self):
        """Test converting 15-minute intervals from Copenhagen to UTC."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # Generate 4 hours of 15-minute intervals (16 intervals)
        base_time = datetime(2025, 10, 12, 0, 0, 0)
        intervals = []

        for i in range(16):
            minutes = i * 15
            local_dt = (base_time + timedelta(minutes=minutes)).replace(tzinfo=copenhagen_tz)
            utc_dt = local_dt.astimezone(timezone.utc)
            intervals.append((local_dt, utc_dt))

        # Verify first interval: 00:00 CEST = 22:00 UTC (previous day)
        assert intervals[0][0].hour == 0
        assert intervals[0][0].minute == 0
        assert intervals[0][1].hour == 22  # Previous day
        assert intervals[0][1].day == 11

        # Verify last interval: 03:45 CEST = 01:45 UTC
        assert intervals[15][0].hour == 3
        assert intervals[15][0].minute == 45
        assert intervals[15][1].hour == 1
        assert intervals[15][1].minute == 45

    def test_96_intervals_per_day(self):
        """Test that 96 15-minute intervals cover a full day."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        base_time = datetime(2025, 10, 12, 0, 0, 0, tzinfo=copenhagen_tz)

        intervals = []
        for i in range(96):
            minutes = i * 15
            local_dt = base_time + timedelta(minutes=minutes)
            utc_dt = local_dt.astimezone(timezone.utc)
            intervals.append(utc_dt.isoformat())

        # Should have 96 unique keys
        assert len(intervals) == 96
        assert len(set(intervals)) == 96  # All unique

        # All should have timezone
        assert all("+00:00" in k for k in intervals)


class TestErrorHandling:
    """Test error handling for invalid configurations."""

    def test_invalid_timezone_name(self):
        """Test handling of invalid timezone names."""
        from zoneinfo import ZoneInfoNotFoundError

        with pytest.raises(ZoneInfoNotFoundError):
            ZoneInfo("Invalid/Timezone")

    def test_invalid_timezone_with_naive_timestamp(self):
        """Test that invalid timezone with naive timestamp is handled."""
        from zoneinfo import ZoneInfoNotFoundError

        naive_dt = datetime(2025, 10, 12, 13, 0, 0)

        # This should raise an error
        with pytest.raises(ZoneInfoNotFoundError):
            bad_tz = ZoneInfo("America/NotReal")
            naive_dt.replace(tzinfo=bad_tz)


class TestEnergiDataParserScenario:
    """Test the exact scenario from energi_data_parser.py"""

    def test_energi_data_parser_logic(self):
        """Simulate exactly what energi_data_parser does."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # Sample records from Energi Data Service API
        test_records = [
            {"TimeDK": "2025-10-12T00:00:00", "DayAheadPriceDKK": 524.27},
            {"TimeDK": "2025-10-12T00:15:00", "DayAheadPriceDKK": 525.50},
            {"TimeDK": "2025-10-12T13:00:00+02:00", "DayAheadPriceDKK": 600.00},
        ]

        interval_prices_iso = {}

        for record in test_records:
            timestamp_str = record["TimeDK"]
            price = record["DayAheadPriceDKK"]

            # Parse timestamp (as in energi_data_parser.py lines 97-109)
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

            # If datetime is naive, localize it to Copenhagen time
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=copenhagen_tz)

            # Convert to UTC for consistent storage
            dt_utc = dt.astimezone(timezone.utc)

            # Create ISO format key with timezone
            interval_key = dt_utc.isoformat()
            interval_prices_iso[interval_key] = price

        # Verify all keys have timezone
        assert len(interval_prices_iso) == 3
        assert all("+00:00" in k for k in interval_prices_iso.keys())

        # Verify specific conversions
        expected_keys = [
            "2025-10-11T22:00:00+00:00",  # 00:00 CEST - 2h = 22:00 UTC (prev day)
            "2025-10-11T22:15:00+00:00",  # 00:15 CEST - 2h = 22:15 UTC (prev day)
            "2025-10-12T11:00:00+00:00",  # 13:00 CEST - 2h = 11:00 UTC
        ]

        assert list(interval_prices_iso.keys()) == expected_keys


class TestValidationScenario:
    """Test the validation scenario from BasePriceParser."""

    def test_validation_key_match(self):
        """Test that validation can find current interval."""
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # Simulate current time: 2025-10-12 13:15 UTC
        now_utc = datetime(2025, 10, 12, 13, 15, 0, tzinfo=timezone.utc)

        # Calculate current interval (round down to 15-minute boundary)
        interval_minutes = 15
        minute = (now_utc.minute // interval_minutes) * interval_minutes
        current_interval_utc = now_utc.replace(minute=minute, second=0, microsecond=0)
        current_key = current_interval_utc.isoformat()

        # Simulate parser data (Copenhagen time converted to UTC)
        parser_data = {}
        for hour in range(24):
            for minute in [0, 15, 30, 45]:
                local_dt = datetime(2025, 10, 12, hour, minute, 0, tzinfo=copenhagen_tz)
                utc_dt = local_dt.astimezone(timezone.utc)
                key = utc_dt.isoformat()
                parser_data[key] = 500.0 + hour * 10 + minute

        # Verify current key exists in parser data
        assert current_key in parser_data
        assert current_key == "2025-10-12T13:15:00+00:00"

        # Verify we can retrieve the price
        current_price = parser_data.get(current_key)
        assert current_price is not None


if __name__ == "__main__":
    # Run with: python tests/test_timezone_conversions.py
    # Or: pytest tests/test_timezone_conversions.py -v
    pytest.main([__file__, "-v", "--tb=short"])
