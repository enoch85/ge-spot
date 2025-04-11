"""Rate limiting utilities for GE-Spot integration."""
import logging
import datetime
from typing import Optional, Tuple, Dict, Any

from ..const.network import Network

_LOGGER = logging.getLogger(__name__)

class RateLimiter:
    """Shared rate limiting logic for API requests."""
    
    @staticmethod
    def should_skip_fetch(
        last_fetched: Optional[datetime.datetime], 
        current_time: datetime.datetime,
        consecutive_failures: int = 0,
        last_failure_time: Optional[datetime.datetime] = None,
        last_successful_fetch: Optional[Dict[str, Any]] = None,
        configured_interval: Optional[int] = None
    ) -> Tuple[bool, str]:
        """Determine if we should skip fetching based on rate limiting rules.
        
        Args:
            last_fetched: The last time a successful fetch was performed
            current_time: The current time
            consecutive_failures: Number of consecutive failures (for backoff)
            last_failure_time: When the last failure occurred
            last_successful_fetch: Last successful fetch data (for checking hourly prices)
            configured_interval: User-configured update interval in minutes
            
        Returns:
            Tuple of (should_skip, reason)
        """
        if last_fetched is None:
            return False, "No previous fetch"

        # Calculate time since last fetch in minutes
        time_diff = (current_time - last_fetched).total_seconds() / 60  # in minutes

        # Get effective interval - respect user configuration but enforce minimum
        min_interval = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
        
        # Use user's configured interval if it's set and longer than the minimum
        effective_interval = configured_interval or min_interval
        effective_interval = max(min_interval, effective_interval)

        # If less than minimum fetch interval, always skip
        if time_diff < min_interval:
            reason = f"Last fetch was only {time_diff:.1f} minutes ago (minimum: {min_interval})"
            return True, reason
            
        # Apply progressive backoff based on consecutive failures
        if consecutive_failures > 0:
            # Exponential backoff: doubling with each failure, capped at 45 minutes
            backoff_minutes = min(45, 2 ** (consecutive_failures - 1) * min_interval)
            if last_failure_time and (current_time - last_failure_time).total_seconds() / 60 < backoff_minutes:
                next_retry = last_failure_time + datetime.timedelta(minutes=backoff_minutes)
                reason = f"Backing off due to {consecutive_failures} consecutive failures. Next retry: {next_retry.strftime('%H:%M:%S')}"
                return True, reason

        # Check for special time windows when data should be fetched regardless of standard intervals
        hour = current_time.hour
        for start_hour, end_hour in Network.Defaults.SPECIAL_HOUR_WINDOWS:
            if start_hour <= hour < end_hour:
                reason = f"In special hour window {start_hour}-{end_hour}, allowing fetch"
                return False, reason

        # Check if we have hourly prices for the current hour
        if last_successful_fetch and "hourly_prices" in last_successful_fetch:
            hourly_prices = last_successful_fetch["hourly_prices"]
            # If we already have prices for the current hour, use the effective interval
            current_hour_str = f"{current_time.hour:02d}:00"
            if current_hour_str in hourly_prices:
                if time_diff < effective_interval:
                    reason = f"Already have price for current hour and last fetch was {time_diff:.1f} min ago (configured: {effective_interval})"
                    return True, reason
                else:
                    reason = f"Have price for current hour but {time_diff:.1f} min since last fetch exceeds configured interval"
                    return False, reason

        # Standard rate limiting - don't fetch more often than the effective interval
        if time_diff < effective_interval:
            reason = f"Last fetch was {time_diff:.1f} minutes ago (configured interval: {effective_interval})"
            return True, reason
            
        return False, f"Time since last fetch ({time_diff:.1f} min) exceeds configured interval ({effective_interval} min)"
