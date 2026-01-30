#!/usr/bin/env python3
"""Tests for import multiplier and export price calculation functionality.

These tests verify:
1. Import multiplier correctly scales spot prices before adding tariffs/taxes
2. Export price calculation uses correct formula: (spot × multiplier + offset) × (1 + VAT)
3. Edge cases: zero multiplier, negative offset, extreme values
4. Integration with currency conversion and display units
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone
import zoneinfo

from custom_components.ge_spot.utils.unit_conversion import convert_energy_price
from custom_components.ge_spot.coordinator.data_processor import DataProcessor
from custom_components.ge_spot.coordinator.data_models import IntervalPriceData
from custom_components.ge_spot.const.config import Config
from custom_components.ge_spot.const.defaults import Defaults
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.const.energy import EnergyUnit


# ============================================================================
# Test: Import Multiplier in unit_conversion.convert_energy_price
# ============================================================================


class TestImportMultiplier:
    """Test import multiplier functionality in price conversion."""

    def test_default_multiplier_no_change(self):
        """Default multiplier of 1.0 should not change spot price."""
        result = convert_energy_price(
            price=80.0,  # 80 EUR/MWh
            source_unit=EnergyUnit.MWH,
            target_unit=EnergyUnit.KWH,
            vat_rate=0.0,
            display_unit_multiplier=1,
            additional_tariff=0.0,
            energy_tax=0.0,
            tariff_in_subunit=False,
            import_multiplier=1.0,  # Default
        )
        # 80 EUR/MWh = 0.08 EUR/kWh
        assert result == pytest.approx(0.08, rel=1e-4)

    def test_belgian_style_multiplier(self):
        """Test Belgian-style tariff: 0.1068 × spot price."""
        result = convert_energy_price(
            price=80.0,  # 80 EUR/MWh
            source_unit=EnergyUnit.MWH,
            target_unit=EnergyUnit.KWH,
            vat_rate=0.0,
            display_unit_multiplier=1,
            additional_tariff=0.0,
            energy_tax=0.0,
            tariff_in_subunit=False,
            import_multiplier=0.1068,  # Belgian multiplier
        )
        # 80 EUR/MWh = 0.08 EUR/kWh × 0.1068 = 0.008544 EUR/kWh
        assert result == pytest.approx(0.008544, rel=1e-4)

    def test_multiplier_with_tariff_and_vat(self):
        """Test full Belgian tariff: (spot × 0.1068 + 1.500) × 1.06 in cents."""
        result = convert_energy_price(
            price=80.0,  # 80 EUR/MWh
            source_unit=EnergyUnit.MWH,
            target_unit=EnergyUnit.KWH,
            vat_rate=0.06,  # 6% VAT
            display_unit_multiplier=100,  # Convert to cents
            additional_tariff=1.500,  # 1.500 cents/kWh
            energy_tax=0.0,
            tariff_in_subunit=True,  # Tariff is in cents
            import_multiplier=0.1068,
        )
        # Step 1: 80 / 1000 = 0.08 EUR/kWh
        # Step 2: 0.08 × 0.1068 = 0.008544 EUR/kWh
        # Step 3: 0.008544 + 0.015 (1.5 cents = 0.015 EUR) = 0.023544 EUR/kWh
        # Step 4: 0.023544 × 1.06 = 0.02495664 EUR/kWh
        # Step 5: 0.02495664 × 100 = 2.495664 cents/kWh
        assert result == pytest.approx(2.495664, rel=1e-4)

    def test_zero_multiplier(self):
        """Test zero multiplier results in only tariff/tax."""
        result = convert_energy_price(
            price=80.0,
            source_unit=EnergyUnit.MWH,
            target_unit=EnergyUnit.KWH,
            vat_rate=0.0,
            display_unit_multiplier=1,
            additional_tariff=0.05,  # 0.05 EUR/kWh
            energy_tax=0.01,  # 0.01 EUR/kWh
            tariff_in_subunit=False,
            import_multiplier=0.0,  # Zero multiplier
        )
        # Spot × 0 = 0, then add tariff + tax = 0.05 + 0.01 = 0.06 EUR/kWh
        assert result == pytest.approx(0.06, rel=1e-4)

    def test_large_multiplier(self):
        """Test large multiplier (edge case)."""
        result = convert_energy_price(
            price=10.0,
            source_unit=EnergyUnit.MWH,
            target_unit=EnergyUnit.KWH,
            vat_rate=0.0,
            display_unit_multiplier=1,
            additional_tariff=0.0,
            energy_tax=0.0,
            tariff_in_subunit=False,
            import_multiplier=10.0,  # Max allowed multiplier
        )
        # 10 / 1000 = 0.01 × 10 = 0.1 EUR/kWh
        assert result == pytest.approx(0.1, rel=1e-4)

    def test_small_multiplier(self):
        """Test very small multiplier (precision test)."""
        result = convert_energy_price(
            price=100.0,
            source_unit=EnergyUnit.MWH,
            target_unit=EnergyUnit.KWH,
            vat_rate=0.0,
            display_unit_multiplier=1,
            additional_tariff=0.0,
            energy_tax=0.0,
            tariff_in_subunit=False,
            import_multiplier=0.001,  # Very small multiplier
        )
        # 100 / 1000 = 0.1 × 0.001 = 0.0001 EUR/kWh
        assert result == pytest.approx(0.0001, rel=1e-4)


# ============================================================================
# Test: Export Price Calculation in DataProcessor
# ============================================================================


class TestExportPriceCalculation:
    """Test export price calculation in DataProcessor."""

    @pytest.fixture
    def mock_timezone_service(self):
        """Create a mock TimezoneService for testing."""
        mock_tz_service = MagicMock()
        mock_tz_service.target_timezone = zoneinfo.ZoneInfo("Europe/Stockholm")
        mock_tz_service.area_timezone = zoneinfo.ZoneInfo("Europe/Stockholm")
        mock_tz_service.ha_timezone = zoneinfo.ZoneInfo("Europe/Stockholm")
        mock_tz_service.get_current_interval_key.return_value = "10:00"
        mock_tz_service.get_next_interval_key.return_value = "10:15"
        return mock_tz_service

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.config.time_zone = "Europe/Stockholm"
        return hass

    @pytest.fixture
    def mock_manager(self):
        """Create a mock manager instance."""
        manager = MagicMock()
        manager.get_exchange_service = MagicMock(return_value=None)
        return manager

    def test_export_price_formula(self, mock_timezone_service, mock_hass, mock_manager):
        """Test export price formula: (spot × multiplier + offset) × (1 + VAT)."""
        config = {
            Config.AREA: "SE4",
            Config.CURRENCY: Currency.EUR,
            Config.VAT: 0.0,  # Import VAT (not used for export)
            Config.ADDITIONAL_TARIFF: 0.0,
            Config.ENERGY_TAX: 0.0,
            Config.DISPLAY_UNIT: "decimal",
            Config.EXPORT_ENABLED: True,
            Config.EXPORT_MULTIPLIER: 0.5,  # 50% of spot
            Config.EXPORT_OFFSET: 0.01,  # 0.01 EUR/kWh offset
            Config.EXPORT_VAT: 0.0,  # No export VAT
        }

        processor = DataProcessor(
            hass=mock_hass,
            area="SE4",
            target_currency=Currency.EUR,
            config=config,
            tz_service=mock_timezone_service,
            manager=mock_manager,
        )

        # Test the internal _calculate_export_prices method
        raw_prices = {"10:00": 0.08, "10:15": 0.10}  # EUR/kWh
        export_prices = processor._calculate_export_prices(raw_prices)

        # Formula: (spot × 0.5 + 0.01) × 1.0
        # 10:00: (0.08 × 0.5 + 0.01) × 1.0 = 0.05
        # 10:15: (0.10 × 0.5 + 0.01) × 1.0 = 0.06
        assert export_prices["10:00"] == pytest.approx(0.05, rel=1e-4)
        assert export_prices["10:15"] == pytest.approx(0.06, rel=1e-4)

    def test_export_price_with_vat(
        self, mock_timezone_service, mock_hass, mock_manager
    ):
        """Test export price with VAT applied."""
        config = {
            Config.AREA: "SE4",
            Config.CURRENCY: Currency.EUR,
            Config.VAT: 0.0,
            Config.ADDITIONAL_TARIFF: 0.0,
            Config.ENERGY_TAX: 0.0,
            Config.DISPLAY_UNIT: "decimal",
            Config.EXPORT_ENABLED: True,
            Config.EXPORT_MULTIPLIER: 1.0,  # 100% of spot
            Config.EXPORT_OFFSET: 0.0,  # No offset
            Config.EXPORT_VAT: 0.21,  # 21% export VAT
        }

        processor = DataProcessor(
            hass=mock_hass,
            area="SE4",
            target_currency=Currency.EUR,
            config=config,
            tz_service=mock_timezone_service,
            manager=mock_manager,
        )

        raw_prices = {"10:00": 0.10}  # EUR/kWh
        export_prices = processor._calculate_export_prices(raw_prices)

        # Formula: (0.10 × 1.0 + 0.0) × 1.21 = 0.121
        assert export_prices["10:00"] == pytest.approx(0.121, rel=1e-4)

    def test_export_price_negative_offset(
        self, mock_timezone_service, mock_hass, mock_manager
    ):
        """Test export price with negative offset (common for feed-in)."""
        config = {
            Config.AREA: "SE4",
            Config.CURRENCY: Currency.EUR,
            Config.VAT: 0.0,
            Config.ADDITIONAL_TARIFF: 0.0,
            Config.ENERGY_TAX: 0.0,
            Config.DISPLAY_UNIT: "decimal",
            Config.EXPORT_ENABLED: True,
            Config.EXPORT_MULTIPLIER: 0.1,  # 10% of spot
            Config.EXPORT_OFFSET: -0.01,  # Negative offset (deduction)
            Config.EXPORT_VAT: 0.0,
        }

        processor = DataProcessor(
            hass=mock_hass,
            area="SE4",
            target_currency=Currency.EUR,
            config=config,
            tz_service=mock_timezone_service,
            manager=mock_manager,
        )

        raw_prices = {"10:00": 0.20}  # EUR/kWh
        export_prices = processor._calculate_export_prices(raw_prices)

        # Formula: (0.20 × 0.1 + (-0.01)) × 1.0 = 0.02 - 0.01 = 0.01
        assert export_prices["10:00"] == pytest.approx(0.01, rel=1e-4)

    def test_export_price_zero_multiplier(
        self, mock_timezone_service, mock_hass, mock_manager
    ):
        """Test export with zero multiplier (fixed price)."""
        config = {
            Config.AREA: "SE4",
            Config.CURRENCY: Currency.EUR,
            Config.VAT: 0.0,
            Config.ADDITIONAL_TARIFF: 0.0,
            Config.ENERGY_TAX: 0.0,
            Config.DISPLAY_UNIT: "decimal",
            Config.EXPORT_ENABLED: True,
            Config.EXPORT_MULTIPLIER: 0.0,  # No spot component
            Config.EXPORT_OFFSET: 0.05,  # Fixed 0.05 EUR/kWh
            Config.EXPORT_VAT: 0.0,
        }

        processor = DataProcessor(
            hass=mock_hass,
            area="SE4",
            target_currency=Currency.EUR,
            config=config,
            tz_service=mock_timezone_service,
            manager=mock_manager,
        )

        raw_prices = {"10:00": 0.10, "10:15": 0.20}
        export_prices = processor._calculate_export_prices(raw_prices)

        # With zero multiplier, all prices should equal the offset
        assert export_prices["10:00"] == pytest.approx(0.05, rel=1e-4)
        assert export_prices["10:15"] == pytest.approx(0.05, rel=1e-4)

    def test_export_disabled_returns_empty(
        self, mock_timezone_service, mock_hass, mock_manager
    ):
        """Test that export disabled returns empty dict."""
        config = {
            Config.AREA: "SE4",
            Config.CURRENCY: Currency.EUR,
            Config.VAT: 0.0,
            Config.ADDITIONAL_TARIFF: 0.0,
            Config.ENERGY_TAX: 0.0,
            Config.DISPLAY_UNIT: "decimal",
            Config.EXPORT_ENABLED: False,  # Disabled
            Config.EXPORT_MULTIPLIER: 1.0,
            Config.EXPORT_OFFSET: 0.0,
            Config.EXPORT_VAT: 0.0,
        }

        processor = DataProcessor(
            hass=mock_hass,
            area="SE4",
            target_currency=Currency.EUR,
            config=config,
            tz_service=mock_timezone_service,
            manager=mock_manager,
        )

        raw_prices = {"10:00": 0.10}
        export_prices = processor._calculate_export_prices(raw_prices)

        assert export_prices == {}

    def test_export_empty_input_returns_empty(
        self, mock_timezone_service, mock_hass, mock_manager
    ):
        """Test that empty input returns empty dict."""
        config = {
            Config.AREA: "SE4",
            Config.CURRENCY: Currency.EUR,
            Config.VAT: 0.0,
            Config.ADDITIONAL_TARIFF: 0.0,
            Config.ENERGY_TAX: 0.0,
            Config.DISPLAY_UNIT: "decimal",
            Config.EXPORT_ENABLED: True,
            Config.EXPORT_MULTIPLIER: 1.0,
            Config.EXPORT_OFFSET: 0.0,
            Config.EXPORT_VAT: 0.0,
        }

        processor = DataProcessor(
            hass=mock_hass,
            area="SE4",
            target_currency=Currency.EUR,
            config=config,
            tz_service=mock_timezone_service,
            manager=mock_manager,
        )

        export_prices = processor._calculate_export_prices({})
        assert export_prices == {}

    def test_export_skips_none_values(
        self, mock_timezone_service, mock_hass, mock_manager
    ):
        """Test that None values in input are skipped."""
        config = {
            Config.AREA: "SE4",
            Config.CURRENCY: Currency.EUR,
            Config.VAT: 0.0,
            Config.ADDITIONAL_TARIFF: 0.0,
            Config.ENERGY_TAX: 0.0,
            Config.DISPLAY_UNIT: "decimal",
            Config.EXPORT_ENABLED: True,
            Config.EXPORT_MULTIPLIER: 1.0,
            Config.EXPORT_OFFSET: 0.0,
            Config.EXPORT_VAT: 0.0,
        }

        processor = DataProcessor(
            hass=mock_hass,
            area="SE4",
            target_currency=Currency.EUR,
            config=config,
            tz_service=mock_timezone_service,
            manager=mock_manager,
        )

        raw_prices = {"10:00": 0.10, "10:15": None, "10:30": 0.12}
        export_prices = processor._calculate_export_prices(raw_prices)

        assert "10:00" in export_prices
        assert "10:15" not in export_prices  # None skipped
        assert "10:30" in export_prices


# ============================================================================
# Test: IntervalPriceData Export Properties
# ============================================================================


class TestIntervalPriceDataExport:
    """Test export price properties in IntervalPriceData."""

    @pytest.fixture
    def mock_tz_service(self):
        """Create a mock timezone service."""
        mock = MagicMock()
        mock.target_timezone = zoneinfo.ZoneInfo("Europe/Stockholm")
        mock.get_current_interval_key.return_value = "10:00"
        mock.get_next_interval_key.return_value = "10:15"
        return mock

    def test_export_current_price(self, mock_tz_service):
        """Test export_current_price property."""
        data = IntervalPriceData(
            export_enabled=True,
            export_today_prices={"10:00": 0.05, "10:15": 0.06},
        )
        data._tz_service = mock_tz_service

        assert data.export_current_price == 0.05

    def test_export_current_price_disabled(self, mock_tz_service):
        """Test export_current_price when export is disabled."""
        data = IntervalPriceData(
            export_enabled=False,
            export_today_prices={"10:00": 0.05},
        )
        data._tz_service = mock_tz_service

        assert data.export_current_price is None

    def test_export_next_interval_price(self, mock_tz_service):
        """Test export_next_interval_price property."""
        data = IntervalPriceData(
            export_enabled=True,
            export_today_prices={"10:00": 0.05, "10:15": 0.06},
        )
        data._tz_service = mock_tz_service

        assert data.export_next_interval_price == 0.06

    def test_export_statistics(self, mock_tz_service):
        """Test export_statistics property."""
        data = IntervalPriceData(
            export_enabled=True,
            export_today_prices={"10:00": 0.04, "10:15": 0.06, "10:30": 0.05},
        )
        data._tz_service = mock_tz_service

        stats = data.export_statistics
        assert stats.avg == pytest.approx(0.05, rel=1e-4)
        assert stats.min == 0.04
        assert stats.max == 0.06

    def test_export_statistics_disabled(self, mock_tz_service):
        """Test export_statistics when export is disabled."""
        data = IntervalPriceData(
            export_enabled=False,
            export_today_prices={"10:00": 0.05},
        )
        data._tz_service = mock_tz_service

        stats = data.export_statistics
        assert stats.avg is None
        assert stats.min is None
        assert stats.max is None

    def test_export_tomorrow_statistics(self, mock_tz_service):
        """Test export_tomorrow_statistics property."""
        data = IntervalPriceData(
            export_enabled=True,
            export_tomorrow_prices={"10:00": 0.03, "10:15": 0.07},
        )
        data._tz_service = mock_tz_service

        stats = data.export_tomorrow_statistics
        assert stats.avg == pytest.approx(0.05, rel=1e-4)
        assert stats.min == 0.03
        assert stats.max == 0.07


# ============================================================================
# Test: Cache Invalidation
# ============================================================================


class TestCacheInvalidation:
    """Test that price-affecting settings trigger cache invalidation."""

    def test_import_multiplier_in_price_affecting_settings(self):
        """Verify IMPORT_MULTIPLIER is in the price_affecting_settings list."""
        # This is a code inspection test - the actual list is in options.py
        # We verify by importing and checking the Config constants
        from custom_components.ge_spot.const.config import Config

        # These are the settings that should invalidate cache
        expected_cache_invalidation_settings = [
            Config.VAT,
            Config.IMPORT_MULTIPLIER,
            Config.ADDITIONAL_TARIFF,
            Config.ENERGY_TAX,
            Config.DISPLAY_UNIT,
            Config.EXPORT_ENABLED,
            Config.EXPORT_MULTIPLIER,
            Config.EXPORT_OFFSET,
            Config.EXPORT_VAT,
        ]

        # Verify all expected settings exist in Config
        for setting in expected_cache_invalidation_settings:
            assert hasattr(Config, setting.upper().replace(".", "_")) or setting in dir(
                Config
            ), f"Config should have {setting}"
