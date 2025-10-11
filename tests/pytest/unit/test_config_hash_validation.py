"""Unit tests for configuration hash validation in DataProcessor.

Tests verify that:
1. Hash changes when any config parameter changes
2. Hash is deterministic (same config = same hash)
3. Processed data validation works correctly
4. Fast-path is used when hash matches
5. Reprocessing triggered when hash mismatches
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from custom_components.ge_spot.coordinator.data_processor import DataProcessor
from custom_components.ge_spot.const.display import DisplayUnit
from custom_components.ge_spot.const.currencies import Currency


class MockManager:
    """Mock manager for testing."""
    _exchange_service = None


class MockTzService:
    """Mock timezone service for testing."""
    target_timezone = 'Europe/Oslo'
    
    def get_current_interval_key(self):
        return "13:00"
    
    def get_next_interval_key(self):
        return "13:15"
    
    def get_today_range(self):
        """Return list of today's interval keys (HH:MM format)."""
        return [f"{h:02d}:{m:02d}" for h in range(24) for m in [0, 15, 30, 45]]


@pytest.fixture
def base_config():
    """Base configuration for testing."""
    return {
        'vat': 25.0,
        'include_vat': True,
        'display_unit': DisplayUnit.CENTS,
        'precision': 2
    }


@pytest.fixture
def processor(base_config):
    """Create a DataProcessor instance for testing."""
    return DataProcessor(
        hass=None,
        area='SE3',
        target_currency=Currency.SEK,
        config=base_config,
        tz_service=MockTzService(),
        manager=MockManager()
    )


