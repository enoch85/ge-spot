"""Rate limiting utilities for GE-Spot integration."""

import logging
import datetime
from typing import Optional, Tuple

from ..const.network import Network
from ..const.sources import Source
from ..const.intervals import SourceIntervals
from ..const.time import TimeInterval
from ..utils.debug_utils import log_rate_limiting

_LOGGER = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter for API fetch operations.

    All methods are static as rate limiting is coordinated globally
    through shared state in UnifiedPriceManager.
    """

    @staticmethod
    def should_skip_fetch(
        last_fetched: Optional[datetime.datetime],
        current_time: datetime.datetime,
        consecutive_failures: int = 0,
        last_failure_time: Optional[datetime.datetime] = None,
        min_interval: int = None,
        last_successful_fetch: Optional[datetime.datetime] = None,
        source: str = None,
        area: str = None,
        in_grace_period: bool = False,
    ) -> Tuple[bool, str]:
        """Determine if we should skip fetching based on rate limiting rules.

        Priority order (highest to lowest):
        0. Grace period → bypass rate limiting for fallback attempts
        1. Never fetched → always fetch
        2. Failure backoff → prevent hammering during issues
        3. AEMO market hours → allow frequent updates
        4. Special time windows → reduced rate limiting (1 min vs 15 min)
        5. Minimum interval → enforce basic rate limiting (15 min)
        6. Interval boundary → force updates at interval transitions

        Args:
            last_fetched: When last fetch occurred
            current_time: Current time
            consecutive_failures: Number of consecutive failures
            last_failure_time: When last failure occurred
            min_interval: Minimum interval between fetches in minutes
            last_successful_fetch: When last successful fetch occurred
            source: Source identifier
            area: Area identifier
            in_grace_period: True if within grace period after startup/reload
        """
        # If never fetched, always fetch
        if last_fetched is None:
            reason = "No previous fetch"
            log_rate_limiting(area or "unknown", False, reason, source)
            return False, reason

        # PRIORITY 0: During grace period, bypass rate limiting to allow fallback attempts
        # This ensures that after HA restart, we can immediately try all fallback sources
        # to find one with complete data, without waiting for rate limit intervals
        if in_grace_period:
            reason = "Within grace period after startup - bypassing rate limiting for fallback attempts"
            log_rate_limiting(area or "unknown", False, reason, source)
            return False, reason

        # PRIORITY 1: Apply exponential backoff for failures (highest priority after first fetch)
        # This allows retries after failures while preventing API hammering
        # Backoff schedule: 1st fail=15min, 2nd=30min, 3rd=60min (capped)
        if consecutive_failures > 0:
            # Use specified min_interval or fall back to default for backoff calculation
            if min_interval is None:
                if source:
                    from ..const.intervals import SourceIntervals

                    min_interval = SourceIntervals.get_interval(source)
                else:
                    min_interval = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES

            backoff_minutes = min(60, 2 ** (consecutive_failures - 1) * min_interval)
            if (
                last_failure_time
                and (current_time - last_failure_time).total_seconds()
                / Network.Defaults.SECONDS_PER_MINUTE
                < backoff_minutes
            ):
                next_retry = last_failure_time + datetime.timedelta(
                    minutes=backoff_minutes
                )
                reason = f"Backing off after {consecutive_failures} failures. Next retry: {next_retry.strftime('%H:%M:%S')}"
                log_rate_limiting(area or "unknown", True, reason, source)
                return True, reason

        # PRIORITY 2: Special case for AEMO - always allow fetch during market hours (7:00-19:00)
        if source == Source.AEMO and 7 <= current_time.hour < 19:
            reason = "Market hours for AEMO (7:00-19:00), allowing fetch"
            log_rate_limiting(area or "unknown", False, reason, source)
            return False, reason

        # PRIORITY 3: Check for special time windows (e.g. when new prices are released)
        # Use reduced rate limiting (1 min) during these windows for faster data acquisition
        hour = current_time.hour
        in_special_window = False
        special_window_range = None

        for start_hour, end_hour in Network.Defaults.SPECIAL_HOUR_WINDOWS:
            if start_hour <= hour < end_hour:
                in_special_window = True
                special_window_range = (start_hour, end_hour)
                break

        if in_special_window:
            # Calculate time since last fetch
            time_diff = (
                current_time - last_fetched
            ).total_seconds() / Network.Defaults.SECONDS_PER_MINUTE
            special_min_interval = Network.Defaults.SPECIAL_WINDOW_MIN_INTERVAL_MINUTES

            if time_diff < special_min_interval:
                reason = (
                    f"In special window {special_window_range[0]:02d}:00-{special_window_range[1]:02d}:00 "
                    f"but last fetch was {time_diff:.1f} min ago (minimum: {special_min_interval} min during windows)"
                )
                log_rate_limiting(area or "unknown", True, reason, source)
                return True, reason

            reason = (
                f"In special window {special_window_range[0]:02d}:00-{special_window_range[1]:02d}:00, "
                f"allowing fetch ({time_diff:.1f} min >= {special_min_interval} min)"
            )
            log_rate_limiting(area or "unknown", False, reason, source)
            return False, reason

        # Calculate time since last fetch in minutes for remaining checks
        time_diff = (
            current_time - last_fetched
        ).total_seconds() / Network.Defaults.SECONDS_PER_MINUTE

        # Use specified min_interval or fall back to default
        if min_interval is None:
            if source:
                min_interval = SourceIntervals.get_interval(source)
            else:
                min_interval = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES

        # PRIORITY 4: If less than minimum fetch interval, skip
        if time_diff < min_interval:
            reason = f"Last fetch was only {time_diff:.1f} minutes ago (minimum: {min_interval})"
            log_rate_limiting(area or "unknown", True, reason, source)
            return True, reason

        # PRIORITY 5: Force update at interval boundaries (configuration-driven)
        # This runs last so it respects all the above constraints
        interval_minutes = TimeInterval.get_interval_minutes()

        # Calculate interval keys for both timestamps
        def get_interval_key(dt: datetime.datetime) -> str:
            """Get interval key (HH:MM) for a datetime."""
            minute = (dt.minute // interval_minutes) * interval_minutes
            return f"{dt.hour:02d}:{minute:02d}"

        last_interval_key = get_interval_key(last_fetched)
        current_interval_key = get_interval_key(current_time)

        if last_interval_key != current_interval_key:
            reason = f"Interval boundary crossed (from {last_interval_key} to {current_interval_key}), forcing update"
            log_rate_limiting(area or "unknown", False, reason, source)
            return False, reason

        # Allow fetch if enough time has passed
        reason = f"Time since last fetch ({time_diff:.1f} min) exceeds minimum interval"
        log_rate_limiting(area or "unknown", False, reason, source)
        return False, reason
