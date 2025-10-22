"""Unit tests for AEMO parser (refactored version)."""

import pytest
from datetime import datetime, timedelta
import zoneinfo

from custom_components.ge_spot.api.parsers.aemo_parser import AemoParser
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.const.sources import Source


# Generate current time data for testing
def _generate_current_aemo_data(
    region: str, num_intervals: int = 3, timezone_str: str = "Australia/Sydney"
) -> str:
    """Generate AEMO CSV data with current timestamps.

    Args:
        region: AEMO region code (NSW1, QLD1, etc.)
        num_intervals: Number of 30-minute intervals to generate
        timezone_str: Timezone to use for timestamp generation
    """
    region_tz = zoneinfo.ZoneInfo(timezone_str)
    now = datetime.now(region_tz)

    # Round down to nearest 30 minutes (AEMO trading intervals)
    current_30min = now.replace(minute=(now.minute // 30) * 30, second=0, microsecond=0)

    lines = []
    for i in range(num_intervals):
        interval_time = current_30min + timedelta(minutes=30 * i)
        timestamp = interval_time.strftime("%Y/%m/%d %H:%M:%S")
        price = 150.0 + (i * 10)  # Simple price progression

        lines.append(
            f"D,PREDISPATCH,REGION_PRICES,1,{timestamp},{region},{i+1},0,{timestamp},"
            f"{price:.2f},{price:.2f},{price:.2f},{price:.2f},{price:.2f},{price:.2f},{price:.2f},"
            f"0.0,0.0,0.0,0.0,{timestamp}"
        )

    return "\n".join(lines)


# Sample CSV data matching AEMO NEMWEB format
SAMPLE_CSV_HEADER = "I,PREDISPATCH,REGION_PRICES,1,PREDISPATCH_RUN_DATETIME,REGIONID,PERIODID,INTERVENTION,DATETIME,RRP,EEP,ROP,RAISE6SECRRP,RAISE60SECRRP,RAISE5MINRRP,RAISEREGRRP,LOWER6SECRRP,LOWER60SECRRP,LOWER5MINRRP,LOWERREGRRP,LASTCHANGED"


class TestAemoParser:
    """Test cases for AemoParser."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return AemoParser()

    @pytest.fixture
    def sample_csv_nsw(self):
        """Create sample CSV with NSW1 data (current timestamps)."""
        return f"{SAMPLE_CSV_HEADER}\n{_generate_current_aemo_data('NSW1', 4)}"

    @pytest.fixture
    def sample_csv_qld(self):
        """Create sample CSV with QLD1 data (current timestamps)."""
        return f"{SAMPLE_CSV_HEADER}\n{_generate_current_aemo_data('QLD1', 4, 'Australia/Brisbane')}"

    def test_parse_nsw_data(self, parser, sample_csv_nsw):
        """Test parsing NSW1 region data."""
        # Prepare input data structure
        input_data = {
            "csv_content": sample_csv_nsw,
            "area": "NSW1",
            "timezone": "Australia/Sydney",
            "currency": Currency.AUD,
            "raw_data": {"test": "metadata"},
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

        # Check interval data (4 30-min intervals expanded to 8 15-min intervals)
        interval_raw = result["interval_raw"]
        assert len(interval_raw) == 8  # 4 × 2 (30min → 15min expansion)

        # Verify ISO timestamps are used as keys
        keys = list(interval_raw.keys())
        assert all("T" in key for key in keys)  # ISO format check
        assert all("+" in key or "Z" in key for key in keys)  # Has timezone

        # Verify prices (each 30-min price duplicated twice for 15-min intervals)
        prices = list(interval_raw.values())
        assert len(prices) == 8
        # First 30-min interval (150.00) duplicated twice
        assert prices[0] == 150.0
        assert prices[1] == 150.0
        # Second 30-min interval (160.00) duplicated twice
        assert prices[2] == 160.0
        assert prices[3] == 160.0
        # Third 30-min interval (170.00) duplicated twice
        assert prices[4] == 170.0
        assert prices[5] == 170.0
        # Fourth 30-min interval (180.00) duplicated twice
        assert prices[6] == 180.0
        assert prices[7] == 180.0

    def test_parse_qld_data(self, parser, sample_csv_qld):
        """Test parsing QLD1 region data."""
        input_data = {
            "csv_content": sample_csv_qld,
            "area": "QLD1",
            "timezone": "Australia/Brisbane",
            "currency": Currency.AUD,
            "raw_data": {},
        }

        result = parser.parse(input_data)

        assert result["area"] == "QLD1"
        assert result["timezone"] == "Australia/Brisbane"
        # 4 30-min intervals expanded to 8 15-min intervals
        assert len(result["interval_raw"]) == 8

        # Verify each 30-min price is duplicated twice for 15-min intervals
        prices = list(result["interval_raw"].values())
        assert len(prices) == 8
        # First 30-min interval (150.00) duplicated twice
        assert prices[0] == 150.0
        assert prices[1] == 150.0
        # Second 30-min interval (160.00) duplicated twice
        assert prices[2] == 160.0
        assert prices[3] == 160.0
        # Third 30-min interval (170.00) duplicated twice
        assert prices[4] == 170.0
        assert prices[5] == 170.0
        # Fourth 30-min interval (180.00) duplicated twice
        assert prices[6] == 180.0
        assert prices[7] == 180.0

    def test_parse_invalid_region(self, parser, sample_csv_nsw):
        """Test parsing with region not in CSV data."""
        input_data = {
            "csv_content": sample_csv_nsw,
            "area": "SA1",  # Not in sample data
            "timezone": "Australia/Adelaide",
            "currency": Currency.AUD,
            "raw_data": {},
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
            "raw_data": {},
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
            "raw_data": {},
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
        assert header[0] == "I"
        assert header[1] == "PREDISPATCH"
        assert header[2] == "REGION_PRICES"
        assert "REGIONID" in header
        assert "RRP" in header
        assert "DATETIME" in header

    def test_extract_header_not_found(self, parser):
        """Test header extraction with missing header."""
        csv_no_header = "D,SOME,DATA,1,value"
        header = parser._extract_header(csv_no_header)

        assert header is None

    def test_parse_predispatch_csv(self, parser, sample_csv_nsw):
        """Test CSV parsing method directly."""
        prices = parser._parse_predispatch_csv(sample_csv_nsw, "NSW1")

        assert len(prices) == 4  # Updated to 4 intervals
        assert all("timestamp" in p and "price" in p for p in prices)

        # Check first record - should be current 30-min interval in Sydney time
        # Just verify it's a valid datetime and price
        assert isinstance(prices[0]["timestamp"], datetime)
        assert (
            prices[0]["price"] == 150.0
        )  # First price from _generate_current_aemo_data

        # Verify price progression
        assert prices[1]["price"] == 160.0
        assert prices[2]["price"] == 170.0
        assert prices[3]["price"] == 180.0

    def test_empty_result_structure(self, parser):
        """Test empty result structure."""
        result = parser._create_empty_result(
            {"area": "NSW1", "timezone": "Australia/Sydney"},
            "Australia/Sydney",
            Currency.AUD,
        )

        assert result["interval_raw"] == {}
        assert result["currency"] == Currency.AUD
        assert result["timezone"] == "Australia/Sydney"
        assert result["area"] == "NSW1"
        assert result["source"] == Source.AEMO
        assert result["source_interval_minutes"] == 30