class TestConfigHashGeneration:
    """Test hash generation logic."""
    
    def test_hash_is_deterministic(self, processor):
        """Hash should be identical for same configuration."""
        hash1 = processor._calculate_processing_config_hash()
        hash2 = processor._calculate_processing_config_hash()
        assert hash1 == hash2, "Hash should be deterministic"
    
    def test_hash_length(self, processor):
        """Hash should be exactly 12 characters."""
        hash_value = processor._calculate_processing_config_hash()
        assert len(hash_value) == 12, f"Hash should be 12 chars, got {len(hash_value)}"
    
    def test_hash_is_hexadecimal(self, processor):
        """Hash should only contain hex characters."""
        hash_value = processor._calculate_processing_config_hash()
        try:
            int(hash_value, 16)
        except ValueError:
            pytest.fail(f"Hash '{hash_value}' is not valid hexadecimal")
    
    def test_hash_changes_with_currency(self, base_config):
        """Hash should change when currency changes."""
        processor_sek = DataProcessor(
            hass=None, area='SE3', target_currency=Currency.SEK,
            config=base_config, tz_service=MockTzService(), manager=MockManager()
        )
        processor_eur = DataProcessor(
            hass=None, area='SE3', target_currency=Currency.EUR,
            config=base_config, tz_service=MockTzService(), manager=MockManager()
        )
        
        hash_sek = processor_sek._calculate_processing_config_hash()
        hash_eur = processor_eur._calculate_processing_config_hash()
        
        assert hash_sek != hash_eur, "Hash should differ for different currencies"
    
    def test_hash_changes_with_vat_rate(self, base_config):
        """Hash should change when VAT rate changes."""
        config_25 = {**base_config, 'vat': 25.0}
        config_0 = {**base_config, 'vat': 0.0}
        
        processor_25 = DataProcessor(
            hass=None, area='SE3', target_currency=Currency.SEK,
            config=config_25, tz_service=MockTzService(), manager=MockManager()
        )
        processor_0 = DataProcessor(
            hass=None, area='SE3', target_currency=Currency.SEK,
            config=config_0, tz_service=MockTzService(), manager=MockManager()
        )
        
        hash_25 = processor_25._calculate_processing_config_hash()
        hash_0 = processor_0._calculate_processing_config_hash()
        
        assert hash_25 != hash_0, "Hash should differ for different VAT rates"
    
    def test_hash_changes_with_include_vat(self, base_config):
        """Hash should change when include_vat flag changes."""
        config_with_vat = {**base_config, 'include_vat': True}
        config_without_vat = {**base_config, 'include_vat': False}
        
        processor_with = DataProcessor(
            hass=None, area='SE3', target_currency=Currency.SEK,
            config=config_with_vat, tz_service=MockTzService(), manager=MockManager()
        )
        processor_without = DataProcessor(
            hass=None, area='SE3', target_currency=Currency.SEK,
            config=config_without_vat, tz_service=MockTzService(), manager=MockManager()
        )
        
        hash_with = processor_with._calculate_processing_config_hash()
        hash_without = processor_without._calculate_processing_config_hash()
        
        assert hash_with != hash_without, "Hash should differ for different include_vat settings"
    
    def test_hash_changes_with_display_unit(self, base_config):
        """Hash should change when display unit changes."""
        config_cents = {**base_config, 'display_unit': DisplayUnit.CENTS}
        config_decimal = {**base_config, 'display_unit': DisplayUnit.DECIMAL}
        
        processor_cents = DataProcessor(
            hass=None, area='SE3', target_currency=Currency.SEK,
            config=config_cents, tz_service=MockTzService(), manager=MockManager()
        )
        processor_decimal = DataProcessor(
            hass=None, area='SE3', target_currency=Currency.SEK,
            config=config_decimal, tz_service=MockTzService(), manager=MockManager()
        )
        
        hash_cents = processor_cents._calculate_processing_config_hash()
        hash_decimal = processor_decimal._calculate_processing_config_hash()
        
        assert hash_cents != hash_decimal, "Hash should differ for different display units"
    
    def test_hash_changes_with_precision(self, base_config):
        """Hash should change when precision changes."""
        config_2 = {**base_config, 'precision': 2}
        config_3 = {**base_config, 'precision': 3}
        
        processor_2 = DataProcessor(
            hass=None, area='SE3', target_currency=Currency.SEK,
            config=config_2, tz_service=MockTzService(), manager=MockManager()
        )
        processor_3 = DataProcessor(
            hass=None, area='SE3', target_currency=Currency.SEK,
            config=config_3, tz_service=MockTzService(), manager=MockManager()
        )
        
        hash_2 = processor_2._calculate_processing_config_hash()
        hash_3 = processor_3._calculate_processing_config_hash()
        
        assert hash_2 != hash_3, "Hash should differ for different precision settings"
    
    def test_hash_changes_with_timezone(self, base_config):
        """Hash should change when target timezone changes."""
        # Create two timezone services with different timezones
        tz_service_stockholm = MockTzService()
        tz_service_stockholm.target_timezone = 'Europe/Stockholm'
        
        tz_service_oslo = MockTzService()
        tz_service_oslo.target_timezone = 'Europe/Oslo'
        
        processor_stockholm = DataProcessor(
            hass=None, area='SE3', target_currency=Currency.SEK,
            config=base_config, tz_service=tz_service_stockholm,
            manager=MockManager()
        )
        processor_oslo = DataProcessor(
            hass=None, area='SE3', target_currency=Currency.SEK,
            config=base_config, tz_service=tz_service_oslo,
            manager=MockManager()
        )
        
        hash_stockholm = processor_stockholm._calculate_processing_config_hash()
        hash_oslo = processor_oslo._calculate_processing_config_hash()
        
        assert hash_stockholm != hash_oslo, "Hash should differ for different target timezones"


