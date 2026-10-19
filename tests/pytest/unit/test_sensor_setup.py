# tests/integration/test_sensor_setup.py
"""Tests for the GE Spot sensor platform setup."""

import asyncio

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.const import Platform

from custom_components.ge_spot.const import DOMAIN, Config
from custom_components.ge_spot.coordinator import UnifiedPriceCoordinator
from datetime import timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from custom_components.ge_spot.sensor.base import BaseElectricityPriceSensor
from custom_components.ge_spot.coordinator.data_models import IntervalPriceData
from custom_components.ge_spot.timezone.service import TimezoneService
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from freezegun import freeze_time
from homeassistant.util import dt as dt_util

# Define mock data that the coordinator would typically provide
MOCK_COORDINATOR_DATA = {
    "area": "SE4",
    "currency": "SEK",
    "current_price": 123.45,
    "next_interval_price": 130.00,
    "today_stats": {
        "average": 110.5,
        "min": 90.0,
        "max": 150.0,
        "min_timestamp": "2025-04-25T03:00:00+00:00",
        "max_timestamp": "2025-04-25T18:00:00+00:00",
        "current": 123.45,  # Ensure current is present for difference/percent sensors
        "peak": {"average": 140.0},
        "off_peak": {"average": 100.0},
    },
    "hour_stats": {  # For OffPeakPeakSensor attributes
        "peak_avg": 140.0,
        "off_peak_avg": 100.0,
    },
    "tomorrow_valid": False,
    "source": "mock_source",
    "timezone": "Europe/Stockholm",
    "vat_included": False,
    "has_data": True,
    "error": None,
    # Add other keys expected by sensors if necessary
}


def test_coordinator_sensors_do_not_poll_individually():
    sensor = BaseElectricityPriceSensor(
        MagicMock(),
        {"area": "SE4", "currency": "SEK"},
        "current_price",
        "Current Price",
    )
    assert not sensor.should_poll


async def test_shared_coordinator_updates_prices_after_interval_change(hass):
    config = {Config.AREA: "SE4", Config.CURRENCY: "EUR"}
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)
    data = IntervalPriceData(
        today_interval_prices={"12:00": 0.1301, "12:15": 0.12525},
        _tz_service=TimezoneService(hass, "SE4", config),
    )
    values = []
    with freeze_time("2026-10-13T10:14:59Z") as clock, patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.UnifiedPriceManager"
    ) as manager_class, patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
    ), patch(
        "custom_components.ge_spot.get_exchange_service",
        new=AsyncMock(return_value=MagicMock()),
    ):
        manager = manager_class.return_value
        manager.fetch_data = AsyncMock(return_value=data)
        manager.async_close = AsyncMock()
        manager._health_check_scheduled = True
        manager._tz_service = data._tz_service
        assert await hass.config_entries.async_setup(entry.entry_id)
        coordinator = hass.data[DOMAIN][entry.entry_id]
        remove_listener = coordinator.async_add_listener(
            lambda: values.append(coordinator.data.current_price)
        )
        try:
            assert coordinator.data.current_price == 0.1301
            clock.tick(timedelta(seconds=31))
            async_fire_time_changed(hass, dt_util.now())
            await hass.async_block_till_done()
            # The interval start and the scheduled refresh both notify.
            assert manager.fetch_data.await_count == 2
            assert values and set(values) == {0.12525}
        finally:
            remove_listener()
            await coordinator.async_shutdown()
            await coordinator.async_close()


