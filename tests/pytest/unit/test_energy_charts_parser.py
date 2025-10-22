"""Unit tests for Energy-Charts parser."""

import pytest
from datetime import datetime, timezone

from custom_components.ge_spot.api.parsers.energy_charts_parser import EnergyChartsParser
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.const.sources import Source


class TestEnergyChartsParser:
    """Test cases for EnergyChartsParser."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return EnergyChartsParser()

    @pytest.fixture
    def sample_energy_charts_data(self):
        """Create sample Energy-Charts API response (96 15-min intervals)."""
        # Generate 96 data points for one day (15-minute intervals)
        # Starting from midnight 2025-10-07
        unix_seconds = []
        prices = []

        # Start timestamp: 2025-10-07 00:00:00 UTC
        start_timestamp = datetime(2025, 10, 7, 0, 0, 0, tzinfo=timezone.utc).timestamp()

        # Generate 96 intervals (24 hours × 4 intervals/hour)
        for i in range(96):
            # Each interval is 15 minutes (900 seconds) apart
            timestamp = start_timestamp + (i * 900)
            unix_seconds.append(int(timestamp))

            # Realistic price variation (30-150 EUR/MWh)
            # Lower at night, higher during day
            hour_of_day = (i // 4) % 24
            base_price = 50 + (30 * abs(12 - hour_of_day) / 12)  # Peak at noon
            variation = -5 + (i % 4) * 3  # Small 15-min variation
            prices.append(round(base_price + variation, 2))

        return {
            "unix_seconds": unix_seconds,
            "price": prices,
            "unit": "EUR / MWh",
            "license_info": "© Bundesnetzagentur | SMARD.de, CC BY 4.0",
        }

    @pytest.fixture
    def full_input_data(self, sample_energy_charts_data):
        """Create full input data structure as provided by EnergyChartsAPI."""
        return {
            "raw_data": sample_energy_charts_data,
            "timezone": "Europe/Berlin",
            "currency": Currency.EUR,
            "area": "DE-LU",
            "bzn": "DE-LU",
            "source": Source.ENERGY_CHARTS,
            "fetched_at": "2025-10-07T12:00:00Z",
            "license_info": sample_energy_charts_data["license_info"],
        }

    def test_parse_de_lu_data(self, parser, full_input_data):
        """Test parsing DE-LU (Germany-Luxembourg) data."""
        result = parser.parse(full_input_data)

        # Check structure
        assert "interval_raw" in result
        assert "currency" in result
        assert "timezone" in result
        assert "source" in result
        assert "source_unit" in result

        # Check values
        assert result["currency"] == Currency.EUR
        assert result["timezone"] == "Europe/Berlin"
        assert result["source"] == Source.ENERGY_CHARTS
        assert result["area"] == "DE-LU"
        assert result["source_unit"] == "MWh"

        # Check interval data (96 15-min intervals for one day)
        interval_raw = result["interval_raw"]
        assert len(interval_raw) == 96, f"Expected 96 intervals, got {len(interval_raw)}"

        # Verify ISO timestamps are used as keys
        keys = list(interval_raw.keys())
        assert all("2025-10-07" in key for key in keys)
        assert all("T" in key for key in keys)  # ISO format check
        assert all("+00:00" in key or "Z" in key for key in keys)  # UTC timezone

        # Verify prices are numeric
        prices = list(interval_raw.values())
        assert all(isinstance(p, float) for p in prices)

        # Verify prices are in reasonable range (EUR/MWh)
        assert all(0 <= p <= 500 for p in prices), "Prices should be in reasonable range"

    def test_parse_fr_data(self, parser, sample_energy_charts_data):
        """Test parsing France data."""
        input_data = {
            "raw_data": sample_energy_charts_data,
            "timezone": "Europe/Berlin",
            "currency": Currency.EUR,
            "area": "FR",
            "bzn": "FR",
            "source": Source.ENERGY_CHARTS,
            "license_info": "",
        }

        result = parser.parse(input_data)

        assert result["area"] == "FR"
        assert result["timezone"] == "Europe/Berlin"
        assert len(result["interval_raw"]) == 96

    def test_parse_empty_data(self, parser):
        """Test parsing with empty price arrays."""
        input_data = {
            "raw_data": {"unix_seconds": [], "price": [], "unit": "EUR / MWh"},
            "timezone": "Europe/Berlin",
            "currency": Currency.EUR,
            "area": "NL",
        }

        result = parser.parse(input_data)

        # Should return empty but valid structure
        assert len(result["interval_raw"]) == 0
        assert result["currency"] == Currency.EUR
        assert result["source"] == Source.ENERGY_CHARTS

    def test_parse_missing_raw_data(self, parser):
        """Test parsing with missing raw_data key."""
        input_data = {"timezone": "Europe/Berlin", "currency": Currency.EUR, "area": "BE"}

        result = parser.parse(input_data)

        # Should return empty result
        assert len(result["interval_raw"]) == 0

    def test_parse_mismatched_arrays(self, parser):
        """Test parsing with mismatched timestamp/price arrays."""
        input_data = {
            "raw_data": {
                "unix_seconds": [1696636800, 1696637700],  # 2 timestamps
                "price": [105.51],  # 1 price - mismatch!
                "unit": "EUR / MWh",
            },
            "timezone": "Europe/Berlin",
            "currency": Currency.EUR,
            "area": "AT",
        }

        result = parser.parse(input_data)

        # Should return empty result due to mismatch
        assert len(result["interval_raw"]) == 0

    def test_parse_invalid_timestamp(self, parser):
        """Test parsing with invalid unix timestamp."""
        input_data = {
            "raw_data": {
                "unix_seconds": ["invalid", 1696637700],  # Invalid timestamp
                "price": [105.51, 102.60],
                "unit": "EUR / MWh",
            },
            "timezone": "Europe/Berlin",
            "currency": Currency.EUR,
            "area": "CH",
        }

        result = parser.parse(input_data)

        # Should skip invalid entry but parse valid one
        assert 0 <= len(result["interval_raw"]) <= 1

    def test_parse_invalid_price(self, parser):
        """Test parsing with invalid price value."""
        input_data = {
            "raw_data": {
                "unix_seconds": [1696636800, 1696637700],
                "price": ["invalid", 102.60],  # Invalid price
                "unit": "EUR / MWh",
            },
            "timezone": "Europe/Berlin",
            "currency": Currency.EUR,
            "area": "PL",
        }

        result = parser.parse(input_data)

        # Should skip invalid entry but parse valid one
        assert 0 <= len(result["interval_raw"]) <= 1

    def test_timestamp_conversion(self, parser):
        """Test unix timestamp to ISO format conversion."""
        # 2024-10-07 12:00:00 UTC (correct unix timestamp)
        unix_ts = 1728302400

        input_data = {
            "raw_data": {"unix_seconds": [unix_ts], "price": [100.0], "unit": "EUR / MWh"},
            "timezone": "Europe/Berlin",
            "currency": Currency.EUR,
            "area": "DE-LU",
        }

        result = parser.parse(input_data)

        # Check timestamp format
        keys = list(result["interval_raw"].keys())
        assert len(keys) == 1

        # Verify ISO format
        timestamp_str = keys[0]
        assert "T" in timestamp_str

        # Verify timestamp can be parsed back
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        assert dt.year == 2024
        assert dt.month == 10
        assert dt.day == 7

    def test_validate_success(self, parser, full_input_data):
        """Test validation with valid data."""
        result = parser.parse(full_input_data)

        # Validation should pass
        assert parser.validate(result) is True

    def test_validate_missing_field(self, parser):
        """Test validation with missing required field."""
        invalid_data = {
            "interval_raw": {"2025-10-07T12:00:00+00:00": 100.0},
            "currency": Currency.EUR,
            # Missing "timezone" and "source_unit"
        }

        assert parser.validate(invalid_data) is False

    def test_validate_invalid_timestamp(self, parser):
        """Test validation with invalid timestamp format."""
        invalid_data = {
            "interval_raw": {"invalid-timestamp": 100.0},
            "currency": Currency.EUR,
            "timezone": "Europe/Berlin",
            "source_unit": "MWh",
        }

        assert parser.validate(invalid_data) is False

    def test_validate_invalid_price_type(self, parser):
        """Test validation with non-numeric price."""
        invalid_data = {
            "interval_raw": {"2025-10-07T12:00:00+00:00": "invalid"},
            "currency": Currency.EUR,
            "timezone": "Europe/Berlin",
            "source_unit": "MWh",
        }

        assert parser.validate(invalid_data) is False

    def test_create_empty_result(self, parser):
        """Test empty result structure."""
        original_data = {"area": "DE-LU", "timezone": "Europe/Berlin", "currency": Currency.EUR}

        result = parser._create_empty_result(original_data, "Europe/Berlin", Currency.EUR)

        assert result["interval_raw"] == {}
        assert result["currency"] == Currency.EUR
        assert result["timezone"] == "Europe/Berlin"
        assert result["source"] == Source.ENERGY_CHARTS
        assert result["source_unit"] == "MWh"

    def test_license_info_preserved(self, parser, full_input_data):
        """Test that license information is preserved in parsed data."""
        result = parser.parse(full_input_data)

        assert "license_info" in result
        assert "Bundesnetzagentur" in result["license_info"]
        assert "CC BY 4.0" in result["license_info"]

    def test_multiple_bidding_zones(self, parser, sample_energy_charts_data):
        """Test parsing for different bidding zones."""
        zones = ["DE-LU", "FR", "NL", "BE", "AT", "CH", "PL", "DK1", "DK2"]

        for zone in zones:
            input_data = {
                "raw_data": sample_energy_charts_data,
                "timezone": "Europe/Berlin",
                "currency": Currency.EUR,
                "area": zone,
                "bzn": zone,
                "source": Source.ENERGY_CHARTS,
                "license_info": "",
            }

            result = parser.parse(input_data)

            assert result["area"] == zone
            assert len(result["interval_raw"]) == 96
            assert result["source"] == Source.ENERGY_CHARTS