class TestProcessedDataValidation:
    """Test _is_processed_data_valid() method."""
    
    def test_valid_processed_data(self, processor):
        """Should return True for valid processed data with matching hash."""
        current_hash = processor._calculate_processing_config_hash()
        
        # Generate a full day of 15-minute intervals (96 intervals)
        today_intervals = processor._tz_service.get_today_range()
        
        # Create data with most of today's intervals (>80%)
        interval_data = {key: 100.0 + hash(key) % 100 for key in today_intervals[:80]}
        
        valid_data = {
            "interval_prices": interval_data,
            "statistics": {"min": 100, "max": 200},
            "target_timezone": "Europe/Oslo",
            "processing_config_hash": current_hash,
            # NEW: Required fields for validation
            "raw_interval_prices_original": {"2025-10-11T00:00:00+02:00": 100.0},
            "source_timezone": "Europe/Oslo",
            "source_currency": "NOK",
        }
        
        assert processor._is_processed_data_valid(valid_data) is True
    
    def test_invalid_hash_mismatch(self, processor):
        """Should return False when hash doesn't match (config changed)."""
        stale_data = {
            "interval_prices": {"00:00": 100.0, "13:00": 150.0},
            "statistics": {"min": 100, "max": 200},
            "target_timezone": "Europe/Oslo",
            "processing_config_hash": "stale_hash12",  # Wrong hash
        }
        
        assert processor._is_processed_data_valid(stale_data) is False
    
    def test_invalid_missing_interval_prices(self, processor):
        """Should return False when interval_prices is missing."""
        invalid_data = {
            "statistics": {"min": 100, "max": 200},
            "target_timezone": "Europe/Oslo",
            "processing_config_hash": processor._calculate_processing_config_hash(),
        }
        
        assert processor._is_processed_data_valid(invalid_data) is False
    
    def test_invalid_missing_statistics(self, processor):
        """Should return False when statistics is missing."""
        invalid_data = {
            "interval_prices": {"00:00": 100.0},
            "target_timezone": "Europe/Oslo",
            "processing_config_hash": processor._calculate_processing_config_hash(),
        }
        
        assert processor._is_processed_data_valid(invalid_data) is False
    
    def test_invalid_missing_target_timezone(self, processor):
        """Should return False when target_timezone is missing."""
        invalid_data = {
            "interval_prices": {"00:00": 100.0},
            "statistics": {"min": 100, "max": 200},
            "processing_config_hash": processor._calculate_processing_config_hash(),
        }
        
        assert processor._is_processed_data_valid(invalid_data) is False
    
    def test_invalid_raw_format_iso_timestamps(self, processor):
        """Should return False for raw data with ISO timestamps."""
        raw_data = {
            "interval_prices": {"2025-01-01T00:00:00+01:00": 100.0},  # ISO format
            "statistics": {"min": 100, "max": 200},
            "target_timezone": "Europe/Oslo",
            "processing_config_hash": processor._calculate_processing_config_hash(),
        }
        
        assert processor._is_processed_data_valid(raw_data) is False
    
    def test_invalid_empty_interval_prices(self, processor):
        """Should return False when interval_prices is empty."""
        invalid_data = {
            "interval_prices": {},  # Empty
            "statistics": {"min": 100, "max": 200},
            "target_timezone": "Europe/Oslo",
            "processing_config_hash": processor._calculate_processing_config_hash(),
        }
        
        assert processor._is_processed_data_valid(invalid_data) is False
    
    def test_invalid_missing_hash(self, processor):
        """Should return False when processing_config_hash is missing."""
        invalid_data = {
            "interval_prices": {"00:00": 100.0},
            "statistics": {"min": 100, "max": 200},
            "target_timezone": "Europe/Oslo",
            # Missing processing_config_hash
        }
        
        assert processor._is_processed_data_valid(invalid_data) is False
    
    def test_invalid_missing_raw_data(self, processor):
        """Should return False when raw_interval_prices_original is missing."""
        current_hash = processor._calculate_processing_config_hash()
        
        today_intervals = processor._tz_service.get_today_range()
        interval_data = {key: 100.0 for key in today_intervals[:80]}
        
        invalid_data = {
            "interval_prices": interval_data,
            "statistics": {"min": 100, "max": 200},
            "target_timezone": "Europe/Oslo",
            "processing_config_hash": current_hash,
            "source_timezone": "Europe/Oslo",
            "source_currency": "NOK",
            # Missing raw_interval_prices_original
        }
        
        assert processor._is_processed_data_valid(invalid_data) is False
    
    def test_invalid_missing_source_timezone(self, processor):
        """Should return False when source_timezone is missing."""
        current_hash = processor._calculate_processing_config_hash()
        
        today_intervals = processor._tz_service.get_today_range()
        interval_data = {key: 100.0 for key in today_intervals[:80]}
        
        invalid_data = {
            "interval_prices": interval_data,
            "statistics": {"min": 100, "max": 200},
            "target_timezone": "Europe/Oslo",
            "processing_config_hash": current_hash,
            "raw_interval_prices_original": {"2025-10-11T00:00:00+02:00": 100.0},
            "source_currency": "NOK",
            # Missing source_timezone
        }
        
        assert processor._is_processed_data_valid(invalid_data) is False
    
    def test_invalid_missing_source_currency(self, processor):
        """Should return False when source_currency is missing."""
        current_hash = processor._calculate_processing_config_hash()
        
        today_intervals = processor._tz_service.get_today_range()
        interval_data = {key: 100.0 for key in today_intervals[:80]}
        
        invalid_data = {
            "interval_prices": interval_data,
            "statistics": {"min": 100, "max": 200},
            "target_timezone": "Europe/Oslo",
            "processing_config_hash": current_hash,
            "raw_interval_prices_original": {"2025-10-11T00:00:00+02:00": 100.0},
            "source_timezone": "Europe/Oslo",
            # Missing source_currency
        }
        
        assert processor._is_processed_data_valid(invalid_data) is False
    
    def test_invalid_stale_data_from_yesterday(self, processor):
        """Should return False when cached data is from yesterday."""
        current_hash = processor._calculate_processing_config_hash()
        
        # Create data with YESTERDAY's intervals (different times - won't match today)
        yesterday_intervals = [f"{h:02d}:{m:02d}" for h in range(12) for m in [0, 30]]  # Different pattern
        interval_data = {key: 100.0 for key in yesterday_intervals}
        
        stale_data = {
            "interval_prices": interval_data,
            "statistics": {"min": 100, "max": 200},
            "target_timezone": "Europe/Oslo",
            "processing_config_hash": current_hash,
            "raw_interval_prices_original": {"2025-10-10T00:00:00+02:00": 100.0},
            "source_timezone": "Europe/Oslo",
            "source_currency": "NOK",
        }
        
        assert processor._is_processed_data_valid(stale_data) is False
    
    def test_invalid_incomplete_today_data(self, processor):
        """Should return False when today's data is < 80% complete."""
        current_hash = processor._calculate_processing_config_hash()
        
        # Get today's expected intervals
        today_intervals = processor._tz_service.get_today_range()
        
        # Only provide 50% of today's intervals (less than 80% threshold)
        interval_data = {key: 100.0 for key in today_intervals[:48]}  # 50 out of 96
        
        incomplete_data = {
            "interval_prices": interval_data,
            "statistics": {"min": 100, "max": 200},
            "target_timezone": "Europe/Oslo",
            "processing_config_hash": current_hash,
            "raw_interval_prices_original": {"2025-10-11T00:00:00+02:00": 100.0},
            "source_timezone": "Europe/Oslo",
            "source_currency": "NOK",
        }
        
        assert processor._is_processed_data_valid(incomplete_data) is False