async def test_interval_start_updates_listeners_while_refresh_waits(hass):
    """A slow provider must not keep the previous interval's price on sensors."""
    config = {Config.AREA: "SE4", Config.CURRENCY: "EUR"}
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)
    data = IntervalPriceData(
        today_interval_prices={"12:00": 0.1301, "12:15": 0.12525},
        _tz_service=TimezoneService(hass, "SE4", config),
    )
    provider = asyncio.Event()

    async def fetch_data():
        if manager.fetch_data.await_count > 1:
            await provider.wait()
        return data

    values = []
    # Pin this area's interval-start offset to 2 s within the refresh period.
    with freeze_time("2026-10-13T10:14:00Z") as clock, patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.random.uniform",
        return_value=2.0,
    ), patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.UnifiedPriceManager"
    ) as manager_class, patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
    ), patch(
        "custom_components.ge_spot.get_exchange_service",
        new=AsyncMock(return_value=MagicMock()),
    ):
        manager = manager_class.return_value
        manager.fetch_data = AsyncMock(side_effect=fetch_data)
        manager.async_close = AsyncMock()
        manager._health_check_scheduled = True
        manager._tz_service = data._tz_service
        assert await hass.config_entries.async_setup(entry.entry_id)
        coordinator = hass.data[DOMAIN][entry.entry_id]
        remove_listener = coordinator.async_add_listener(
            lambda: values.append(coordinator.data.current_price)
        )
        try:
            # The scheduled refresh starts and waits on the provider.
            clock.tick(timedelta(seconds=31))
            async_fire_time_changed(hass, dt_util.now())
            await hass.async_block_till_done()
            assert manager.fetch_data.await_count == 2
            assert values == []
            # The 12:15 interval starts while that refresh is still waiting.
            clock.tick(timedelta(seconds=32))
            async_fire_time_changed(hass, dt_util.now())
            await hass.async_block_till_done()
            assert values == [0.12525]
        finally:
            provider.set()
            await hass.async_block_till_done(wait_background_tasks=True)
            remove_listener()
            await coordinator.async_shutdown()
            await coordinator.async_close()


async def test_new_day_refreshes_instead_of_showing_yesterdays_price(hass):
    """Cached prices describe the previous day until a refresh moves tomorrow's."""
    config = {Config.AREA: "SE4", Config.CURRENCY: "EUR"}
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)
    timezone_service = TimezoneService(hass, "SE4", config)
    previous_day = IntervalPriceData(
        today_interval_prices={"23:45": 0.5, "00:00": 0.1},
        tomorrow_interval_prices={"00:00": 0.2},
        _tz_service=timezone_service,
    )
    new_day = IntervalPriceData(
        today_interval_prices={"00:00": 0.2}, _tz_service=timezone_service
    )
    values = []
    with freeze_time("2026-10-13T21:59:50Z") as clock, patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.random.uniform",
        return_value=2.0,
    ), patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.UnifiedPriceManager"
    ) as manager_class, patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
    ), patch(
        "custom_components.ge_spot.get_exchange_service",
        new=AsyncMock(return_value=MagicMock()),
    ):
        manager = manager_class.return_value
        manager.fetch_data = AsyncMock(side_effect=[previous_day, new_day])
        # No cache for the new day yet.
        manager.get_cached_data = MagicMock(return_value=None)
        manager.async_close = AsyncMock()
        manager._health_check_scheduled = True
        manager._tz_service = timezone_service
        assert await hass.config_entries.async_setup(entry.entry_id)
        coordinator = hass.data[DOMAIN][entry.entry_id]
        remove_listener = coordinator.async_add_listener(
            lambda: values.append(coordinator.data.current_price)
        )
        try:
            # Midnight in Stockholm, before the scheduled refresh is due.
            clock.tick(timedelta(seconds=15))
            async_fire_time_changed(hass, dt_util.now())
            await hass.async_block_till_done(wait_background_tasks=True)
            assert values == [0.2]
            assert manager.fetch_data.await_count == 2
        finally:
            remove_listener()
            await coordinator.async_shutdown()
            await coordinator.async_close()


async def test_new_day_shows_cached_prices_while_refresh_waits(hass):
    """A refresh waiting on providers must not delay the new day's cached price."""
    config = {Config.AREA: "SE4", Config.CURRENCY: "EUR"}
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)
    timezone_service = TimezoneService(hass, "SE4", config)
    previous_day = IntervalPriceData(
        today_interval_prices={"23:45": 0.5, "00:00": 0.1},
        tomorrow_interval_prices={"00:00": 0.2},
        _tz_service=timezone_service,
    )
    # Today's cache after the midnight migration.
    new_day = IntervalPriceData(
        today_interval_prices={"00:00": 0.2}, _tz_service=timezone_service
    )
    provider = asyncio.Event()

    async def fetch_data():
        if manager.fetch_data.await_count == 1:
            return previous_day
        # The new-day refresh looks for the next day's prices.
        await provider.wait()
        return new_day

    values = []
    with freeze_time("2026-10-13T21:59:50Z") as clock, patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.random.uniform",
        return_value=2.0,
    ), patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.UnifiedPriceManager"
    ) as manager_class, patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
    ), patch(
        "custom_components.ge_spot.get_exchange_service",
        new=AsyncMock(return_value=MagicMock()),
    ):
        manager = manager_class.return_value
        manager.fetch_data = AsyncMock(side_effect=fetch_data)
        manager.get_cached_data = MagicMock(return_value=new_day)
        manager.async_close = AsyncMock()
        manager._health_check_scheduled = True
        manager._tz_service = timezone_service
        assert await hass.config_entries.async_setup(entry.entry_id)
        coordinator = hass.data[DOMAIN][entry.entry_id]
        remove_listener = coordinator.async_add_listener(
            lambda: values.append(coordinator.data.current_price)
        )
        try:
            # Midnight in Stockholm, before the scheduled refresh is due.
            clock.tick(timedelta(seconds=15))
            async_fire_time_changed(hass, dt_util.now())
            await hass.async_block_till_done()
            assert manager.fetch_data.await_count == 2
            assert values == [0.2]
            provider.set()
            await hass.async_block_till_done(wait_background_tasks=True)
            assert values == [0.2, 0.2]
        finally:
            provider.set()
            await hass.async_block_till_done(wait_background_tasks=True)
            remove_listener()
            await coordinator.async_shutdown()
            await coordinator.async_close()


