"""Regression: a price-affecting option change must invalidate the cache.

Cached prices are fully processed (VAT/multiplier/tariff/tax baked in). When a
price option changes, ``UnifiedPriceManager._price_config_changed`` must return
True so ``fetch_data`` reprocesses instead of serving stale prices — otherwise
the change only takes effect after an HA restart.
"""

from custom_components.ge_spot.coordinator.unified_price_manager import (
    UnifiedPriceManager,
)
from custom_components.ge_spot.coordinator.data_models import IntervalPriceData


class _DataProcessorStub:
    def __init__(
        self,
        vat_rate=0.25,
        include_vat=True,
        import_multiplier=1.0,
        additional_tariff=0.0,
        energy_tax=0.0,
    ):
        self.vat_rate = vat_rate
        self.include_vat = include_vat
        self.import_multiplier = import_multiplier
        self.additional_tariff = additional_tariff
        self.energy_tax = energy_tax


def _manager(dp):
    # Bypass __init__ (needs hass/session); the method only uses _data_processor.
    mgr = UnifiedPriceManager.__new__(UnifiedPriceManager)
    mgr._data_processor = dp
    return mgr


def _cached(**overrides):
    base = dict(
        applied_vat_rate=0.25,
        applied_include_vat=True,
        applied_import_multiplier=1.0,
        applied_additional_tariff=0.0,
        applied_energy_tax=0.0,
    )
    base.update(overrides)
    return IntervalPriceData(**base)


def test_unchanged_config_keeps_cache():
    assert _manager(_DataProcessorStub())._price_config_changed(_cached()) is False


def test_vat_change_invalidates():
    mgr = _manager(_DataProcessorStub(vat_rate=0.50))
    assert mgr._price_config_changed(_cached(applied_vat_rate=0.25)) is True


def test_multiplier_change_invalidates():
    mgr = _manager(_DataProcessorStub(import_multiplier=0.5))
    assert mgr._price_config_changed(_cached()) is True


def test_tariff_and_tax_changes_invalidate():
    assert (
        _manager(_DataProcessorStub(additional_tariff=0.1))._price_config_changed(
            _cached()
        )
        is True
    )
    assert (
        _manager(_DataProcessorStub(energy_tax=0.05))._price_config_changed(_cached())
        is True
    )


def test_include_vat_toggle_invalidates():
    mgr = _manager(_DataProcessorStub(include_vat=False, vat_rate=0.0))
    assert mgr._price_config_changed(_cached(applied_include_vat=True)) is True


def test_none_cache_is_not_a_change():
    assert _manager(_DataProcessorStub())._price_config_changed(None) is False


def test_legacy_cache_without_stamps_self_heals():
    # Cache stored before this fix has applied_* at defaults (0.0/False/1.0);
    # for a non-default config this must force exactly one reprocess.
    legacy = IntervalPriceData()
    assert (
        _manager(_DataProcessorStub(vat_rate=0.25))._price_config_changed(legacy)
        is True
    )
