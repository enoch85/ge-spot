"""Unit tests for the ConsumptionWeightedAverageSensor HA adapter.

Covers the opt-in setup gating and options flow, meter handling (dropouts, unit
conversion), restore/fingerprint behaviour, the small attribute payload (no
heavy price arrays), and availability — the HA-coupled bits that the pure
accumulator tests don't reach.
"""

from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, UnitOfEnergy
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ge_spot.const import DOMAIN
from custom_components.ge_spot.const.attributes import Attributes
from custom_components.ge_spot.const.config import Config
from custom_components.ge_spot.sensor import electricity
from custom_components.ge_spot.sensor.price import ConsumptionWeightedAverageSensor

METER = "sensor.house_energy"


def _make_sensor(
    period="daily",
    energy=METER,
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
        "average_price_paid_today" if period == "daily" else "average_price_paid_month"
    )
    return ConsumptionWeightedAverageSensor(
        coordinator, config_data, sensor_type, "Average Price Paid", energy, period
    )


async def _add_to_hass(sensor, hass):
    """Run the real async_added_to_hass: meter tracking and baseline seed."""
    sensor.hass = hass
    sensor.entity_id = "sensor.gespot_average_price_paid_today_se3"
    sensor._tz_service = None  # default timezone for the period keys
    sensor.coordinator.data = Mock(current_price=1.5)
    sensor.async_write_ha_state = Mock()
    sensor.async_get_last_extra_data = AsyncMock(return_value=None)
    await sensor.async_added_to_hass()


# --- Opt-in setup gating ---------------------------------------------------


@pytest.mark.asyncio
async def test_no_weighted_sensors_without_energy_entity(hass):
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
    coordinator = Mock()
    coordinator.area = "SE3"
    coordinator.currency = "SEK"
    coordinator.data = None
    coordinator._tz_service = Mock()

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={Config.AREA: "SE3"},
        options={Config.ENERGY_ENTITY: METER},
        entry_id="e2",
    )
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    captured = []
    await electricity.async_setup_entry(hass, entry, lambda es: captured.extend(es))

    weighted = [e for e in captured if isinstance(e, ConsumptionWeightedAverageSensor)]
    assert len(weighted) == 2
    assert {w._period for w in weighted} == {"daily", "monthly"}
    assert all(w._energy_entity_id == METER for w in weighted)


@pytest.mark.asyncio
async def test_energy_entity_can_be_cleared_in_options(hass):
    """The saved meter is only suggested, so clearing it turns the feature off."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={Config.AREA: "SE3"},
        options={Config.ENERGY_ENTITY: METER},
        entry_id="e3",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    marker = next(k for k in result["data_schema"].schema if k == Config.ENERGY_ENTITY)
    assert marker.description == {"suggested_value": METER}

    # The frontend omits cleared fields on submit.
    await hass.config_entries.options.async_configure(result["flow_id"], user_input={})
    assert Config.ENERGY_ENTITY not in entry.options


# --- Meter handling --------------------------------------------------------


@pytest.mark.asyncio
async def test_meter_dropout_gap_is_not_priced(hass):
    """A dropout re-baselines instead of pricing the gap at the current price."""
    hass.states.async_set(METER, "6.0")
    s = _make_sensor()
    await _add_to_hass(s, hass)

    for value in ("unavailable", "8.0", "9.0"):
        hass.states.async_set(METER, value)
        await hass.async_block_till_done()

    assert s._acc.energy_acc == pytest.approx(1.0)  # only 8 -> 9, not 6 -> 8
    assert s._acc.cost_acc == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_wh_meter_is_converted_to_kwh(hass):
    wh = {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.WATT_HOUR}
    hass.states.async_set(METER, "1000", wh)
    s = _make_sensor()
    await _add_to_hass(s, hass)

    hass.states.async_set(METER, "3000", wh)
    await hass.async_block_till_done()

    attrs = s.extra_state_attributes
    assert attrs[Attributes.CONSUMED_ENERGY] == pytest.approx(2.0)
    assert attrs[Attributes.ACCUMULATED_COST] == pytest.approx(3.0)
    assert s.native_value == pytest.approx(1.5)


# --- Restore / fingerprint -------------------------------------------------


def test_restore_roundtrip_when_fingerprint_matches():
    s = _make_sensor()
    s._acc.cost_acc = 10.0
    s._acc.energy_acc = 5.0
    s._acc.simple_sum = 12.0
    s._acc.simple_count = 6
    s._acc.period_start_key = "2026-06-30"
    s._acc.last_energy = 123.0
    data = s.extra_restore_state_data.as_dict()

    # A VAT change keeps the numbers: cost booked before it is what was paid.
    restored = _make_sensor(vat=0.12)
    restored._restore(data)
    assert restored._acc.cost_acc == pytest.approx(10.0)
    assert restored._acc.energy_acc == pytest.approx(5.0)
    assert restored._acc.simple_count == 6
    assert restored._acc.last_energy is None  # re-seeded from the meter instead
    assert restored.native_value == pytest.approx(round(10.0 / 5.0, 3))


def test_restore_discarded_when_fingerprint_differs():
    s = _make_sensor(display_unit="decimal")
    s._acc.cost_acc = 10.0
    s._acc.energy_acc = 5.0
    data = s.extra_restore_state_data.as_dict()

    # Display unit changed -> accumulated cost basis changed -> start fresh.
    other = _make_sensor(display_unit="cents")
    other._restore(data)
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
    assert attrs[Attributes.ENERGY_SOURCE] == METER
    assert attrs[Attributes.PERIOD] == "daily"
    # The heavy base-class arrays must never appear on this sensor.
    assert "today_interval_prices" not in attrs
    assert "tomorrow_interval_prices" not in attrs


def test_available_stays_true_even_without_coordinator_data():
    s = _make_sensor()
    s.coordinator.last_update_success = False
    s.coordinator.data = None
    assert s.available is True