async def test_interval_offset_stays_within_one_interval(hass):
    """A refresh period longer than an interval must not skip interval starts."""
    from custom_components.ge_spot.coordinator.unified_price_manager import (
        UnifiedPriceManager,
    )
    from custom_components.ge_spot.const.defaults import Defaults
    from custom_components.ge_spot.const.time import TimeInterval

    config = {
        Config.AREA: "SE4",
        Config.CURRENCY: "EUR",
        Config.INCLUDE_VAT: False,
        Config.DISPLAY_UNIT: "decimal",
    }
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)
    timezone_service = TimezoneService(hass, "SE4", config)
    previous_day = IntervalPriceData(
        today_interval_prices={"23:45": 0.5, "00:00": 0.1},
        tomorrow_interval_prices={"00:00": 0.2},
        _tz_service=timezone_service,
    )
    new_day = IntervalPriceData(
        today_interval_prices={"00:00": 0.2}, _tz_service=timezone_service
    )
    values = []
    provider = asyncio.Event()

    async def fetch_data():
        if manager.fetch_data.await_count == 1:
            return previous_day
        await provider.wait()
        return new_day

    # A 20-minute refresh period, with the offset near the top of its range.
    with freeze_time("2026-10-13T21:59:50Z") as clock, patch.object(
        Defaults, "UPDATE_INTERVAL", 20
    ), patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.random.uniform",
        side_effect=lambda low, high: high * 0.99,
    ), patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.UnifiedPriceManager"
    ) as manager_class, patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
    ), patch(
        "custom_components.ge_spot.get_exchange_service",
        new=AsyncMock(return_value=MagicMock()),
    ):
        manager = UnifiedPriceManager(hass, "SE4", "EUR", config)
        manager_class.return_value = manager
        manager._cache_manager.store("SE4", "nordpool", previous_day)
        manager.fetch_data = AsyncMock(side_effect=fetch_data)
        manager.async_close = AsyncMock()
        manager._health_check_scheduled = True
        manager._tz_service = timezone_service
        assert await hass.config_entries.async_setup(entry.entry_id)
        coordinator = hass.data[DOMAIN][entry.entry_id]
        remove_listener = coordinator.async_add_listener(
            lambda: values.append(coordinator.data.current_price)
        )
        try:
            assert (
                coordinator._interval_update_offset
                < TimeInterval.get_interval_seconds()
            )
            # The 23:45 interval's write, delayed by the offset.
            clock.tick(timedelta(seconds=2))
            async_fire_time_changed(hass, dt_util.now())
            await hass.async_block_till_done()
            assert values == [0.5]
            # Midnight's write lands before the 00:15 interval starts and is
            # handled as a new day.
            clock.tick(timedelta(minutes=15))
            async_fire_time_changed(hass, dt_util.now())
            await hass.async_block_till_done()
            assert manager.fetch_data.await_count == 2
            assert values[1] == 0.2
            assert coordinator.data.today_interval_prices == {"00:00": 0.2}
        finally:
            provider.set()
            await hass.async_block_till_done(wait_background_tasks=True)
            remove_listener()
            await coordinator.async_shutdown()
            await coordinator.async_close()


