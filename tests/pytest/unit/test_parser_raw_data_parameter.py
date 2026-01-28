"""Comprehensive tests for parser raw_data parameter consistency and interval_raw handling.

This test module verifies:
1. All parser parse() methods use 'raw_data' parameter (matching BasePriceParser)
2. All parsers return 'interval_raw' key with correct structure
3. Timezone conversions work correctly across different timezones
4. Price data handling is consistent across all parsers
5. DST transitions are handled correctly
6. Different API response formats are parsed correctly

These tests are designed to catch regressions in the parser infrastructure.
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock, patch
import inspect

from custom_components.ge_spot.api.base.price_parser import BasePriceParser
from custom_components.ge_spot.api.parsers.aemo_parser import AemoParser
from custom_components.ge_spot.api.parsers.amber_parser import AmberParser
from custom_components.ge_spot.api.parsers.comed_parser import ComedParser
from custom_components.ge_spot.api.parsers.energi_data_parser import EnergiDataParser
from custom_components.ge_spot.api.parsers.energy_charts_parser import (
    EnergyChartsParser,
)
from custom_components.ge_spot.api.parsers.entsoe_parser import EntsoeParser
from custom_components.ge_spot.api.parsers.nordpool_parser import NordpoolParser
from custom_components.ge_spot.api.parsers.omie_parser import OmieParser
from custom_components.ge_spot.api.parsers.stromligning_parser import StromligningParser

from custom_components.ge_spot.timezone.service import TimezoneService
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.const.sources import Source

# ============================================================================
# Test fixtures
# ============================================================================


@pytest.fixture
def timezone_service():
    """Create a timezone service for testing."""
    service = TimezoneService()
    return service


@pytest.fixture
def all_parser_classes():
    """Return all parser classes for testing."""
    return [
        AemoParser,
        AmberParser,
        ComedParser,
        EnergiDataParser,
        EnergyChartsParser,
        EntsoeParser,
        NordpoolParser,
        OmieParser,
        StromligningParser,
    ]


# ============================================================================
# Test: Parameter naming consistency
# ============================================================================


class TestParserParameterNaming:
    """Test that all parsers use consistent parameter names."""

    def test_base_parser_uses_raw_data_parameter(self):
        """Verify BasePriceParser.parse() uses 'raw_data' parameter."""
        sig = inspect.signature(BasePriceParser.parse)
        params = list(sig.parameters.keys())

        assert "raw_data" in params, (
            f"BasePriceParser.parse() should have 'raw_data' parameter, "
            f"but has: {params}"
        )

    @pytest.mark.parametrize(
        "parser_class",
        [
            AemoParser,
            AmberParser,
            ComedParser,
            EnergiDataParser,
            EnergyChartsParser,
            EntsoeParser,
            NordpoolParser,
            OmieParser,
            StromligningParser,
        ],
    )
    def test_parser_uses_raw_data_parameter(self, parser_class):
        """Verify each parser's parse() method uses 'raw_data' parameter."""
        sig = inspect.signature(parser_class.parse)
        params = list(sig.parameters.keys())

        assert "raw_data" in params, (
            f"{parser_class.__name__}.parse() should have 'raw_data' parameter, "
            f"but has: {params}"
        )

        # Also verify it's the second parameter (after self)
        assert params[1] == "raw_data", (
            f"{parser_class.__name__}.parse() should have 'raw_data' as second parameter, "
            f"but order is: {params}"
        )

    @pytest.mark.parametrize(
        "parser_class",
        [
            AemoParser,
            AmberParser,
            ComedParser,
            EnergiDataParser,
            EnergyChartsParser,
            EntsoeParser,
            NordpoolParser,
            OmieParser,
            StromligningParser,
        ],
    )
    def test_parser_inherits_from_base(self, parser_class):
        """Verify all parsers inherit from BasePriceParser."""
        assert issubclass(
            parser_class, BasePriceParser
        ), f"{parser_class.__name__} should inherit from BasePriceParser"


