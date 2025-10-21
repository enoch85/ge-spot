"""Test that all parsers display correct source names in validation error messages.

This test verifies that parsers were initialized correctly with string source values,
not TimezoneService objects, by triggering validation failures and checking the
error messages.

The bug being tested: Previously, parsers could be initialized with TimezoneService
as the first argument, causing error messages to show:
    <custom_components.ge_spot.timezone.service.TimezoneService object at 0x7f2809715be0>
instead of the actual source name like "aemo" or "nordpool".
"""
import logging
from datetime import datetime, timezone, timedelta
import pytest

from custom_components.ge_spot.api.parsers import (
    NordpoolParser,
    EntsoeParser,
    AemoParser,
    EnergiDataParser,
    EnergyChartsParser,
    OmieParser,
    ComedParser,
    StromligningParser,
    get_parser_for_source
)
from custom_components.ge_spot.const.sources import Source


class TestParserSourceValidation:
    """Test that parsers show correct source names in validation errors."""

    @pytest.fixture
    def all_parsers(self):
        """Provide all parser instances for testing."""
        return {
            Source.NORDPOOL: NordpoolParser(),
            Source.ENTSOE: EntsoeParser(),
            Source.AEMO: AemoParser(),
            Source.ENERGI_DATA_SERVICE: EnergiDataParser(),
            Source.ENERGY_CHARTS: EnergyChartsParser(),
            Source.OMIE: OmieParser(),
            Source.COMED: ComedParser(),
            Source.STROMLIGNING: StromligningParser(),
        }

    def test_parser_source_is_string(self, all_parsers):
        """Test that all parsers have string source attributes."""
        for source_name, parser in all_parsers.items():
            assert isinstance(parser.source, str), (
                f"Parser for {source_name} has non-string source: "
                f"{type(parser.source).__name__}"
            )
            assert parser.source == source_name, (
                f"Parser source mismatch: expected '{source_name}', "
                f"got '{parser.source}'"
            )

    def test_parser_validation_empty_interval_raw(self, all_parsers, caplog):
        """Test validation error messages with empty interval_raw data."""
        for source_name, parser in all_parsers.items():
            caplog.clear()
            
            # Create data with empty interval_raw - should fail validation
            test_data = {
                "interval_raw": {},
                "currency": "EUR"
            }
            
            with caplog.at_level(logging.WARNING):
                result = parser.validate_parsed_data(test_data)
            
            # Should fail validation
            assert result is False, f"{source_name} should fail validation with empty data"
            
            # Check that error message contains correct source name
            warning_messages = [rec.message for rec in caplog.records if rec.levelname == "WARNING"]
            assert len(warning_messages) > 0, f"No warning logged for {source_name}"
            
            # Verify the source name appears in the message
            found_source_in_message = any(source_name in msg for msg in warning_messages)
            assert found_source_in_message, (
                f"Source name '{source_name}' not found in warning messages: {warning_messages}"
            )
            
            # Verify NO TimezoneService object reference appears
            for msg in warning_messages:
                assert "TimezoneService object at 0x" not in msg, (
                    f"TimezoneService object leak detected in {source_name}: {msg}"
                )
                assert "<custom_components.ge_spot.timezone.service.TimezoneService" not in msg, (
                    f"TimezoneService object leak detected in {source_name}: {msg}"
                )

    def test_parser_validation_missing_current_price(self, all_parsers, caplog):
        """Test validation accepts data with valid structure regardless of time.
        
        Parser validation checks ONLY structural integrity:
        - interval_raw exists and is a dict
        - Has at least one price
        - Has required metadata (timezone, currency)
        
        Parser does NOT check time-based requirements like "current interval exists".
        That's business logic handled by DataProcessor after timezone conversion.
        """
        for source_name, parser in all_parsers.items():
            caplog.clear()
            
            # Create structurally valid data with interval_raw that includes metadata
            # Time of price is irrelevant for structural validation
            past_time = datetime.now(timezone.utc) - timedelta(hours=2)
            test_data = {
                "interval_raw": {
                    past_time.isoformat(): 50.0
                },
                "currency": "EUR",
                "timezone": "Europe/Amsterdam"
            }
            
            with caplog.at_level(logging.DEBUG):
                result = parser.validate_parsed_data(test_data)
            
            # Should PASS validation - structure is valid
            assert result is True, (
                f"{source_name} should accept structurally valid data "
                f"(validation checks structure, not business logic)"
            )
            
            # Check for DEBUG message confirming structural validity
            debug_messages = [rec.message for rec in caplog.records if rec.levelname == "DEBUG"]
            
            # Should log that structure is valid
            assert any("structure valid" in msg.lower() for msg in debug_messages), (
                f"{source_name} should log DEBUG about structural validity"
            )

    def test_parser_factory_creates_correct_parsers(self):
        """Test that get_parser_for_source creates parsers with correct sources."""
        test_sources = [
            Source.NORDPOOL,
            Source.ENTSOE,
            Source.AEMO,
            Source.ENERGI_DATA_SERVICE,
            Source.ENERGY_CHARTS,
            Source.OMIE,
            Source.COMED,
            Source.STROMLIGNING,
        ]
        
        for source in test_sources:
            parser = get_parser_for_source(source)
            
            # Verify source is a string
            assert isinstance(parser.source, str), (
                f"Factory-created parser for {source} has non-string source: "
                f"{type(parser.source).__name__}"
            )
            
            # Verify source matches
            assert parser.source == source, (
                f"Factory-created parser source mismatch: expected '{source}', "
                f"got '{parser.source}'"
            )

    def test_parser_class_names_consistency(self, all_parsers):
        """Test that parser class names follow consistent naming pattern."""
        expected_names = {
            Source.NORDPOOL: "NordpoolParser",
            Source.ENTSOE: "EntsoeParser",
            Source.AEMO: "AemoParser",
            Source.ENERGI_DATA_SERVICE: "EnergiDataParser",
            Source.ENERGY_CHARTS: "EnergyChartsParser",
            Source.OMIE: "OmieParser",
            Source.COMED: "ComedParser",
            Source.STROMLIGNING: "StromligningParser",
        }
        
        for source_name, parser in all_parsers.items():
            expected_class_name = expected_names[source_name]
            actual_class_name = parser.__class__.__name__
            
            assert actual_class_name == expected_class_name, (
                f"Parser class name mismatch for {source_name}: "
                f"expected '{expected_class_name}', got '{actual_class_name}'"
            )

    def test_parser_initialization_with_timezone_service(self):
        """Test that parsers can be initialized with timezone_service parameter."""
        from custom_components.ge_spot.timezone.service import TimezoneService
        
        tz_service = TimezoneService()
        
        # Test that parsers accept timezone_service as second parameter
        parsers_to_test = [
            (NordpoolParser, Source.NORDPOOL),
            (EntsoeParser, Source.ENTSOE),
            (AemoParser, Source.AEMO),
            (EnergiDataParser, Source.ENERGI_DATA_SERVICE),
            (ComedParser, Source.COMED),
        ]
        
        for parser_class, expected_source in parsers_to_test:
            # Initialize with timezone_service
            parser = parser_class(timezone_service=tz_service)
            
            # Verify source is still a string
            assert isinstance(parser.source, str), (
                f"{parser_class.__name__} initialized with timezone_service has "
                f"non-string source: {type(parser.source).__name__}"
            )
            
            # Verify source is correct
            assert parser.source == expected_source, (
                f"{parser_class.__name__} source mismatch: "
                f"expected '{expected_source}', got '{parser.source}'"
            )
            
            # Verify timezone_service is set correctly
            assert parser.timezone_service is not None, (
                f"{parser_class.__name__} timezone_service not set"
            )

    def test_no_timezone_service_in_source_attribute(self, all_parsers):
        """Explicit test that source attribute is never a TimezoneService object."""
        from custom_components.ge_spot.timezone.service import TimezoneService
        
        for source_name, parser in all_parsers.items():
            # This is the critical test - source should NEVER be a TimezoneService
            assert not isinstance(parser.source, TimezoneService), (
                f"CRITICAL BUG: Parser for {source_name} has TimezoneService as source! "
                f"This causes error messages to show object memory addresses instead of source names."
            )
            
            # Double-check it's a string
            assert isinstance(parser.source, str), (
                f"Parser for {source_name} source is not a string: {type(parser.source)}"
            )
