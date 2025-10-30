"""Test IntervalPriceData model with computed properties."""

import pytest
from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from custom_components.ge_spot.coordinator.data_models import IntervalPriceData
from custom_components.ge_spot.coordinator.data_validity import DataValidity
from custom_components.ge_spot.api.base.data_structure import PriceStatistics


@pytest.fixture
def mock_timezone_service():
    """Create a mock timezone service."""
    tz_service = Mock()
    tz_service.target_timezone = ZoneInfo("Europe/Stockholm")
    tz_service.get_current_interval_key.return_value = "14:15"
    tz_service.get_next_interval_key.return_value = "14:30"
    return tz_service


@pytest.fixture
def sample_today_prices():
    """Create sample today prices (96 intervals)."""
    return {f"{h:02d}:{m:02d}": 100.0 + h for h in range(24) for m in [0, 15, 30, 45]}


@pytest.fixture
def sample_tomorrow_prices():
    """Create sample tomorrow prices (96 intervals)."""
    return {f"{h:02d}:{m:02d}": 200.0 + h for h in range(24) for m in [0, 15, 30, 45]}


@pytest.fixture
def sample_raw_prices():
    """Create sample raw prices (without VAT)."""
    return {f"{h:02d}:{m:02d}": 90.0 + h for h in range(24) for m in [0, 15, 30, 45]}


class TestIntervalPriceDataCreation:
    """Test creating IntervalPriceData instances."""

    def test_create_empty_data_model(self):
        """Test creating empty data model."""
        data = IntervalPriceData()

        assert data.today_interval_prices == {}
        assert data.tomorrow_interval_prices == {}
        assert data.source == ""
        assert data.area == ""
        assert data.vat_rate == 0.0
        assert data.vat_included is False
        assert data.migrated_from_tomorrow is False

    def test_create_with_source_data(self, sample_today_prices, sample_tomorrow_prices):
        """Test creating with source data."""
        data = IntervalPriceData(
            today_interval_prices=sample_today_prices,
            tomorrow_interval_prices=sample_tomorrow_prices,
            source="nordpool",
            area="SE3",
            source_currency="EUR",
            target_currency="SEK",
        )

        assert len(data.today_interval_prices) == 96
        assert len(data.tomorrow_interval_prices) == 96
        assert data.source == "nordpool"
        assert data.area == "SE3"
        assert data.source_currency == "EUR"
        assert data.target_currency == "SEK"

    def test_create_with_metadata(self):
        """Test creating with full metadata."""
        data = IntervalPriceData(
            source="nordpool",
            area="SE3",
            source_currency="EUR",
            target_currency="SEK",
            source_timezone="Europe/Oslo",
            target_timezone="Europe/Stockholm",
            ecb_rate=11.5,
            ecb_updated="2025-10-30T12:00:00Z",
            vat_rate=0.25,
            vat_included=True,
            display_unit="SEK/kWh",
            fetched_at="2025-10-30T14:00:00Z",
        )

        assert data.source == "nordpool"
        assert data.area == "SE3"
        assert data.ecb_rate == 11.5
        assert data.vat_rate == 0.25
        assert data.vat_included is True
        assert data.display_unit == "SEK/kWh"