# ============================================================================
# Test: interval_raw output consistency
# ============================================================================


class TestIntervalRawOutput:
    """Test that all parsers output interval_raw correctly."""

    def test_base_parser_helper_methods_use_interval_raw(self, timezone_service):
        """Verify base parser helper methods use interval_raw parameter."""
        # Check _get_current_price
        sig = inspect.signature(BasePriceParser._get_current_price)
        params = list(sig.parameters.keys())
        assert (
            "interval_raw" in params
        ), f"_get_current_price should use 'interval_raw' parameter, got: {params}"

        # Check _get_next_interval_price
        sig = inspect.signature(BasePriceParser._get_next_interval_price)
        params = list(sig.parameters.keys())
        assert (
            "interval_raw" in params
        ), f"_get_next_interval_price should use 'interval_raw' parameter, got: {params}"

        # Check _calculate_day_average
        sig = inspect.signature(BasePriceParser._calculate_day_average)
        params = list(sig.parameters.keys())
        assert (
            "interval_raw" in params
        ), f"_calculate_day_average should use 'interval_raw' parameter, got: {params}"

    @pytest.mark.parametrize(
        "parser_class,test_input",
        [
            (
                NordpoolParser,
                {
                    "raw_data": {
                        "today": {
                            "multiAreaEntries": [
                                {
                                    "deliveryStart": "2025-01-28T00:00:00+01:00",
                                    "entryPerArea": {"SE3": 50.0},
                                },
                                {
                                    "deliveryStart": "2025-01-28T01:00:00+01:00",
                                    "entryPerArea": {"SE3": 55.0},
                                },
                            ]
                        }
                    },
                    "timezone": "Europe/Stockholm",
                    "currency": Currency.EUR,
                    "area": "SE3",
                    "delivery_area": "SE3",
                },
            ),
            (
                AmberParser,
                [
                    {"startTime": "2025-01-28T00:00:00+11:00", "perKwh": 25.5},
                    {"startTime": "2025-01-28T00:30:00+11:00", "perKwh": 26.0},
                ],
            ),
            (
                StromligningParser,
                {
                    "prices": [
                        {"date": "2025-01-28T00:00:00Z", "price": {"value": 0.5}},
                        {"date": "2025-01-28T01:00:00Z", "price": {"value": 0.55}},
                    ]
                },
            ),
        ],
    )
    def test_parser_returns_interval_raw_key(
        self, parser_class, test_input, timezone_service
    ):
        """Verify parser returns result with 'interval_raw' key."""
        parser = parser_class(timezone_service=timezone_service)
        result = parser.parse(test_input)

        assert (
            "interval_raw" in result
        ), f"{parser_class.__name__} should return 'interval_raw' key in result"
        assert isinstance(
            result["interval_raw"], dict
        ), f"{parser_class.__name__} interval_raw should be a dictionary"


# ============================================================================
# Test: Timezone handling across different regions
# ============================================================================


