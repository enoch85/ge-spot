"""Rate limiting utilities for GE-Spot integration."""
import logging
import datetime
from typing import Optional, Tuple, Dict

from ..const.network import Network
from ..const.sources import Source
from ..const.intervals import SourceIntervals
from ..utils.debug_utils import log_rate_limiting

_LOGGER = logging.getLogger(__name__)

# Global registry to track last API calls across all components
# This ensures all components respect the same rate limiting
# Format: { area: { 'last_fetch': datetime, 'consecutive_failures': int, 'last_failure': datetime } }
_API_CALL_REGISTRY: Dict[str, Dict] = {}

class RateLimiter:
    """Shared rate limiting logic for API requests."""

    @staticmethod
    def _update_registry(
        area: str,
        fetch_time: Optional[datetime.datetime] = None,
        failure: bool = False,
        failure_time: Optional[datetime.datetime] = None
    ):
        """Update the global registry with latest API call information."""
        if area is None:
            return
            
        if area not in _API_CALL_REGISTRY:
            _API_CALL_REGISTRY[area] = {
                'last_fetch': None,
                'consecutive_failures': 0,
                'last_failure': None
            }
            
        if fetch_time:
            _API_CALL_REGISTRY[area]['last_fetch'] = fetch_time
            
        if failure:
            if 'consecutive_failures' not in _API_CALL_REGISTRY[area]:
                _API_CALL_REGISTRY[area]['consecutive_failures'] = 0
            _API_CALL_REGISTRY[area]['consecutive_failures'] += 1
            
            if failure_time:
                _API_CALL_REGISTRY[area]['last_failure'] = failure_time
        else:
            # Reset failure count on successful fetch
            _API_CALL_REGISTRY[area]['consecutive_failures'] = 0
            
    @staticmethod
    def get_registry_info(area: str) -> Dict:
        """Get rate limiting information from registry for a given area."""
        if area not in _API_CALL_REGISTRY:
            return {
                'last_fetch': None,
                'consecutive_failures': 0,
                'last_failure': None
            }
        return _API_CALL_REGISTRY[area]
    
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
        # Check registry first for most up-to-date information
        if area:
            registry_info = RateLimiter.get_registry_info(area)
            registry_last_fetch = registry_info.get('last_fetch')
            registry_failures = registry_info.get('consecutive_failures', 0)
            registry_last_failure = registry_info.get('last_failure')
            
            # Use the most recent timestamp
            if registry_last_fetch and (last_fetched is None or registry_last_fetch > last_fetched):
                _LOGGER.debug(f"Using registry last fetch time for {area}: {registry_last_fetch}")
                last_fetched = registry_last_fetch
                
            # Use the highest failure count to be safe
            consecutive_failures = max(consecutive_failures, registry_failures)
            
            # Use the most recent failure time
            if registry_last_failure and (last_failure_time is None or registry_last_failure > last_failure_time):
                last_failure_time = registry_last_failure
        
        # If never fetched, always fetch
        if last_fetched is None:
            reason = "No previous fetch"
            log_rate_limiting(area or "unknown", False, reason, source)
            # Update registry
            if area:
                RateLimiter._update_registry(area)
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
                _LOGGER.debug(f"Using source-specific interval for {source}: {min_interval} minutes")
            else:
                min_interval = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
                _LOGGER.debug(f"Using default interval: {min_interval} minutes")

        # If less than minimum fetch interval, skip
        if time_diff < min_interval:
            reason = f"Last fetch was only {time_diff:.1f} minutes ago (minimum: {min_interval} for source {source or 'unknown'})"
            log_rate_limiting(area or "unknown", True, reason, source)
            # Add more debug info to understand why the rate limiter isn't working
            _LOGGER.debug(
                f"Rate limiter enforcing skip: Source={source}, Area={area}, "
                f"Interval={min_interval}min, Last fetch: {last_fetched}, "
                f"Now: {current_time}, Diff: {time_diff}min"
            )
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