class TestComputedProperties:
    """Test computed properties calculate correctly."""

    def test_has_tomorrow_prices_true(self, sample_tomorrow_prices):
        """Test has_tomorrow_prices returns True when prices exist."""
        data = IntervalPriceData(tomorrow_interval_prices=sample_tomorrow_prices)

        assert data.has_tomorrow_prices is True

    def test_has_tomorrow_prices_false(self):
        """Test has_tomorrow_prices returns False when no prices."""
        data = IntervalPriceData()

        assert data.has_tomorrow_prices is False

    def test_statistics_calculation(self, sample_today_prices):
        """Test statistics computed from today's prices."""
        data = IntervalPriceData(today_interval_prices=sample_today_prices)

        stats = data.statistics

        assert stats.avg is not None
        assert stats.min == 100.0  # First hour
        assert stats.max == 123.0  # Last hour
        assert stats.min_timestamp is not None
        assert stats.max_timestamp is not None

    def test_statistics_empty_when_no_prices(self):
        """Test statistics return empty when no prices."""
        data = IntervalPriceData()

        stats = data.statistics

        assert stats.avg is None
        assert stats.min is None
        assert stats.max is None

    def test_tomorrow_statistics_calculation(self, sample_tomorrow_prices):
        """Test tomorrow_statistics computed from tomorrow's prices."""
        data = IntervalPriceData(tomorrow_interval_prices=sample_tomorrow_prices)

        stats = data.tomorrow_statistics

        assert stats.avg is not None
        assert stats.min == 200.0
        assert stats.max == 223.0

    def test_current_price_lookup(self, sample_today_prices, mock_timezone_service):
        """Test current_price looks up correct interval."""
        data = IntervalPriceData(
            today_interval_prices=sample_today_prices, _tz_service=mock_timezone_service
        )

        current_price = data.current_price

        # Current interval is 14:15, price should be 100 + 14 = 114
        assert current_price == 114.0

    def test_current_price_none_without_tz_service(self, sample_today_prices):
        """Test current_price returns None without timezone service."""
        data = IntervalPriceData(today_interval_prices=sample_today_prices)

        assert data.current_price is None

    def test_next_interval_price_lookup(
        self, sample_today_prices, mock_timezone_service
    ):
        """Test next_interval_price looks up correct interval."""
        data = IntervalPriceData(
            today_interval_prices=sample_today_prices, _tz_service=mock_timezone_service
        )

        next_price = data.next_interval_price

        # Next interval is 14:30, price should be 100 + 14 = 114
        assert next_price == 114.0

    def test_next_interval_price_from_tomorrow(
        self, sample_today_prices, sample_tomorrow_prices, mock_timezone_service
    ):
        """Test next_interval_price falls back to tomorrow."""
        # Set next interval to 00:00 (which would be tomorrow after 23:45)
        # But remove 00:00 from today prices to force lookup in tomorrow
        today_without_midnight = {
            k: v for k, v in sample_today_prices.items() if k != "00:00"
        }
        mock_timezone_service.get_next_interval_key.return_value = "00:00"

        data = IntervalPriceData(
            today_interval_prices=today_without_midnight,
            tomorrow_interval_prices=sample_tomorrow_prices,
            _tz_service=mock_timezone_service,
        )

        next_price = data.next_interval_price

        # Next interval is 00:00 tomorrow, price should be 200.0
        assert next_price == 200.0

    def test_current_interval_key_property(self, mock_timezone_service):
        """Test current_interval_key property."""
        data = IntervalPriceData(_tz_service=mock_timezone_service)

        assert data.current_interval_key == "14:15"

    def test_next_interval_key_property(self, mock_timezone_service):
        """Test next_interval_key property."""
        data = IntervalPriceData(_tz_service=mock_timezone_service)

        assert data.next_interval_key == "14:30"

    def test_tomorrow_valid_true_with_96_intervals(self, sample_tomorrow_prices):
        """Test tomorrow_valid returns True with 96 intervals."""
        data = IntervalPriceData(tomorrow_interval_prices=sample_tomorrow_prices)

        assert data.tomorrow_valid is True

    def test_tomorrow_valid_true_with_dst_intervals(self):
        """Test tomorrow_valid handles DST (92-100 intervals)."""
        # 92 intervals (spring DST)
        prices_92 = {f"{i:04d}": 100.0 for i in range(92)}
        data = IntervalPriceData(tomorrow_interval_prices=prices_92)
        assert data.tomorrow_valid is True

        # 100 intervals (fall DST)
        prices_100 = {f"{i:04d}": 100.0 for i in range(100)}
        data = IntervalPriceData(tomorrow_interval_prices=prices_100)
        assert data.tomorrow_valid is True

    def test_tomorrow_valid_false_with_incomplete_data(self):
        """Test tomorrow_valid returns False with incomplete data."""
        # Only 50 intervals
        incomplete_prices = {
            f"{h:02d}:{m:02d}": 100.0 for h in range(13) for m in [0, 15, 30, 45]
        }
        data = IntervalPriceData(tomorrow_interval_prices=incomplete_prices)

        assert data.tomorrow_valid is False

    def test_data_validity_calculation(
        self, sample_today_prices, sample_tomorrow_prices, mock_timezone_service
    ):
        """Test data_validity property computes correctly."""
        data = IntervalPriceData(
            today_interval_prices=sample_today_prices,
            tomorrow_interval_prices=sample_tomorrow_prices,
            target_timezone="Europe/Stockholm",
            _tz_service=mock_timezone_service,
        )

        validity = data.data_validity

        assert isinstance(validity, DataValidity)
        assert validity.today_interval_count == 96
        assert validity.tomorrow_interval_count == 96
        assert validity.interval_count == 192
        assert validity.has_current_interval is True

    def test_data_validity_empty_without_tz_service(self):
        """Test data_validity returns empty without timezone service."""
        data = IntervalPriceData(today_interval_prices={"14:00": 100.0})

        validity = data.data_validity

        assert isinstance(validity, DataValidity)
        assert validity.interval_count == 0


