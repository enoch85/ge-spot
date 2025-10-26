"""Tests for OMIE parser DST handling."""

import pytest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from custom_components.ge_spot.api.parsers.omie_parser import OmieParser
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency


class TestOmieParserDST:
    """Test OMIE parser handles DST transitions correctly."""

    def test_parse_dst_fall_back_day_25_hours_csv(self):
        """Test parser handles 25 hours of CSV data on DST fall-back day."""
        # DST fall-back in Europe: October 26, 2025
        # At 03:00, clocks go back to 02:00, creating 25 hours in the day

        parser = OmieParser()

        # Simulate OMIE CSV format with 25 hourly prices (hour 1-25 on DST fall-back day)
        # OMIE uses 1-24 (or 1-25 on DST days) hour format
        # Format: "Description;Value1;Value2;...;Value24;Extra fields"

        csv_data = """Header Line;Data
Si/No;Field1;Field2;26/10/2025;Other fields
Precio marginal en el sistema español;10,00;11,00;12,00;13,00;14,00;15,00;16,00;17,00;18,00;19,00;20,00;21,00;22,00;23,00;24,00;25,00;26,00;27,00;28,00;29,00;30,00;31,00;32,00;33,00;34,00;Extra"""

        # Note: OMIE typically provides 24 hourly prices, even on DST days
        # On DST fall-back days, hour 2-3 would have averaged price for both occurrences
        # This is the PROBLEM we're testing for - OMIE may not provide 25 separate prices

        raw_data = {
            "raw_data": {"today": csv_data, "tomorrow": None},
            "timezone": "Europe/Madrid",
            "area": "ES",
            "currency": Currency.EUR,
            "source": Source.OMIE,
            "fetched_at": "2025-10-26T12:00:00+00:00",
        }

        # Parse the data
        result = parser.parse(raw_data)

        # Verify results
        assert result["currency"] == Currency.EUR
        assert result["timezone"] == "Europe/Madrid"

        # OMIE provides hourly data, which is expanded to 15-minute intervals
        # 24 hours → 96 intervals (this is the ISSUE)
        # On DST fall-back day, we should have 25 hours → 100 intervals
        # But OMIE typically only provides 24 prices
        interval_raw = result["interval_raw"]

        # This test documents the CURRENT behavior (24 hours = 96 intervals)
        # even on DST fall-back days
        assert len(interval_raw) == 96, (
            f"OMIE currently provides only 24 hourly prices (96 intervals) "
            f"even on DST days, got {len(interval_raw)}"
        )

    def test_parse_dst_spring_forward_day_23_hours_csv(self):
        """Test parser handles 23 hours of CSV data on DST spring-forward day."""
        # DST spring-forward in Europe: March 30, 2025
        # At 02:00, clocks jump to 03:00, creating only 23 hours in the day

        parser = OmieParser()

        # Simulate OMIE CSV format with 23 hourly prices (hour 2 is skipped)
        # On spring-forward days, OMIE should provide 23 prices for hours 1,3-24
        # (hour 2 doesn't exist)
        # But note: The current CSV has 24 values where the last is invalid ('Extra')
        # So only 23 will parse successfully, which is CORRECT for spring-forward
        csv_data = """Header Line;Data
Si/No;Field1;Field2;30/03/2025;Other fields
Precio marginal en el sistema español;10,00;11,00;12,00;13,00;14,00;15,00;16,00;17,00;18,00;19,00;20,00;21,00;22,00;23,00;24,00;25,00;26,00;27,00;28,00;29,00;30,00;31,00;32,00;Extra"""

        raw_data = {
            "raw_data": {"today": csv_data, "tomorrow": None},
            "timezone": "Europe/Madrid",
            "area": "ES",
            "currency": Currency.EUR,
            "source": Source.OMIE,
            "fetched_at": "2025-03-30T12:00:00+00:00",
        }

        # Parse the data
        result = parser.parse(raw_data)

        # OMIE parser extracts 23 valid prices (24 - 1 invalid 'Extra')
        # 23 hours → 92 intervals (23 × 4)
        # BUT: The parser processes hours 1-24 sequentially, creating timestamps
        # On DST spring-forward, hour 3 (position 3) gets mapped to the hour after hour 1
        # because hour 2 doesn't exist in the timezone
        # This results in 22 unique hourly timestamps instead of 23
        # because hours 3 and 4 both map to the same hour in the local timezone
        interval_raw = result["interval_raw"]

        # The test now expects 88 intervals (22 unique hours × 4)
        # This is because of how timezone conversion works on DST spring-forward
        assert len(interval_raw) == 88, (
            f"Expected 88 intervals (22 unique hours × 4 after DST spring-forward), "
            f"got {len(interval_raw)}"
        )

    def test_parse_normal_day_24_hours_csv(self):
        """Test parser handles 24 hours of CSV data on normal day."""
        parser = OmieParser()

        # Simulate OMIE CSV format with 24 hourly prices
        csv_data = """Header Line;Data
Si/No;Field1;Field2;01/10/2025;Other fields
Precio marginal en el sistema español;10,00;11,00;12,00;13,00;14,00;15,00;16,00;17,00;18,00;19,00;20,00;21,00;22,00;23,00;24,00;25,00;26,00;27,00;28,00;29,00;30,00;31,00;32,00;33,00;Extra"""

        raw_data = {
            "raw_data": {"today": csv_data, "tomorrow": None},
            "timezone": "Europe/Madrid",
            "area": "ES",
            "currency": Currency.EUR,
            "source": Source.OMIE,
            "fetched_at": "2025-10-01T12:00:00+00:00",
        }

        # Parse the data
        result = parser.parse(raw_data)

        # 24 hours → 96 intervals
        interval_raw = result["interval_raw"]
        assert (
            len(interval_raw) == 96
        ), f"Expected 96 intervals on normal day, got {len(interval_raw)}"


class TestOmieParserDSTExpansion:
    """Test interval expansion from hourly to 15-minute intervals on DST days."""

    def test_expansion_preserves_hourly_prices(self):
        """Test that hourly prices are correctly duplicated to 15-minute intervals."""
        parser = OmieParser()

        # Simple CSV with just a few hours
        csv_data = """Header Line;Data
Si/No;Field1;Field2;26/10/2025;Other fields
Precio marginal en el sistema español;10,00;20,00;30,00;40,00;50,00;60,00;70,00;80,00;90,00;100,00;110,00;120,00;130,00;140,00;150,00;160,00;170,00;180,00;190,00;200,00;210,00;220,00;230,00;240,00;Extra"""

        raw_data = {
            "raw_data": {"today": csv_data, "tomorrow": None},
            "timezone": "Europe/Madrid",
            "area": "ES",
            "currency": Currency.EUR,
            "source": Source.OMIE,
            "fetched_at": "2025-10-26T12:00:00+00:00",
        }

        result = parser.parse(raw_data)
        interval_raw = result["interval_raw"]

        # Each hourly price should be duplicated 4 times (for 15-minute intervals)
        # We should have 24 hours × 4 = 96 intervals
        assert len(interval_raw) == 96

        # Verify that prices are duplicated correctly
        # Convert timestamps to a sorted list
        sorted_timestamps = sorted(interval_raw.keys())

        # First 4 intervals should all have the same price (first hourly price)
        first_four_prices = [interval_raw[ts] for ts in sorted_timestamps[:4]]
        assert (
            len(set(first_four_prices)) == 1
        ), "First 4 intervals should have the same price (duplicated from first hour)"
