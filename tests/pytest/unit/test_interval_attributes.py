"""Interval price attributes and data validity across repeated state writes."""

from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from custom_components.ge_spot.const.time import TimeInterval
from custom_components.ge_spot.coordinator.data_models import IntervalPriceData
from custom_components.ge_spot.coordinator.data_validity import (
    calculate_data_validity,
)
from custom_components.ge_spot.sensor import base
from custom_components.ge_spot.sensor.price import PriceValueSensor

STOCKHOLM = ZoneInfo("Europe/Stockholm")


def _day_keys(last_hour=23):
    minutes = TimeInterval.get_interval_minutes()
    return [
        f"{hour:02d}:{minute:02d}"
        for hour in range(last_hour + 1)
        for minute in range(0, 60, minutes)
    ]


def _sensor():
    today = {key: 1.0 + i / 1000 for i, key in enumerate(_day_keys())}
    tomorrow = {key: 2.0 + i / 1000 for i, key in enumerate(_day_keys())}
    coordinator = Mock()
    coordinator.last_update_success = True
    coordinator.data = IntervalPriceData(
        today_interval_prices=today,
        tomorrow_interval_prices=tomorrow,
        today_raw_prices={key: price / 2 for key, price in today.items()},
        tomorrow_raw_prices={key: price / 2 for key, price in tomorrow.items()},
        source="nordpool",
        area="SE3",
        target_timezone="Europe/Stockholm",
    )
    sensor = PriceValueSensor(
        coordinator,
        {"area": "SE3", "vat": 0.25, "precision": 3, "currency": "SEK"},
        "current_price",
        "Current Price",
        lambda data: data.current_price,
    )
    sensor._tz_service = Mock(target_timezone=STOCKHOLM)
    return sensor, coordinator


@freeze_time("2026-11-11 14:05:00+01:00")
def test_state_writes_reuse_converted_interval_prices():
    """A refresh without new prices does not convert the interval lists again."""
    sensor, coordinator = _sensor()
    data = coordinator.data
    key_count = len(data.today_interval_prices) + len(data.tomorrow_interval_prices)

    with patch.object(
        base, "parse_interval_key", wraps=base.parse_interval_key
    ) as parse:
        first = sensor.extra_state_attributes
        assert parse.call_count == key_count
        parse.reset_mock()
        second = sensor.extra_state_attributes

    assert parse.call_count == 0
    assert second == first
    assert second["today_interval_prices"][0] == {
        "time": datetime(2026, 11, 11, 0, 0, tzinfo=STOCKHOLM),
        "value": 1.0,
        "raw_value": 0.5,
    }


def test_interval_prices_follow_edits_new_prices_and_new_day():
    """Kept entries are isolated from consumers and rebuilt when inputs change."""
    sensor, coordinator = _sensor()

    with freeze_time("2026-11-11 23:59:00+01:00") as frozen:
        shown = sensor.extra_state_attributes["today_interval_prices"]
        shown[0]["value"] = -1.0
        shown.clear()
        assert sensor.extra_state_attributes["today_interval_prices"][0]["value"] == 1.0

        coordinator.data = replace(
            coordinator.data,
            today_interval_prices={**coordinator.data.today_interval_prices},
        )
        coordinator.data.today_interval_prices["23:45"] = 9.0
        assert (
            sensor.extra_state_attributes["today_interval_prices"][-1]["value"] == 9.0
        )

        coordinator.data.today_interval_prices["23:45"] = 8.0  # edited in place
        assert (
            sensor.extra_state_attributes["today_interval_prices"][-1]["value"] == 8.0
        )

        frozen.move_to("2026-11-12 00:00:05+01:00")
        today = sensor.extra_state_attributes["today_interval_prices"]
        assert today[0]["time"] == datetime(2026, 11, 12, 0, 0, tzinfo=STOCKHOLM)


@pytest.mark.parametrize(
    ("today_keys", "tomorrow_keys", "expected_day", "expected_time"),
    [
        # Full today, no tomorrow
        (_day_keys(), [], 0, (23, 45)),
        # Tomorrow present: the latest tomorrow key wins
        (_day_keys(), _day_keys(13), 1, (13, 45)),
        # Fall-back DST suffixes and a single-digit hour parse like HH:MM
        (["00:00", "02:15_1", "02:15_2", "9:30"], [], 0, (9, 30)),
        # Malformed keys are skipped, also when they are all of tomorrow
        (["00:00", "11:45", "24:00"], ["bad"], 0, (11, 45)),
    ],
)
def test_last_valid_interval_is_latest_parsed_key(
    today_keys, tomorrow_keys, expected_day, expected_time
):
    """The last valid interval is the latest valid key of the latest day."""
    now = datetime(2026, 10, 25, 1, 30, tzinfo=STOCKHOLM)
    validity = calculate_data_validity(
        interval_prices=dict.fromkeys(today_keys, 1.0),
        tomorrow_interval_prices=dict.fromkeys(tomorrow_keys, 1.0),
        now=now,
        current_interval_key="01:30",
        target_timezone="Europe/Stockholm",
    )

    expected = datetime(2026, 10, 25 + expected_day, *expected_time, tzinfo=STOCKHOLM)
    assert validity.last_valid_interval == expected
    assert validity.last_valid_interval.tzinfo is STOCKHOLM
    assert validity.data_valid_until == expected + timedelta(
        minutes=TimeInterval.get_interval_minutes()
    )
