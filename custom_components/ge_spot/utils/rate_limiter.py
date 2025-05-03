"""Rate limiting utilities for GE-Spot integration."""
import logging
import datetime
from typing import Optional, Tuple

from ..const.network import Network
from ..const.sources import Source
from ..utils.debug_utils import log_rate_limiting

_LOGGER = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, identifier=None):
        """Initialize the RateLimiter with an optional identifier."""
        self.identifier = identifier

    @staticmethod
    def should_skip_fetch(
        last_fetched: Optional[datetime.datetime],
        current_time: datetime.datetime,
        consecutive_failures: int = 0,
        last_failure_time: Optional[datetime.datetime] = None,
        min_interval: int = None,
        last_successful_fetch: Optional[datetime.datetime] = None,
        source: str = None,
        area: str = None
    ) -> Tuple[bool, str]:
        """Determine if we should skip fetching based on rate limiting rules."""
        # If never fetched, always fetch
        if last_fetched is None:
            reason = "No previous fetch"
            log_rate_limiting(area or "unknown", False, reason, source)
            return False, reason

        # Force update at hour boundaries
        if last_fetched.hour != current_time.hour:
            reason = "Hour boundary crossed, forcing update"
            log_rate_limiting(area or "unknown", False, reason, source)
            return False, reason

        # Special case for AEMO - always allow fetch during market hours (7:00-19:00)
        if source == Source.AEMO and 7 <= current_time.hour < 19:
            reason = "Market hours for AEMO (7:00-19:00), allowing fetch"
            log_rate_limiting(area or "unknown", False, reason, source)
            return False, reason

        # Calculate time since last fetch in minutes
        time_diff = (current_time - last_fetched).total_seconds() / 60

        # Use specified min_interval or fall back to default
        if min_interval is None:
            if source:
                from ..const.intervals import SourceIntervals
                min_interval = SourceIntervals.get_interval(source)
            else:
                min_interval = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES

        # If less than minimum fetch interval, skip
        if time_diff < min_interval:
            reason = f"Last fetch was only {time_diff:.1f} minutes ago (minimum: {min_interval})"
            log_rate_limiting(area or "unknown", True, reason, source)
            return True, reason

        # Apply exponential backoff for failures
        if consecutive_failures > 0:
            backoff_minutes = min(45, 2 ** (consecutive_failures - 1) * min_interval)
            if last_failure_time and (current_time - last_failure_time).total_seconds() / 60 < backoff_minutes:
                next_retry = last_failure_time + datetime.timedelta(minutes=backoff_minutes)
                reason = f"Backing off after {consecutive_failures} failures. Next retry: {next_retry.strftime('%H:%M:%S')}"
                log_rate_limiting(area or "unknown", True, reason, source)
                return True, reason

        # Check for special time windows (e.g., when new prices are released)
        hour = current_time.hour
        for start_hour, end_hour in Network.Defaults.SPECIAL_HOUR_WINDOWS:
            if start_hour <= hour < end_hour:
                reason = f"In special hour window {start_hour}-{end_hour}, allowing fetch"
                log_rate_limiting(area or "unknown", False, reason, source)
                return False, reason

        # Allow fetch if enough time has passed
        reason = f"Time since last fetch ({time_diff:.1f} min) exceeds minimum interval"
        log_rate_limiting(area or "unknown", False, reason, source)
        return False, reason
