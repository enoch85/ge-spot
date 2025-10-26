"""Tests for Energi Data Service parser DST handling."""

import pytest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from custom_components.ge_spot.api.parsers.energi_data_parser import EnergiDataParser
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency


class TestEnergiDataParserDST:
    """Test Energi Data Service parser handles DST transitions correctly."""

    def test_parse_dst_fall_back_day_25_hours(self):
        """Test parser handles 25 hours of data on DST fall-back day (100 intervals)."""
        # DST fall-back in Europe: October 26, 2025
        # At 03:00, clocks go back to 02:00, creating 25 hours in the day

        parser = EnergiDataParser()

        # Simulate API response with 100 intervals (25 hours × 4 intervals/hour)
        # Using Copenhagen timezone (Europe/Copenhagen)
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # Create 100 intervals for Oct 26, 2025 (DST fall-back day)
        records = []

        # Hours 00:00 - 01:59 (8 intervals, before the repeated hour)
        for hour in range(0, 2):
            for minute in [0, 15, 30, 45]:
                dt = datetime(2025, 10, 26, hour, minute, 0, tzinfo=copenhagen_tz)
                dt_utc = dt.astimezone(timezone.utc)
                records.append(
                    {
                        "TimeDK": dt_utc.isoformat(),
                        "DayAheadPriceDKK": 10.0 + hour + minute / 100,
                        "PriceArea": "DK1",
                    }
                )

        # First occurrence of hour 02 (DST, UTC+2): 02:00-02:59 CEST
        # In UTC, this is 00:00-00:59
        for minute in [0, 15, 30, 45]:
            dt = datetime(2025, 10, 26, 2, minute, 0, tzinfo=copenhagen_tz)
            # This is during DST, so it's UTC+2
            dt_utc = dt.astimezone(timezone.utc)
            records.append(
                {
                    "TimeDK": dt_utc.isoformat(),
                    "DayAheadPriceDKK": 20.0 + minute / 100,  # Different prices
                    "PriceArea": "DK1",
                }
            )

        # Second occurrence of hour 02 (Standard, UTC+1): 02:00-02:59 CET
        # This happens after the clock turns back
        # In UTC, this is 01:00-01:59
        base_dt = datetime(2025, 10, 26, 2, 0, 0, tzinfo=copenhagen_tz)
        base_utc = base_dt.astimezone(timezone.utc)
        for i, minute in enumerate([0, 15, 30, 45]):
            # Add 1 hour to get the second occurrence in UTC
            dt_utc = base_utc + timedelta(hours=1, minutes=i * 15)
            records.append(
                {
                    "TimeDK": dt_utc.isoformat(),
                    "DayAheadPriceDKK": 30.0 + minute / 100,  # Different prices
                    "PriceArea": "DK1",
                }
            )

        # Hours 03:00 - 23:59 (84 intervals, after the repeated hour)
        for hour in range(3, 24):
            for minute in [0, 15, 30, 45]:
                dt = datetime(2025, 10, 26, hour, minute, 0, tzinfo=copenhagen_tz)
                dt_utc = dt.astimezone(timezone.utc)
                records.append(
                    {
                        "TimeDK": dt_utc.isoformat(),
                        "DayAheadPriceDKK": 10.0 + hour + minute / 100,
                        "PriceArea": "DK1",
                    }
                )

        # Wrap in API response structure
        raw_data = {"raw_data": {"today": {"records": records}, "tomorrow": None}}

        # Parse the data
        result = parser.parse(raw_data)

        # Verify results
        assert result["currency"] == Currency.DKK
        assert result["timezone"] == "Europe/Copenhagen"

        # Should have 100 intervals for DST fall-back day
        interval_raw = result["interval_raw"]
        assert (
            len(interval_raw) == 100
        ), f"Expected 100 intervals on DST fall-back day, got {len(interval_raw)}"

        # Verify we have price data
        assert all(isinstance(price, float) for price in interval_raw.values())

    def test_parse_dst_spring_forward_day_23_hours(self):
        """Test parser handles 23 hours of data on DST spring-forward day (92 intervals)."""
        # DST spring-forward in Europe: March 30, 2025
        # At 02:00, clocks jump to 03:00, creating only 23 hours in the day

        parser = EnergiDataParser()
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # Create 92 intervals for March 30, 2025 (DST spring-forward day)
        records = []

        # Hours 00:00 - 01:59 (8 intervals, before the skip)
        for hour in range(0, 2):
            for minute in [0, 15, 30, 45]:
                dt = datetime(2025, 3, 30, hour, minute, 0, tzinfo=copenhagen_tz)
                dt_utc = dt.astimezone(timezone.utc)
                records.append(
                    {
                        "TimeDK": dt_utc.isoformat(),
                        "DayAheadPriceDKK": 10.0 + hour + minute / 100,
                        "PriceArea": "DK1",
                    }
                )

        # Hour 02:00-02:59 is SKIPPED (no data for this hour)

        # Hours 03:00 - 23:59 (84 intervals, after the skip)
        for hour in range(3, 24):
            for minute in [0, 15, 30, 45]:
                dt = datetime(2025, 3, 30, hour, minute, 0, tzinfo=copenhagen_tz)
                dt_utc = dt.astimezone(timezone.utc)
                records.append(
                    {
                        "TimeDK": dt_utc.isoformat(),
                        "DayAheadPriceDKK": 10.0 + hour + minute / 100,
                        "PriceArea": "DK1",
                    }
                )

        # Wrap in API response structure
        raw_data = {"raw_data": {"today": {"records": records}, "tomorrow": None}}

        # Parse the data
        result = parser.parse(raw_data)

        # Verify results
        interval_raw = result["interval_raw"]
        assert (
            len(interval_raw) == 92
        ), f"Expected 92 intervals on DST spring-forward day, got {len(interval_raw)}"

    def test_parse_normal_day_24_hours(self):
        """Test parser handles 24 hours of data on normal day (96 intervals)."""
        parser = EnergiDataParser()
        copenhagen_tz = ZoneInfo("Europe/Copenhagen")

        # Create 96 intervals for a normal day (not DST transition)
        records = []

        # All 24 hours
        for hour in range(0, 24):
            for minute in [0, 15, 30, 45]:
                dt = datetime(2025, 10, 1, hour, minute, 0, tzinfo=copenhagen_tz)
                dt_utc = dt.astimezone(timezone.utc)
                records.append(
                    {
                        "TimeDK": dt_utc.isoformat(),
                        "DayAheadPriceDKK": 10.0 + hour + minute / 100,
                        "PriceArea": "DK1",
                    }
                )

        # Wrap in API response structure
        raw_data = {"raw_data": {"today": {"records": records}, "tomorrow": None}}

        # Parse the data
        result = parser.parse(raw_data)

        # Verify results
        interval_raw = result["interval_raw"]
        assert (
            len(interval_raw) == 96
        ), f"Expected 96 intervals on normal day, got {len(interval_raw)}"