class TestFastPathUpdate:
    """Test _update_current_next_only() fast-path method."""
    
    @pytest.mark.asyncio
    async def test_updates_current_and_next_prices(self, processor):
        """Should update current and next prices from cached data."""
        cached_data = {
            "interval_prices": {
                "00:00": 100.0,
                "13:00": 150.0,  # Current (13:00)
                "13:15": 155.0,  # Next (13:15)
                "14:00": 160.0,
            },
            "tomorrow_interval_prices": {},
            "statistics": {"min": 100, "max": 200},
            "target_timezone": "Europe/Oslo",
        }
        
        result = await processor._update_current_next_only(cached_data)
        
        assert result["current_price"] == 150.0
        assert result["next_interval_price"] == 155.0
    
    @pytest.mark.asyncio
    async def test_updates_interval_keys(self, processor):
        """Should update current and next interval keys."""
        cached_data = {
            "interval_prices": {"00:00": 100.0, "13:00": 150.0, "13:15": 155.0},
            "tomorrow_interval_prices": {},
        }
        
        result = await processor._update_current_next_only(cached_data)
        
        assert result["current_interval_key"] == "13:00"
        assert result["next_interval_key"] == "13:15"
    
    @pytest.mark.asyncio
    async def test_sets_using_cached_data_flag(self, processor):
        """Should set using_cached_data flag to True."""
        cached_data = {
            "interval_prices": {"00:00": 100.0, "13:00": 150.0, "13:15": 155.0},
            "tomorrow_interval_prices": {},
        }
        
        result = await processor._update_current_next_only(cached_data)
        
        assert result["using_cached_data"] is True
    
    @pytest.mark.asyncio
    async def test_updates_last_update_timestamp(self, processor):
        """Should update last_update timestamp."""
        cached_data = {
            "interval_prices": {"00:00": 100.0, "13:00": 150.0, "13:15": 155.0},
            "tomorrow_interval_prices": {},
        }
        
        result = await processor._update_current_next_only(cached_data)
        
        assert "last_update" in result
        assert result["last_update"] is not None
    
    @pytest.mark.asyncio
    async def test_fallback_to_tomorrow_prices(self, processor):
        """Should fallback to tomorrow_interval_prices for late evening."""
        cached_data = {
            "interval_prices": {"00:00": 100.0, "12:00": 150.0},  # No 13:00
            "tomorrow_interval_prices": {
                "13:00": 200.0,  # Current in tomorrow
                "13:15": 205.0,  # Next in tomorrow
            },
        }
        
        result = await processor._update_current_next_only(cached_data)
        
        assert result["current_price"] == 200.0
        assert result["next_interval_price"] == 205.0


