"""Regression coverage for routine logging and repeated update failures."""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ge_spot.const.network import Network
from custom_components.ge_spot.const.time import TimeInterval
from custom_components.ge_spot.const.intervals import SourceIntervals
from custom_components.ge_spot.coordinator.data_models import IntervalPriceData
from custom_components.ge_spot.coordinator.data_validity import calculate_data_validity
from custom_components.ge_spot.coordinator.fetch_decision import FetchDecisionMaker
from custom_components.ge_spot.coordinator.unified_price_manager import (
    UnifiedPriceCoordinator,
)


@pytest.mark.parametrize(
    "hour,has_current,low_data,reason",
    [
        (12, True, True, "Low on data but rate limited"),
        (12, False, True, "No current interval data, but rate limited"),
        (13, True, False, "Special window but rate limited"),
        (16, True, False, "After window but missing tomorrow data - rate limited"),
    ],
)
def test_rate_limited_fetch_decisions_only_log_debug(
    caplog, hour, has_current, low_data, reason
):
    decision = FetchDecisionMaker(tz_service=MagicMock())
    now = datetime(2026, 6, 27, hour, tzinfo=timezone.utc)
    validity = MagicMock()
    validity.has_current_interval = has_current
    validity.tomorrow_interval_count = 0
    validity.intervals_remaining.return_value = (
        0 if low_data else Network.Defaults.DATA_SAFETY_BUFFER_INTERVALS
    )

    with caplog.at_level(logging.DEBUG, logger=FetchDecisionMaker.__module__):
        need_fetch, result = decision.should_fetch(
            now=now,
            last_fetch=now - timedelta(minutes=1),
            data_validity=validity,
        )

    assert not need_fetch
    assert reason in result
    records = [r for r in caplog.records if r.name == FetchDecisionMaker.__module__]
    assert records and all(r.levelno == logging.DEBUG for r in records)
    assert any(reason in r.message for r in records)


async def test_update_failure_logs_once_until_recovery(hass, caplog, monkeypatch):
    with patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.UnifiedPriceManager"
    ) as manager_class:
        coordinator = UnifiedPriceCoordinator(
            hass,
            "SE4",
            "SEK",
            timedelta(minutes=Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES),
            {},
        )
    manager = manager_class.return_value
    empty = IntervalPriceData(area="SE4", source="None")
    empty._error = "No cache and no fetch: rate limited"
    empty._consecutive_failures = Network.Defaults.RETRY_COUNT
    manager.fetch_data = AsyncMock(return_value=empty)
    manager.is_in_grace_period.return_value = True
    caplog.set_level(logging.INFO, logger=UnifiedPriceCoordinator.__module__)
    clock = MagicMock(return_value=datetime(2026, 10, 13, 7, tzinfo=timezone.utc))
    monkeypatch.setattr(
        "custom_components.ge_spot.coordinator.unified_price_manager.dt_util.utcnow",
        clock,
    )

    assert await coordinator._async_update_data() is empty
    assert not caplog.records
    manager.is_in_grace_period.return_value = False
    clock.return_value += timedelta(
        minutes=Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
    )
    for reason in ("rate limited for 1 minute", "rate limited for 2 minutes"):
        empty._error = reason
        assert await coordinator._async_update_data() is empty
    assert sum(r.levelno == logging.WARNING for r in caplog.records) == 1

    recovered = IntervalPriceData(
        area="SE4",
        today_interval_prices={"00:00": 1.0},
        _tz_service=MagicMock(get_current_interval_key=MagicMock(return_value="00:00")),
    )
    manager.fetch_data.return_value = recovered
    for _ in range(2):
        assert await coordinator._async_update_data() is recovered
    assert sum("Price data recovered" in r.message for r in caplog.records) == 1

    manager.fetch_data.return_value = empty
    assert await coordinator._async_update_data() is empty
    assert sum(r.levelno == logging.WARNING for r in caplog.records) == 1
    clock.return_value += timedelta(
        minutes=Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
    )
    assert await coordinator._async_update_data() is empty
    assert sum(r.levelno == logging.WARNING for r in caplog.records) == 2


async def test_future_prices_cannot_hide_sustained_missing_current_price(hass, caplog):
    with patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.UnifiedPriceManager"
    ) as manager_class:
        coordinator = UnifiedPriceCoordinator(
            hass, "SE4", "SEK", timedelta(minutes=15), {}
        )
    manager = manager_class.return_value
    manager.is_in_grace_period.return_value = False
    manager.fetch_data = AsyncMock(
        return_value=IntervalPriceData(
            area="SE4",
            tomorrow_interval_prices={"00:00": 1.0},
            _tz_service=MagicMock(
                get_current_interval_key=MagicMock(return_value="00:00")
            ),
        )
    )
    caplog.set_level(logging.WARNING, logger=UnifiedPriceCoordinator.__module__)
    now = datetime(2026, 10, 13, 7, tzinfo=timezone.utc)
    with patch(
        "custom_components.ge_spot.coordinator.unified_price_manager.dt_util.utcnow",
        return_value=now,
    ) as clock:
        for _ in range(Network.Defaults.RETRY_COUNT + 2):
            await coordinator._async_update_data()
        assert not caplog.records
        clock.return_value = now + timedelta(
            minutes=Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
        )
        for _ in range(2):
            await coordinator._async_update_data()
    assert sum(r.levelno == logging.WARNING for r in caplog.records) == 1


def test_usable_startup_cache_does_not_require_network_fetch():
    validity = MagicMock()
    validity.has_current_interval = True
    validity.today_interval_count = TimeInterval.get_intervals_per_day()
    validity.tomorrow_interval_count = 0
    validity.intervals_remaining.return_value = TimeInterval.get_intervals_per_day()
    should_fetch, _ = FetchDecisionMaker(
        MagicMock(area_timezone=timezone.utc)
    ).should_fetch(
        now=datetime(2026, 10, 13, 7, tzinfo=timezone.utc),
        last_fetch=None,
        data_validity=validity,
        in_grace_period=True,
    )
    assert not should_fetch


def test_tomorrow_prices_do_not_count_as_current_data():
    validity = calculate_data_validity(
        {},
        {"07:00": 1.0},
        datetime(2026, 10, 13, 7, tzinfo=timezone.utc),
        "07:00",
        target_timezone="UTC",
    )
    assert not validity.has_current_interval


@pytest.mark.parametrize("source", ["aemo", "comed", "amber"])
@pytest.mark.parametrize("hour", [7, 13, 16])
def test_rolling_prices_refresh_without_day_ahead_windows(source, hour):
    now = datetime(2026, 10, 13, hour, tzinfo=timezone.utc)
    validity = MagicMock(has_current_interval=True)
    decision = FetchDecisionMaker(MagicMock())
    assert not decision.should_fetch(
        now, now - timedelta(minutes=1), validity, source=source
    )[0]
    assert decision.should_fetch(
        now,
        now - timedelta(minutes=SourceIntervals.get_interval(source)),
        validity,
        source=source,
    )[0]
