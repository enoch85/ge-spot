"""Unit tests for AEMO parser (refactored version)."""

import pytest
from datetime import datetime

from custom_components.ge_spot.api.parsers.aemo_parser import AemoParser
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.const.sources import Source


# Sample CSV data matching AEMO NEMWEB format
SAMPLE_CSV_HEADER = 'I,PREDISPATCH,REGION_PRICES,1,PREDISPATCH_RUN_DATETIME,REGIONID,PERIODID,INTERVENTION,DATETIME,RRP,EEP,ROP,RAISE6SECRRP,RAISE60SECRRP,RAISE5MINRRP,RAISEREGRRP,LOWER6SECRRP,LOWER60SECRRP,LOWER5MINRRP,LOWERREGRRP,LASTCHANGED'

SAMPLE_CSV_DATA_NSW = """D,PREDISPATCH,REGION_PRICES,1,2025/10/07 00:33:36,NSW1,1,0,2025/10/07 01:00:00,176.03,176.03,176.03,176.03,176.03,176.03,176.03,0.0,0.0,0.0,0.0,2025/10/07 00:33:36
D,PREDISPATCH,REGION_PRICES,1,2025/10/07 00:33:36,NSW1,2,0,2025/10/07 01:30:00,155.26,155.26,155.26,155.26,155.26,155.26,155.26,0.0,0.0,0.0,0.0,2025/10/07 00:33:36
D,PREDISPATCH,REGION_PRICES,1,2025/10/07 00:33:36,NSW1,3,0,2025/10/07 02:00:00,132.77,132.77,132.77,132.77,132.77,132.77,132.77,0.0,0.0,0.0,0.0,2025/10/07 00:33:36"""

SAMPLE_CSV_DATA_QLD = """D,PREDISPATCH,REGION_PRICES,1,2025/10/07 00:33:36,QLD1,1,0,2025/10/07 01:00:00,95.50,95.50,95.50,95.50,95.50,95.50,95.50,0.0,0.0,0.0,0.0,2025/10/07 00:33:36
D,PREDISPATCH,REGION_PRICES,1,2025/10/07 00:33:36,QLD1,2,0,2025/10/07 01:30:00,88.25,88.25,88.25,88.25,88.25,88.25,88.25,0.0,0.0,0.0,0.0,2025/10/07 00:33:36"""