class TestHashCollisionProbability:
    """Test hash collision probability."""
    
    def test_hash_space_is_large_enough(self):
        """12-character hex hash provides sufficient collision resistance."""
        # 16^12 = 281,474,976,710,656 (281 trillion) possible hashes
        hash_space = 16 ** 12
        
        # With typical config space:
        # - 10 currencies
        # - 10 VAT rates (0%, 5%, 10%, ..., 25%)
        # - 2 include_vat options
        # - 2 display units
        # - 3 precision values (1, 2, 3)
        # = 10 × 10 × 2 × 2 × 3 = 1,200 possible configs
        
        config_space = 1200
        
        # Collision probability with 12-char hash is negligible
        # Even with 1 million configs, probability < 0.000001%
        collision_probability = (config_space * config_space) / hash_space
        
        assert hash_space > 1e14, "Hash space should be > 100 trillion"
        assert collision_probability < 1e-8, "Collision probability should be < 0.00000001"
    
    def test_different_configs_produce_different_hashes(self, base_config):
        """Generate multiple configs and verify no collisions."""
        hashes = set()
        configs_tested = 0
        
        # Test various currency combinations
        for currency in [Currency.SEK, Currency.EUR, Currency.DKK, Currency.NOK]:
            for vat in [0.0, 12.5, 25.0]:
                for include_vat in [True, False]:
                    for display_unit in [DisplayUnit.CENTS, DisplayUnit.DECIMAL]:
                        config = {
                            **base_config,
                            'vat': vat,
                            'include_vat': include_vat,
                            'display_unit': display_unit,
                        }
                        processor = DataProcessor(
                            hass=None, area='SE3', target_currency=currency,
                            config=config, tz_service=MockTzService(), manager=MockManager()
                        )
                        hash_value = processor._calculate_processing_config_hash()
                        
                        assert hash_value not in hashes, f"Hash collision detected for config: {config}"
                        hashes.add(hash_value)
                        configs_tested += 1
        
        # We should have tested multiple configs without collisions
        assert configs_tested > 30, "Should test at least 30 config combinations"
        assert len(hashes) == configs_tested, "All hashes should be unique"
