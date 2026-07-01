"""Unit tests for the ConsumptionWeightedAverageSensor HA adapter.

Covers the opt-in setup gating, restore/fingerprint behaviour, the small
attribute payload (no heavy price arrays), and availability — the HA-coupled
bits that the pure accumulator tests don't reach.
"""

from unittest.mock import Mock

import pytest

from custom_components.ge_spot.const import DOMAIN
from custom_components.ge_spot.const.attributes import Attributes
from custom_components.ge_spot.const.config import Config
from custom_components.ge_spot.sensor import electricity
from custom_components.ge_spot.sensor.price import ConsumptionWeightedAverageSensor


def _make_sensor(
    period="daily",
    energy="sensor.house_energy",
    currency="SEK",
    display_unit="decimal",
    vat=0.25,
):
    coordinator = Mock()
    coordinator.data = None
    coordinator._tz_service = Mock()
    config_data = {
        Attributes.AREA: "SE3",
        Attributes.VAT: vat,
        Config.PRECISION: 3,
        Config.DISPLAY_UNIT: display_unit,
        Attributes.CURRENCY: currency,
        "entry_id": "x",
    }
    sensor_type = (
        "consumption_weighted_average_today"
        if period == "daily"
        else "consumption_weighted_average_month"
    )
    return ConsumptionWeightedAverageSensor(
        coordinator, config_data, sensor_type, "Your Average Price", energy, period
    )


# --- Opt-in setup gating ---------------------------------------------------


@pytest.mark.asyncio
async def test_no_weighted_sensors_without_energy_entity(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    coordinator = Mock()
    coordinator.area = "SE3"
    coordinator.currency = "SEK"
    coordinator.data = None
    coordinator._tz_service = Mock()

    entry = MockConfigEntry(
        domain=DOMAIN, data={Config.AREA: "SE3"}, options={}, entry_id="e1"
    )
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    captured = []
    await electricity.async_setup_entry(hass, entry, lambda es: captured.extend(es))
    assert not any(isinstance(e, ConsumptionWeightedAverageSensor) for e in captured)


@pytest.mark.asyncio
async def test_two_weighted_sensors_when_energy_entity_set(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    coordinator = Mock()
    coordinator.area = "SE3"
    coordinator.currency = "SEK"
    coordinator.data = None
    coordinator._tz_service = Mock()

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={Config.AREA: "SE3"},
        options={Config.ENERGY_ENTITY: "sensor.house_energy"},
        entry_id="e2",
    )
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    captured = []
    await electricity.async_setup_entry(hass, entry, lambda es: captured.extend(es))

    weighted = [e for e in captured if isinstance(e, ConsumptionWeightedAverageSensor)]
    assert len(weighted) == 2
    assert {w._period for w in weighted} == {"daily", "monthly"}
    assert all(w._energy_entity_id == "sensor.house_energy" for w in weighted)


# --- Restore / fingerprint -------------------------------------------------


def test_restore_roundtrip_when_fingerprint_matches():
    s = _make_sensor()
    s._acc.cost_acc = 10.0
    s._acc.energy_acc = 5.0
    s._acc.simple_sum = 12.0
    s._acc.simple_count = 6
    s._acc.period_start_key = "2026-06-30"
    data = s.extra_restore_state_data.as_dict()

    restored = _make_sensor()
    restored._restore_from(data)
    assert restored._acc.cost_acc == pytest.approx(10.0)
    assert restored._acc.energy_acc == pytest.approx(5.0)
    assert restored._acc.simple_count == 6
    assert restored.native_value == pytest.approx(round(10.0 / 5.0, 3))


def test_restore_discarded_when_fingerprint_differs():
    s = _make_sensor(display_unit="decimal")
    s._acc.cost_acc = 10.0
    s._acc.energy_acc = 5.0
    data = s.extra_restore_state_data.as_dict()

    # Display unit changed -> accumulated cost basis changed -> start fresh.
    other = _make_sensor(display_unit="cents")
    other._restore_from(data)
    assert other._acc.cost_acc == 0.0
    assert other._acc.energy_acc == 0.0
    assert other.native_value is None


# --- State / attributes ----------------------------------------------------


def test_native_value_none_before_any_consumption():
    assert _make_sensor().native_value is None


def test_attributes_report_beating_and_exclude_price_arrays():
    s = _make_sensor()
    s._acc.cost_acc = 7.113
    s._acc.energy_acc = 10.0  # weighted ~0.7113
    s._acc.simple_sum = 10.417
    s._acc.simple_count = 10  # simple ~1.0417

    attrs = s.extra_state_attributes
    assert attrs[Attributes.BEATING_AVERAGE] is True
    assert attrs[Attributes.SAVINGS_VS_AVERAGE] > 0
    assert attrs[Attributes.ENERGY_SOURCE] == "sensor.house_energy"
    assert attrs[Attributes.PERIOD] == "daily"
    # The heavy base-class arrays must never appear on this sensor.
    assert "today_interval_prices" not in attrs
    assert "tomorrow_interval_prices" not in attrs


def test_available_stays_true_even_without_coordinator_data():
    s = _make_sensor()
    s.coordinator.last_update_success = False
    s.coordinator.data = None
    assert s.available is True