class TestMigration:
    """Test migrate_to_new_day() method."""

    def test_migrate_moves_tomorrow_to_today(
        self, sample_today_prices, sample_tomorrow_prices, sample_raw_prices
    ):
        """Test migration moves tomorrow data to today."""
        tomorrow_raw = {
            f"{h:02d}:{m:02d}": 190.0 + h for h in range(24) for m in [0, 15, 30, 45]
        }

        data = IntervalPriceData(
            today_interval_prices=sample_today_prices,
            tomorrow_interval_prices=sample_tomorrow_prices,
            today_raw_prices=sample_raw_prices,
            tomorrow_raw_prices=tomorrow_raw,
        )

        # Before migration
        assert len(data.today_interval_prices) == 96
        assert len(data.tomorrow_interval_prices) == 96
        assert data.today_interval_prices["00:00"] == 100.0
        assert data.tomorrow_interval_prices["00:00"] == 200.0

        # Migrate
        data.migrate_to_new_day()

        # After migration
        assert len(data.today_interval_prices) == 96
        assert len(data.tomorrow_interval_prices) == 0
        assert data.today_interval_prices["00:00"] == 200.0  # From tomorrow
        assert data.today_raw_prices["00:00"] == 190.0  # Raw also moved

    def test_migrate_clears_tomorrow(self, sample_tomorrow_prices):
        """Test migration clears tomorrow prices."""
        data = IntervalPriceData(tomorrow_interval_prices=sample_tomorrow_prices)

        data.migrate_to_new_day()

        assert data.tomorrow_interval_prices == {}
        assert data.tomorrow_raw_prices == {}

    def test_migrate_sets_flag(self, sample_tomorrow_prices):
        """Test migration sets migrated_from_tomorrow flag."""
        data = IntervalPriceData(tomorrow_interval_prices=sample_tomorrow_prices)

        assert data.migrated_from_tomorrow is False

        data.migrate_to_new_day()

        assert data.migrated_from_tomorrow is True

    def test_migrate_updates_timestamp(self, sample_tomorrow_prices):
        """Test migration updates last_updated timestamp."""
        data = IntervalPriceData(tomorrow_interval_prices=sample_tomorrow_prices)

        assert data.last_updated is None

        data.migrate_to_new_day()

        assert data.last_updated is not None

    def test_migrate_recomputes_properties(
        self, sample_tomorrow_prices, mock_timezone_service
    ):
        """Test properties recompute after migration (Issue #44 fix)."""
        data = IntervalPriceData(
            today_interval_prices={},
            tomorrow_interval_prices=sample_tomorrow_prices,
            target_timezone="Europe/Stockholm",
            _tz_service=mock_timezone_service,
        )

        # Before migration: no today data
        validity_before = data.data_validity
        assert validity_before.today_interval_count == 0
        assert validity_before.tomorrow_interval_count == 96

        # Migrate
        data.migrate_to_new_day()

        # After migration: properties auto-recompute!
        validity_after = data.data_validity
        assert validity_after.today_interval_count == 96  # Now has today data
        assert validity_after.tomorrow_interval_count == 0  # Tomorrow cleared

        # This is the key fix for Issue #44: validity is ALWAYS computed fresh


