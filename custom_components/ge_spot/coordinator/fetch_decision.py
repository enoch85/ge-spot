"""Decision maker for when to fetch new data.

This module uses data validity tracking to determine when fetches are needed.
Instead of asking "do we have complete data?", we ask "how long is our data valid for?"
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional, Tuple

from ..const.network import Network
from .data_validity import DataValidity

_LOGGER = logging.getLogger(__name__)


class FetchDecisionMaker:
    """Decision maker for when to fetch new data.

    Uses DataValidity to make clear, timestamp-based decisions about when to fetch.
    Goal: Only fetch 1-2 times per day (typically at 13:00 for tomorrow's data).
    """

    def __init__(self, tz_service: Any):
        """Initialize the fetch decision maker.

        Args:
            tz_service: Timezone service instance
        """
        self._tz_service = tz_service

    def should_fetch(
        self,
        now: datetime,
        last_fetch: Optional[datetime],
        data_validity: DataValidity,
        fetch_interval_minutes: int = 15,
        in_grace_period: bool = False,
        is_health_check: bool = False,
        area: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Determine if we need to fetch from API based on data validity.

        Decision logic:
        1. CRITICAL: No data for current interval → FETCH IMMEDIATELY
        2. Running out: Less than safety buffer intervals remaining → FETCH
        3. Special window: 13:00-14:00 and missing tomorrow's data → FETCH
        4. Initial fetch: Never fetched before → FETCH
        5. Otherwise: SKIP (we have enough future data)

        Args:
            now: Current datetime
            last_fetch: Last API fetch time (used for rate limiting)
            data_validity: DataValidity object describing our current data coverage
            fetch_interval_minutes: Minimum minutes between fetches (rate limit)
            in_grace_period: True if within grace period after startup/reload
            is_health_check: True if this is a health check validation (bypasses rate limiting)

        Returns:
            Tuple of (need_api_fetch, reason)
        """
        # CRITICAL CHECK: Do we have data for the current interval?
        if not data_validity.has_current_interval:
            current_interval_key = self._tz_service.get_current_interval_key()
            reason = f"No data for current interval ({current_interval_key}) - fetching data immediately"
            _LOGGER.info(reason)  # INFO level: expected on reload, not an error

            # Respect rate limiting UNLESS this is a health check
            if last_fetch and not is_health_check:
                from ..utils.rate_limiter import RateLimiter

                should_skip, skip_reason = RateLimiter.should_skip_fetch(
                    last_fetched=last_fetch,
                    current_time=now,
                    min_interval=fetch_interval_minutes,
                    in_grace_period=in_grace_period,
                )

                if should_skip:
                    reason = (
                        f"No current interval data, but rate limited ({skip_reason})"
                    )
                    # INFO level: This is expected when parser changes or cache invalidation happens
                    # The system will fall back to any available cached data
                    _LOGGER.info(reason)
                    return False, reason

            # If is_health_check=True, we skip the rate limit check entirely
            if is_health_check:
                reason += " (health check - bypassing rate limit)"

            return True, reason

        # Initial fetch check (never fetched before)
        if not last_fetch:
            reason = "Initial startup - fetching data"
            _LOGGER.info(reason)
            return True, reason

        # GRACE PERIOD CHECK: During grace period, if we have partial today data, try to get complete data
        # This handles cases where old cache has only tomorrow's data (0 today, 96 tomorrow)
        if in_grace_period:
            from ..const.time import TimeInterval
            from homeassistant.util import dt as dt_util

            # Use DST-aware interval counting for today's date
            today = dt_util.now(area_timezone)
            required_today_intervals = TimeInterval.get_expected_intervals_for_date(
                today, area_timezone
            )

            if data_validity.today_interval_count < required_today_intervals:
                reason = (
                    f"Grace period: incomplete today data (have {data_validity.today_interval_count} intervals, "
                    f"need {required_today_intervals}) - fetching to get complete data"
                )
                _LOGGER.info(reason)

                # Check rate limiting (still respect it even in grace period, but with relaxed rules)
                from ..utils.rate_limiter import RateLimiter

                should_skip, skip_reason = RateLimiter.should_skip_fetch(
                    last_fetched=last_fetch,
                    current_time=now,
                    min_interval=fetch_interval_minutes,
                    in_grace_period=in_grace_period,
                    area=area,
                )

                if should_skip:
                    reason = f"Grace period with incomplete today data, but rate limited ({skip_reason})"
                    _LOGGER.info(reason)
                    return False, reason

                return True, reason

        # Calculate how much data we have left
        intervals_remaining = data_validity.intervals_remaining(now)

        _LOGGER.debug(
            f"Data validity check: {intervals_remaining} intervals remaining, validity: {data_validity}"
        )

        # SAFETY CHECK: Are we running low on data?
        if intervals_remaining < Network.Defaults.DATA_SAFETY_BUFFER_INTERVALS:
            reason = (
                f"Running low on data: only {intervals_remaining} intervals remaining "
                f"(safety buffer: {Network.Defaults.DATA_SAFETY_BUFFER_INTERVALS} intervals) - fetching"
            )
            _LOGGER.info(reason)

            # Check rate limiting
            from ..utils.rate_limiter import RateLimiter

            should_skip, skip_reason = RateLimiter.should_skip_fetch(
                last_fetched=last_fetch,
                current_time=now,
                min_interval=fetch_interval_minutes,
                in_grace_period=in_grace_period,
            )

            if should_skip:
                reason = f"Low on data but rate limited: {skip_reason}"
                _LOGGER.warning(reason)
                return False, reason

            return True, reason

        # SPECIAL WINDOW CHECK: During tomorrow data fetch window (13:00-15:00) - time to fetch tomorrow's data
        hour = now.hour
        # Use the second window from SPECIAL_HOUR_WINDOWS which is for tomorrow's data
        start_hour, end_hour = Network.Defaults.SPECIAL_HOUR_WINDOWS[1]

        if start_hour <= hour < end_hour:
            # Check if we already have tomorrow's complete data
            tomorrow_date = now.date() + timedelta(days=1)

            # Check against the required interval threshold (76 intervals = 80% of 96)
            if (
                data_validity.tomorrow_interval_count
                < Network.Defaults.REQUIRED_TOMORROW_INTERVALS
            ):
                reason = (
                    f"Special fetch window ({start_hour}:00-{end_hour}:00) - "
                    f"missing tomorrow's data (have {data_validity.tomorrow_interval_count} intervals, "
                    f"need {Network.Defaults.REQUIRED_TOMORROW_INTERVALS}) - fetching"
                )
                _LOGGER.info(reason)

                # Check rate limiting
                from ..utils.rate_limiter import RateLimiter

                should_skip, skip_reason = RateLimiter.should_skip_fetch(
                    last_fetched=last_fetch,
                    current_time=now,
                    min_interval=fetch_interval_minutes,
                    in_grace_period=in_grace_period,
                )

                if should_skip:
                    reason = (
                        f"Special window but rate limited: {skip_reason}. "
                        f"Will retry in next update cycle."
                    )
                    _LOGGER.info(reason)
                    return False, reason

                return True, reason
            else:
                reason = (
                    f"Special window ({start_hour}:00-{end_hour}:00) but already have tomorrow's data "
                    f"({data_validity.tomorrow_interval_count} intervals) - skipping"
                )
                _LOGGER.debug(reason)
                return False, reason

        # POST-WINDOW RETRY: After special window, check if we missed tomorrow's data
        elif hour >= end_hour:
            # If we don't have tomorrow's data and it's after the window, try to fetch
            if (
                data_validity.tomorrow_interval_count
                < Network.Defaults.REQUIRED_TOMORROW_INTERVALS
            ):
                reason = (
                    f"After special window ({end_hour}:00) but missing tomorrow's data "
                    f"(have {data_validity.tomorrow_interval_count} intervals, "
                    f"need {Network.Defaults.REQUIRED_TOMORROW_INTERVALS}) - retry fetch"
                )
                _LOGGER.info(reason)

                # Check rate limiting - don't spam the API
                from ..utils.rate_limiter import RateLimiter

                should_skip, skip_reason = RateLimiter.should_skip_fetch(
                    last_fetched=last_fetch,
                    current_time=now,
                    min_interval=fetch_interval_minutes,
                    in_grace_period=in_grace_period,
                )

                if should_skip:
                    reason = (
                        f"After window but missing tomorrow data - rate limited: {skip_reason}. "
                        f"Will retry in next update cycle."
                    )
                    _LOGGER.debug(reason)
                    return False, reason

                return True, reason

        # ALL GOOD: We have enough data
        reason = (
            f"Data valid until {data_validity.data_valid_until.strftime('%Y-%m-%d %H:%M') if data_validity.data_valid_until else 'unknown'} "
            f"({intervals_remaining} intervals remaining) - no fetch needed"
        )
        _LOGGER.debug(reason)
        return False, reason