class TestTimezoneHandling:
    """Test timezone handling for different regions."""

    @pytest.mark.parametrize(
        "source_tz,target_tz,input_time,expected_offset_hours",
        [
            # European timezones
            ("Europe/Stockholm", "Europe/Stockholm", "2025-01-28T12:00:00", 0),
            (
                "UTC",
                "Europe/Stockholm",
                "2025-01-28T12:00:00Z",
                1,
            ),  # CET is UTC+1 in winter
            ("Europe/Berlin", "Europe/London", "2025-01-28T12:00:00+01:00", -1),
            # Australian timezones
            ("Australia/Sydney", "Australia/Sydney", "2025-01-28T12:00:00", 0),
            (
                "UTC",
                "Australia/Sydney",
                "2025-01-28T12:00:00Z",
                11,
            ),  # AEDT is UTC+11 in summer
            # American timezones
            ("America/Chicago", "America/Chicago", "2025-01-28T12:00:00", 0),
            ("UTC", "America/New_York", "2025-01-28T12:00:00Z", -5),  # EST is UTC-5
            # Cross-continental
            ("Europe/Stockholm", "America/New_York", "2025-01-28T12:00:00+01:00", -6),
        ],
    )
    def test_timezone_offset_calculation(
        self, source_tz, target_tz, input_time, expected_offset_hours
    ):
        """Test that timezone offsets are calculated correctly."""
        source_zone = ZoneInfo(source_tz)
        target_zone = ZoneInfo(target_tz)

        # Parse input time
        if input_time.endswith("Z"):
            dt = datetime.fromisoformat(input_time.replace("Z", "+00:00"))
        elif "+" in input_time or input_time.count("-") > 2:
            dt = datetime.fromisoformat(input_time)
        else:
            dt = datetime.fromisoformat(input_time).replace(tzinfo=source_zone)

        # Convert to target timezone
        target_dt = dt.astimezone(target_zone)

        # Calculate actual offset
        actual_offset = (
            target_dt.utcoffset().total_seconds() - dt.utcoffset().total_seconds()
        ) / 3600

        assert actual_offset == expected_offset_hours, (
            f"Expected offset {expected_offset_hours}h from {source_tz} to {target_tz}, "
            f"but got {actual_offset}h"
        )


# ============================================================================
# Test: Price data handling
# ============================================================================


class TestPriceDataHandling:
    """Test price data handling across parsers."""

    def test_nordpool_price_extraction(self, timezone_service):
        """Test Nordpool parser extracts prices correctly."""
        parser = NordpoolParser(timezone_service=timezone_service)

        test_data = {
            "raw_data": {
                "today": {
                    "multiAreaEntries": [
                        {
                            "deliveryStart": "2025-01-28T00:00:00+01:00",
                            "entryPerArea": {"SE3": 50.25},
                        },
                        {
                            "deliveryStart": "2025-01-28T01:00:00+01:00",
                            "entryPerArea": {"SE3": 55.75},
                        },
                        {
                            "deliveryStart": "2025-01-28T02:00:00+01:00",
                            "entryPerArea": {"SE3": 60.00},
                        },
                    ]
                }
            },
            "timezone": "Europe/Stockholm",
            "currency": Currency.EUR,
            "area": "SE3",
            "delivery_area": "SE3",
        }

        result = parser.parse(test_data)

        assert len(result["interval_raw"]) == 3, "Should have 3 interval prices"

        # Verify prices are floats
        for key, price in result["interval_raw"].items():
            assert isinstance(price, (int, float)), f"Price should be numeric: {price}"

    def test_amber_price_extraction(self, timezone_service):
        """Test Amber parser extracts prices correctly."""
        parser = AmberParser(timezone_service=timezone_service)

        test_data = [
            {"startTime": "2025-01-28T00:00:00+11:00", "perKwh": 25.5},
            {"startTime": "2025-01-28T00:30:00+11:00", "perKwh": 26.0},
            {"startTime": "2025-01-28T01:00:00+11:00", "perKwh": 27.5},
        ]

        result = parser.parse(test_data)

        assert len(result["interval_raw"]) == 3, "Should have 3 interval prices"
        assert result["currency"] == Currency.AUD, "Should use AUD currency"

    def test_stromligning_price_extraction(self, timezone_service):
        """Test Stromligning parser extracts prices correctly."""
        parser = StromligningParser(timezone_service=timezone_service)

        # Stromligning expects format: {"date": ISO, "price": {"value": float}}
        test_data = {
            "prices": [
                {"date": "2025-01-28T00:00:00Z", "price": {"value": 0.50}},
                {"date": "2025-01-28T01:00:00Z", "price": {"value": 0.55}},
                {"date": "2025-01-28T02:00:00Z", "price": {"value": 0.60}},
            ]
        }

        result = parser.parse(test_data)

        assert len(result["interval_raw"]) == 3, "Should have 3 interval prices"
        assert result["currency"] == Currency.DKK, "Should use DKK currency"