class TestSerialization:
    """Test serialization methods."""

    def test_to_cache_dict_stores_source_data_only(
        self, sample_today_prices, sample_tomorrow_prices
    ):
        """Test to_cache_dict stores only source data, not computed properties."""
        data = IntervalPriceData(
            today_interval_prices=sample_today_prices,
            tomorrow_interval_prices=sample_tomorrow_prices,
            source="nordpool",
            area="SE3",
            ecb_rate=11.5,
            vat_rate=0.25,
        )

        cache_dict = data.to_cache_dict()

        # Source data should be present
        assert cache_dict["today_interval_prices"] == sample_today_prices
        assert cache_dict["tomorrow_interval_prices"] == sample_tomorrow_prices
        assert cache_dict["source"] == "nordpool"
        assert cache_dict["area"] == "SE3"
        assert cache_dict["ecb_rate"] == 11.5
        assert cache_dict["vat_rate"] == 0.25

        # Computed properties should NOT be in cache dict
        assert "data_validity" not in cache_dict
        assert "statistics" not in cache_dict
        assert "tomorrow_statistics" not in cache_dict
        assert "has_tomorrow_prices" not in cache_dict
        assert "current_price" not in cache_dict

    def test_from_cache_dict_reconstructs_data(
        self, sample_today_prices, mock_timezone_service
    ):
        """Test from_cache_dict reconstructs data model."""
        cache_dict = {
            "today_interval_prices": sample_today_prices,
            "tomorrow_interval_prices": {},
            "source": "nordpool",
            "area": "SE3",
            "source_currency": "EUR",
            "target_currency": "SEK",
            "vat_rate": 0.25,
            "vat_included": True,
        }

        data = IntervalPriceData.from_cache_dict(cache_dict, mock_timezone_service)

        assert data.today_interval_prices == sample_today_prices
        assert data.source == "nordpool"
        assert data.area == "SE3"
        assert data.vat_rate == 0.25
        assert data._tz_service == mock_timezone_service

    def test_from_cache_dict_handles_old_format(self, sample_today_prices):
        """Test from_cache_dict handles old format with computed fields."""
        # Old format with computed fields (should be ignored)
        old_cache_dict = {
            "today_interval_prices": sample_today_prices,
            "source": "nordpool",
            "area": "SE3",
            # Old computed fields (should be ignored)
            "data_validity": {"interval_count": 96},
            "statistics": {"avg": 110.5},
            "has_tomorrow_prices": False,
            "current_price": 114.0,
        }

        data = IntervalPriceData.from_cache_dict(old_cache_dict)

        # Source data loaded
        assert data.today_interval_prices == sample_today_prices
        assert data.source == "nordpool"

        # Computed fields ignored (will be recomputed as properties)
        # The properties will compute fresh values

    def test_to_processed_result_includes_computed_fields(
        self, sample_today_prices, mock_timezone_service
    ):
        """Test to_processed_result includes all computed fields."""
        data = IntervalPriceData(
            today_interval_prices=sample_today_prices,
            source="nordpool",
            area="SE3",
            target_timezone="Europe/Stockholm",
            _tz_service=mock_timezone_service,
        )

        result = data.to_processed_result()

        # Source data present
        assert result["today_interval_prices"] == sample_today_prices
        assert result["source"] == "nordpool"

        # Computed fields also present (for backward compatibility)
        assert "data_validity" in result
        assert "statistics" in result
        assert "tomorrow_statistics" in result
        assert "has_tomorrow_prices" in result
        assert "current_price" in result
        assert "next_interval_price" in result

    def test_round_trip_serialization(
        self, sample_today_prices, sample_tomorrow_prices, mock_timezone_service
    ):
        """Test round-trip: data -> cache_dict -> data."""
        original = IntervalPriceData(
            today_interval_prices=sample_today_prices,
            tomorrow_interval_prices=sample_tomorrow_prices,
            source="nordpool",
            area="SE3",
            ecb_rate=11.5,
            vat_rate=0.25,
            _tz_service=mock_timezone_service,
        )

        # Convert to cache dict
        cache_dict = original.to_cache_dict()

        # Reconstruct from cache dict
        reconstructed = IntervalPriceData.from_cache_dict(
            cache_dict, mock_timezone_service
        )

        # Verify data matches
        assert reconstructed.today_interval_prices == original.today_interval_prices
        assert (
            reconstructed.tomorrow_interval_prices == original.tomorrow_interval_prices
        )
        assert reconstructed.source == original.source
        assert reconstructed.area == original.area
        assert reconstructed.ecb_rate == original.ecb_rate
        assert reconstructed.vat_rate == original.vat_rate