class TestAemoParser:
    """Test cases for AemoParser."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return AemoParser()

    @pytest.fixture
    def sample_csv_nsw(self):
        """Create sample CSV with NSW1 data."""
        return f"{SAMPLE_CSV_HEADER}\n{SAMPLE_CSV_DATA_NSW}"

    @pytest.fixture
    def sample_csv_qld(self):
        """Create sample CSV with QLD1 data."""
        return f"{SAMPLE_CSV_HEADER}\n{SAMPLE_CSV_DATA_QLD}"

    def test_parse_nsw_data(self, parser, sample_csv_nsw):
        """Test parsing NSW1 region data."""
        # Prepare input data structure
        input_data = {
            "csv_content": sample_csv_nsw,
            "area": "NSW1",
            "timezone": "Australia/Sydney",
            "currency": Currency.AUD,
            "raw_data": {"test": "metadata"}
        }
        
        result = parser.parse(input_data)
        
        # Check structure
        assert "interval_raw" in result
        assert "currency" in result
        assert "timezone" in result
        assert "source" in result
        
        # Check values
        assert result["currency"] == Currency.AUD
        assert result["timezone"] == "Australia/Sydney"
        assert result["source"] == Source.AEMO
        assert result["area"] == "NSW1"
        assert result["source_interval_minutes"] == 30
        
        # Check interval data (3 30-min intervals expanded to 6 15-min intervals)
        interval_raw = result["interval_raw"]
        assert len(interval_raw) == 6  # 3 × 2 (30min → 15min expansion)
        
        # Verify ISO timestamps are used as keys
        keys = list(interval_raw.keys())
        assert all("2025-10-07" in key for key in keys)
        assert all("T" in key for key in keys)  # ISO format check
        
        # Verify prices (each 30-min price duplicated twice for 15-min intervals)
        prices = list(interval_raw.values())
        assert prices.count(176.03) == 2  # Duplicated for 01:00 and 01:15
        assert prices.count(155.26) == 2  # Duplicated for 01:30 and 01:45
        assert prices.count(132.77) == 2  # Duplicated for 02:00 and 02:15

    def test_parse_qld_data(self, parser, sample_csv_qld):
        """Test parsing QLD1 region data."""
        input_data = {
            "csv_content": sample_csv_qld,
            "area": "QLD1",
            "timezone": "Australia/Brisbane",
            "currency": Currency.AUD,
            "raw_data": {}
        }
        
        result = parser.parse(input_data)
        
        assert result["area"] == "QLD1"
        assert result["timezone"] == "Australia/Brisbane"
        # 2 30-min intervals expanded to 4 15-min intervals
        assert len(result["interval_raw"]) == 4
        
        # Verify each 30-min price is duplicated twice for 15-min intervals
        prices = list(result["interval_raw"].values())
        assert prices.count(95.50) == 2
        assert prices.count(88.25) == 2

    def test_parse_invalid_region(self, parser, sample_csv_nsw):
        """Test parsing with region not in CSV data."""
        input_data = {
            "csv_content": sample_csv_nsw,
            "area": "SA1",  # Not in sample data
            "timezone": "Australia/Adelaide",
            "currency": Currency.AUD,
            "raw_data": {}
        }
        
        result = parser.parse(input_data)
        
        # Should return empty result
        assert len(result["interval_raw"]) == 0

    def test_parse_no_csv_content(self, parser):
        """Test parsing with missing CSV content."""
        input_data = {
            "area": "NSW1",
            "timezone": "Australia/Sydney",
            "currency": Currency.AUD,
            "raw_data": {}
        }
        
        result = parser.parse(input_data)
        
        # Should return empty result
        assert len(result["interval_raw"]) == 0

    def test_parse_no_area(self, parser, sample_csv_nsw):
        """Test parsing with missing area."""
        input_data = {
            "csv_content": sample_csv_nsw,
            "timezone": "Australia/Sydney",
            "currency": Currency.AUD,
            "raw_data": {}
        }
        
        result = parser.parse(input_data)
        
        # Should return empty result
        assert len(result["interval_raw"]) == 0

    def test_parse_datetime_format(self, parser):
        """Test datetime parsing."""
        # Test valid datetime
        dt = parser._parse_datetime("2025/10/07 01:30:00")
        assert dt.year == 2025
        assert dt.month == 10
        assert dt.day == 7
        assert dt.hour == 1
        assert dt.minute == 30
        assert dt.second == 0

    def test_parse_datetime_invalid(self, parser):
        """Test datetime parsing with invalid format."""
        with pytest.raises(ValueError):
            parser._parse_datetime("invalid-datetime")

    def test_extract_header(self, parser, sample_csv_nsw):
        """Test header extraction."""
        header = parser._extract_header(sample_csv_nsw)
        
        assert header is not None
        assert header[0] == 'I'
        assert header[1] == 'PREDISPATCH'
        assert header[2] == 'REGION_PRICES'
        assert 'REGIONID' in header
        assert 'RRP' in header
        assert 'DATETIME' in header

    def test_extract_header_not_found(self, parser):
        """Test header extraction with missing header."""
        csv_no_header = "D,SOME,DATA,1,value"
        header = parser._extract_header(csv_no_header)
        
        assert header is None

    def test_parse_predispatch_csv(self, parser, sample_csv_nsw):
        """Test CSV parsing method directly."""
        prices = parser._parse_predispatch_csv(sample_csv_nsw, "NSW1")
        
        assert len(prices) == 3
        assert all("timestamp" in p and "price" in p for p in prices)
        
        # Check first record
        assert prices[0]["timestamp"] == datetime(2025, 10, 7, 1, 0, 0)
        assert prices[0]["price"] == 176.03

    def test_empty_result_structure(self, parser):
        """Test empty result structure."""
        result = parser._create_empty_result(
            {"area": "NSW1", "timezone": "Australia/Sydney"},
            "Australia/Sydney",
            Currency.AUD
        )
        
        assert result["interval_raw"] == {}
        assert result["currency"] == Currency.AUD
        assert result["timezone"] == "Australia/Sydney"
        assert result["area"] == "NSW1"
        assert result["source"] == Source.AEMO
        assert result["source_interval_minutes"] == 30