# ============================================================================
# Test: DST transition handling
# ============================================================================


class TestDSTTransitionHandling:
    """Test DST transition handling."""

    @pytest.mark.parametrize(
        "timezone_name,spring_forward_date,fall_back_date",
        [
            ("Europe/Stockholm", "2025-03-30", "2025-10-26"),  # EU DST
            ("America/New_York", "2025-03-09", "2025-11-02"),  # US DST
            (
                "Australia/Sydney",
                "2025-10-05",
                "2025-04-06",
            ),  # AU DST (reversed seasons)
        ],
    )
    def test_dst_aware_interval_count(
        self, timezone_name, spring_forward_date, fall_back_date
    ):
        """Test that DST transitions affect interval counts correctly."""
        from custom_components.ge_spot.const.time import TimeInterval

        tz = ZoneInfo(timezone_name)

        # Spring forward - should have fewer intervals (23 hours)
        spring_dt = datetime.fromisoformat(f"{spring_forward_date}T12:00:00").replace(
            tzinfo=tz
        )
        spring_intervals = TimeInterval.get_expected_intervals_for_date(spring_dt, tz)

        # Fall back - should have more intervals (25 hours)
        fall_dt = datetime.fromisoformat(f"{fall_back_date}T12:00:00").replace(
            tzinfo=tz
        )
        fall_intervals = TimeInterval.get_expected_intervals_for_date(fall_dt, tz)

        # Normal day - should have 96 intervals (24 hours * 4)
        normal_dt = datetime.fromisoformat("2025-06-15T12:00:00").replace(tzinfo=tz)
        normal_intervals = TimeInterval.get_expected_intervals_for_date(normal_dt, tz)

        # Verify
        assert (
            normal_intervals == 96
        ), f"Normal day should have 96 intervals, got {normal_intervals}"
        assert (
            spring_intervals < normal_intervals
        ), f"Spring forward should have fewer intervals: {spring_intervals} vs {normal_intervals}"
        assert (
            fall_intervals > normal_intervals
        ), f"Fall back should have more intervals: {fall_intervals} vs {normal_intervals}"


# ============================================================================
# Test: API response format handling
# ============================================================================


class TestAPIResponseFormats:
    """Test handling of different API response formats."""

    def test_entsoe_xml_string_input(self, timezone_service):
        """Test ENTSOE parser handles XML string input."""
        parser = EntsoeParser(timezone_service=timezone_service)

        # Minimal valid XML structure (parser should handle gracefully)
        xml_input = """<?xml version="1.0" encoding="UTF-8"?>
        <Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
        </Publication_MarketDocument>"""

        result = parser.parse(xml_input)

        assert "interval_raw" in result
        assert "currency" in result
        assert "timezone" in result

    def test_entsoe_dict_with_raw_data_input(self, timezone_service):
        """Test ENTSOE parser handles dict with raw_data key."""
        parser = EntsoeParser(timezone_service=timezone_service)

        dict_input = {
            "raw_data": {"today": [], "tomorrow": []},
            "timezone": "Europe/Berlin",
            "currency": Currency.EUR,
        }

        result = parser.parse(dict_input)

        assert "interval_raw" in result

    def test_nordpool_nested_structure(self, timezone_service):
        """Test Nordpool parser handles nested today/tomorrow structure."""
        parser = NordpoolParser(timezone_service=timezone_service)

        test_data = {
            "raw_data": {
                "yesterday": {"multiAreaEntries": []},
                "today": {
                    "multiAreaEntries": [
                        {
                            "deliveryStart": "2025-01-28T00:00:00+01:00",
                            "entryPerArea": {"SE3": 50.0},
                        }
                    ]
                },
                "tomorrow": {
                    "multiAreaEntries": [
                        {
                            "deliveryStart": "2025-01-29T00:00:00+01:00",
                            "entryPerArea": {"SE3": 55.0},
                        }
                    ]
                },
            },
            "timezone": "Europe/Stockholm",
            "currency": Currency.EUR,
            "area": "SE3",
            "delivery_area": "SE3",
        }

        result = parser.parse(test_data)

        assert "interval_raw" in result
        assert (
            len(result["interval_raw"]) == 2
        ), "Should have prices from today and tomorrow"

    def test_energy_charts_unix_timestamp_input(self, timezone_service):
        """Test Energy Charts parser handles unix timestamp format."""
        parser = EnergyChartsParser(timezone_service=timezone_service)

        # January 28, 2025 00:00:00 UTC in unix seconds
        base_ts = 1738022400

        test_data = {
            "raw_data": {
                "unix_seconds": [base_ts, base_ts + 3600, base_ts + 7200],
                "price": [50.0, 55.0, 60.0],
                "unit": "EUR / MWh",
            },
            "timezone": "Europe/Berlin",
            "currency": Currency.EUR,
            "area": "DE",
        }

        result = parser.parse(test_data)

        assert "interval_raw" in result
        assert len(result["interval_raw"]) == 3

    def test_omie_csv_text_input(self, timezone_service):
        """Test OMIE parser handles CSV text input."""
        parser = OmieParser(timezone_service=timezone_service)

        # OMIE CSV format: Year;Month;Day;Hour;Price_ES;Price_PT
        csv_content = """2025;01;28;1;50.00;51.00
2025;01;28;2;55.00;56.00
2025;01;28;3;60.00;61.00"""

        test_data = {
            "raw_data": {"today": csv_content, "tomorrow": None},
            "timezone": "Europe/Madrid",
            "area": "ES",
            "currency": Currency.EUR,
        }

        result = parser.parse(test_data)

        assert "interval_raw" in result


