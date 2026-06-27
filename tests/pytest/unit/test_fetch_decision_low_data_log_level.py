"""Regression: 'Low on data but rate limited' must not be logged at WARNING.

When an area is low on data but was fetched recently, the rate limiter correctly
skips the fetch. That is expected operation (its sibling skip-reasons in
FetchDecisionMaker are INFO), but it was logged at WARNING and fired every update
cycle for every affected area — flooding the Core log's warning view during
upstream outages. It must log at INFO.
"""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from custom_components.ge_spot.coordinator.fetch_decision import FetchDecisionMaker


def _low_data_rate_limited_decision(caplog):
    decision = FetchDecisionMaker(tz_service=MagicMock())
    now = datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc)

    data_validity = MagicMock()
    data_validity.has_current_interval = True  # pass the critical check
    data_validity.intervals_remaining.return_value = 0  # below the safety buffer

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        need_fetch, reason = decision.should_fetch(
            now=now,
            last_fetch=now - timedelta(minutes=1),  # recent -> rate limited
            data_validity=data_validity,
            fetch_interval_minutes=15,
            in_grace_period=False,
        )
    return need_fetch, reason


def test_low_on_data_rate_limited_does_not_warn(caplog):
    need_fetch, reason = _low_data_rate_limited_decision(caplog)

    assert need_fetch is False
    assert "Low on data but rate limited" in reason
    warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert warnings == [], f"must not log WARNING, got: {warnings}"


def test_low_on_data_rate_limited_logged_at_info(caplog):
    _low_data_rate_limited_decision(caplog)

    infos = [
        r.message
        for r in caplog.records
        if r.levelname == "INFO" and "Low on data but rate limited" in r.message
    ]
    assert len(infos) == 1, f"expected one INFO line, got: {infos}"