class TestBackwardCompatibility:
    """Test backward compatibility with old cache format."""

    def test_old_cache_format_with_computed_fields(self, sample_today_prices):
        """Test loading old cache that has computed fields."""
        old_cache = {
            "today_interval_prices": sample_today_prices,
            "tomorrow_interval_prices": {},
            "source": "nordpool",
            "area": "SE3",
            # Old format: computed fields in cache (should be ignored)
            "data_validity": {
                "interval_count": 96,
                "has_current_interval": True,
            },
            "statistics": {"avg": 110.5, "min": 100.0, "max": 123.0},
            "tomorrow_statistics": {},
            "has_tomorrow_prices": False,
        }

        data = IntervalPriceData.from_cache_dict(old_cache)

        # Source data loads correctly
        assert len(data.today_interval_prices) == 96
        assert data.source == "nordpool"

        # Properties compute fresh (ignore old cached values)
        stats = data.statistics
        assert stats.avg is not None  # Recomputed
        assert stats.min == 100.0
        assert stats.max == 123.0

    def test_mixed_cache_versions(self):
        """Test system works with mix of old and new cache entries."""
        # Some old format entries
        old_entry = {
            "today_interval_prices": {"14:00": 100.0},
            "source": "nordpool",
            "data_validity": {"interval_count": 1},  # Old
        }

        # Some new format entries
        new_entry = {
            "today_interval_prices": {"14:00": 100.0},
            "source": "nordpool",
            # No computed fields
        }

        # Both load correctly
        old_data = IntervalPriceData.from_cache_dict(old_entry)
        new_data = IntervalPriceData.from_cache_dict(new_entry)

        # Both compute properties correctly
        assert old_data.has_tomorrow_prices is False
        assert new_data.has_tomorrow_prices is False


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_data_model_properties(self):
        """Test all properties work on empty data model."""
        data = IntervalPriceData()

        assert data.has_tomorrow_prices is False
        assert data.statistics.avg is None
        assert data.tomorrow_statistics.avg is None
        assert data.current_price is None
        assert data.next_interval_price is None
        assert data.tomorrow_valid is False

    def test_partial_data(self):
        """Test with partial data (some intervals missing)."""
        partial_prices = {"14:00": 100.0, "14:15": 101.0, "14:30": 102.0}
        data = IntervalPriceData(today_interval_prices=partial_prices)

        stats = data.statistics
        assert stats.avg == 101.0
        assert stats.min == 100.0
        assert stats.max == 102.0

    def test_repr_string(self):
        """Test string representation."""
        data = IntervalPriceData(
            area="SE3",
            source="nordpool",
            today_interval_prices={"14:00": 100.0},
            tomorrow_interval_prices={},
        )

        repr_str = repr(data)

        assert "SE3" in repr_str
        assert "nordpool" in repr_str
        assert "today_intervals=1" in repr_str
        assert "tomorrow_intervals=0" in repr_str

    def test_migration_with_empty_tomorrow(self):
        """Test migration works even with empty tomorrow."""
        data = IntervalPriceData(
            today_interval_prices={"14:00": 100.0},
            tomorrow_interval_prices={},
        )

        data.migrate_to_new_day()

        # Should not crash, today becomes empty
        assert data.today_interval_prices == {}
        assert data.migrated_from_tomorrow is True

    def test_properties_with_invalid_tz_service(self, sample_today_prices):
        """Test properties handle invalid timezone service gracefully."""
        bad_tz_service = Mock()
        bad_tz_service.get_current_interval_key.side_effect = Exception("TZ error")

        data = IntervalPriceData(
            today_interval_prices=sample_today_prices, _tz_service=bad_tz_service
        )

        # Should not crash, return None
        assert data.current_price is None
        assert data.current_interval_key is None