@pytest.mark.parametrize(
    ("zone", "day"),
    [
        ("Europe/Stockholm", "2026-03-29"),
        ("Europe/Stockholm", "2026-10-25"),
        # Lord Howe Island moves its clocks by half an hour.
        ("Australia/Lord_Howe", "2026-10-04"),
        ("Australia/Lord_Howe", "2026-04-05"),
    ],
)
async def test_interval_starts_follow_displayed_intervals_across_dst(hass, zone, day):
    """Every displayed quarter-hour gets one write, also on DST change days."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    display_tz = ZoneInfo(zone)
    scheduled = []
    with patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.random.uniform",
        return_value=20.0,
    ), patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.UnifiedPriceManager"
    ) as manager_class, patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.async_track_point_in_utc_time",
        side_effect=lambda hass, action, point: scheduled.append(point),
    ):
        manager_class.return_value._tz_service.target_timezone = display_tz
        coordinator = UnifiedPriceCoordinator(
            hass, "SE4", "EUR", timedelta(seconds=30), {Config.AREA: "SE4"}
        )
        midnight = datetime.fromisoformat(day)
        start = midnight.replace(tzinfo=display_tz).astimezone(dt_util.UTC)
        end = (midnight + timedelta(days=1)).replace(tzinfo=display_tz)
        end = end.astimezone(dt_util.UTC)
        now = start - timedelta(minutes=1)
        with patch.object(dt_util, "utcnow", side_effect=lambda: now):
            while now < end:
                coordinator._schedule_interval_update()
                now = scheduled[-1]

    starts = [point - timedelta(seconds=20) for point in scheduled[:-1]]
    keys = [point.astimezone(display_tz).strftime("%H:%M") for point in starts]
    expected = int((end - start).total_seconds() // 900)
    assert starts[0] == start
    assert len(starts) == expected
    assert all(b - a == timedelta(minutes=15) for a, b in zip(starts, starts[1:]))
    assert all(int(key[3:]) % 15 == 0 for key in keys)


@pytest.mark.asyncio
async def test_sensor_platform_setup(hass, monkeypatch):
    """Test that sensor platform can be set up without errors."""
    # Patch _EXCHANGE_SERVICE.get_rates and get_exchange_service before anything else
    from custom_components.ge_spot.utils import exchange_service as exch_mod

    mock_exchange_service = MagicMock()
    mock_exchange_service.get_rates = AsyncMock(return_value=None)
    mock_exchange_service.close = AsyncMock(return_value=None)
    monkeypatch.setattr(exch_mod, "_EXCHANGE_SERVICE", mock_exchange_service)
    monkeypatch.setattr(
        exch_mod, "get_exchange_service", AsyncMock(return_value=mock_exchange_service)
    )

    # --- Setup Mock Config Entry ---
    config_data = {
        Config.AREA: "SE4",
        Config.CURRENCY: "SEK",
    }
    options_data = {
        Config.INCLUDE_VAT: False,
        Config.VAT: 25,
        Config.DISPLAY_UNIT: "decimal",
        Config.PRECISION: 2,
    }
    mock_entry = MockConfigEntry(
        domain=DOMAIN, data=config_data, options=options_data, entry_id="test_entry_123"
    )
    mock_entry.add_to_hass(hass)

    # --- Setup Mock Coordinator ---
    # Mock the coordinator completely to avoid background tasks
    mock_coordinator = MagicMock(spec=UnifiedPriceCoordinator)
    mock_coordinator.data = MOCK_COORDINATOR_DATA
    mock_coordinator.async_config_entry_first_refresh = AsyncMock()
    mock_coordinator.async_add_listener = MagicMock()
    mock_coordinator.async_remove_listener = MagicMock()

    # Store coordinator in hass.data as the integration __init__ would
    hass.data.setdefault(DOMAIN, {})[mock_entry.entry_id] = mock_coordinator

    # Mock the integration's async_setup_entry to avoid full setup
    with patch("custom_components.ge_spot.async_setup_entry", return_value=True):
        setup_result = await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

    # --- Assertions ---
    assert setup_result is True, "Config entry setup should return True"
    assert (
        mock_entry.state
        == pytest.importorskip("homeassistant.config_entries").ConfigEntryState.LOADED
    )

    # --- Cleanup ---
    with patch("custom_components.ge_spot.async_unload_entry", return_value=True):
        unload_result = await hass.config_entries.async_unload(mock_entry.entry_id)
        await hass.async_block_till_done()

    assert unload_result is True, "Config entry unload should return True"