# ============================================================================
# Test: Edge cases and error handling
# ============================================================================


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling."""

    @pytest.mark.parametrize(
        "parser_class",
        [
            NordpoolParser,
            AmberParser,
            StromligningParser,
            EnergyChartsParser,
        ],
    )
    def test_empty_input_returns_empty_interval_raw(
        self, parser_class, timezone_service
    ):
        """Test that empty input returns result with empty interval_raw."""
        parser = parser_class(timezone_service=timezone_service)

        # Try with empty dict
        result = parser.parse({})

        assert "interval_raw" in result
        assert isinstance(result["interval_raw"], dict)

    @pytest.mark.parametrize(
        "parser_class",
        [
            NordpoolParser,
            AmberParser,
            StromligningParser,
        ],
    )
    def test_none_input_handling(self, parser_class, timezone_service):
        """Test that None-like inputs are handled gracefully."""
        parser = parser_class(timezone_service=timezone_service)

        # Parser should handle this without crashing
        try:
            result = parser.parse(None)
            assert "interval_raw" in result
        except (TypeError, AttributeError):
            # Some parsers may raise on None - that's acceptable
            pass

    def test_negative_prices_preserved(self, timezone_service):
        """Test that negative prices (common in some markets) are preserved."""
        parser = NordpoolParser(timezone_service=timezone_service)

        test_data = {
            "raw_data": {
                "today": {
                    "multiAreaEntries": [
                        {
                            "deliveryStart": "2025-01-28T00:00:00+01:00",
                            "entryPerArea": {"SE3": -10.5},  # Negative price
                        },
                        {
                            "deliveryStart": "2025-01-28T01:00:00+01:00",
                            "entryPerArea": {"SE3": 0.0},  # Zero price
                        },
                        {
                            "deliveryStart": "2025-01-28T02:00:00+01:00",
                            "entryPerArea": {"SE3": 50.0},  # Normal price
                        },
                    ]
                }
            },
            "timezone": "Europe/Stockholm",
            "currency": Currency.EUR,
            "area": "SE3",
            "delivery_area": "SE3",
        }

        result = parser.parse(test_data)

        prices = list(result["interval_raw"].values())
        assert any(p < 0 for p in prices), "Should preserve negative prices"
        assert any(p == 0 for p in prices), "Should preserve zero prices"
        assert any(p > 0 for p in prices), "Should preserve positive prices"

    def test_very_large_prices_preserved(self, timezone_service):
        """Test that very large prices (price spikes) are preserved."""
        parser = AmberParser(timezone_service=timezone_service)

        # Australia occasionally has extreme price spikes
        test_data = [
            {"startTime": "2025-01-28T00:00:00+11:00", "perKwh": 25.5},
            {
                "startTime": "2025-01-28T00:30:00+11:00",
                "perKwh": 15000.0,
            },  # Price spike!
            {"startTime": "2025-01-28T01:00:00+11:00", "perKwh": 30.0},
        ]

        result = parser.parse(test_data)

        prices = list(result["interval_raw"].values())
        assert max(prices) == 15000.0, "Should preserve extreme price spikes"


# ============================================================================
# Test: Metadata consistency
# ============================================================================


class TestMetadataConsistency:
    """Test metadata handling consistency."""

    @pytest.mark.parametrize(
        "parser_class,expected_currency,test_input",
        [
            (
                NordpoolParser,
                Currency.EUR,
                {
                    "raw_data": {"today": {"multiAreaEntries": []}},
                    "timezone": "Europe/Stockholm",
                    "currency": Currency.EUR,
                    "area": "SE3",
                    "delivery_area": "SE3",
                },
            ),
            (AmberParser, Currency.AUD, []),
            (StromligningParser, Currency.DKK, {"prices": []}),
            (ComedParser, Currency.CENTS, {}),
            (EnergiDataParser, Currency.DKK, {}),
        ],
    )
    def test_default_currency(
        self, parser_class, expected_currency, test_input, timezone_service
    ):
        """Test that parsers set correct default currency."""
        parser = parser_class(timezone_service=timezone_service)
        result = parser.parse(test_input)

        assert (
            result.get("currency") == expected_currency
        ), f"{parser_class.__name__} should default to {expected_currency}"

    @pytest.mark.parametrize(
        "parser_class,expected_tz,test_input",
        [
            (AmberParser, "Australia/Sydney", []),
            (StromligningParser, "Europe/Copenhagen", {"prices": []}),
            (EnergiDataParser, "Europe/Copenhagen", {}),
        ],
    )
    def test_default_timezone(
        self, parser_class, expected_tz, test_input, timezone_service
    ):
        """Test that parsers set correct default timezone."""
        parser = parser_class(timezone_service=timezone_service)
        result = parser.parse(test_input)

        assert (
            result.get("timezone") == expected_tz
        ), f"{parser_class.__name__} should default to {expected_tz}"


# ============================================================================
# Test: Interval key format consistency
# ============================================================================


class TestIntervalKeyFormat:
    """Test interval key format consistency."""

    def test_nordpool_uses_iso_keys(self, timezone_service):
        """Test Nordpool parser uses ISO format keys."""
        parser = NordpoolParser(timezone_service=timezone_service)

        test_data = {
            "raw_data": {
                "today": {
                    "multiAreaEntries": [
                        {
                            "deliveryStart": "2025-01-28T00:00:00+01:00",
                            "entryPerArea": {"SE3": 50.0},
                        }
                    ]
                }
            },
            "timezone": "Europe/Stockholm",
            "currency": Currency.EUR,
            "area": "SE3",
            "delivery_area": "SE3",
        }

        result = parser.parse(test_data)

        # Keys should be parseable as ISO datetimes
        for key in result["interval_raw"].keys():
            # Should not raise
            datetime.fromisoformat(key.replace("Z", "+00:00"))

    def test_amber_uses_iso_keys(self, timezone_service):
        """Test Amber parser uses ISO format keys."""
        parser = AmberParser(timezone_service=timezone_service)

        test_data = [{"startTime": "2025-01-28T00:00:00+11:00", "perKwh": 25.5}]

        result = parser.parse(test_data)

        for key in result["interval_raw"].keys():
            # Should not raise
            datetime.fromisoformat(key.replace("Z", "+00:00"))
