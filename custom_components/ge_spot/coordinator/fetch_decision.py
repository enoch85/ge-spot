"""Decision maker for when to fetch new data."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List, Tuple

from homeassistant.util import dt as dt_util

from ..const.network import Network

_LOGGER = logging.getLogger(__name__)

class FetchDecisionMaker:
    """Decision maker for when to fetch new data."""

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
        fetch_interval: int,
        has_current_hour_price: bool
    ) -> Tuple[bool, str]:
        """Determine if we need to fetch from API.

        Args:
            now: Current datetime
            last_fetch: Last API fetch time
            fetch_interval: API fetch interval in minutes
            has_current_hour_price: Whether cache has current hour price

        Returns:
            Tuple of (need_api_fetch, reason)
        """
        need_api_fetch = False
        reason = ""

        # Check special time windows first
        hour = now.hour
        for start_hour, end_hour in Network.Defaults.SPECIAL_HOUR_WINDOWS:
            if start_hour <= hour < end_hour:
                # During special windows, only fetch if:
                # 1. We don't have data for the current hour, or
                # 2. It's been at least 30 seconds since the last fetch
                if not has_current_hour_price:
                    reason = f"Special time window ({start_hour}-{end_hour}), no data for current hour, fetching from API"
                    _LOGGER.info(reason)
                    need_api_fetch = True
                    break
                elif last_fetch:
                    time_since_fetch = (now - last_fetch).total_seconds()
                    if time_since_fetch >= 30:  # Only fetch every 30 seconds during special hours
                        reason = f"Special time window ({start_hour}-{end_hour}), {time_since_fetch:.1f}s since last fetch, fetching from API"
                        _LOGGER.info(reason)
                        need_api_fetch = True
                        break
                    else:
                        # We have current hour data and fetched recently, skip this fetch
                        reason = f"Special time window ({start_hour}-{end_hour}), but fetched {time_since_fetch:.1f}s ago, skipping"
                        _LOGGER.debug(reason)
                else:
                    # No last_fetch time but we have current hour data (unlikely)
                    reason = f"Special time window ({start_hour}-{end_hour}), forcing API update (no last fetch time)"
                    _LOGGER.info(reason)
                    need_api_fetch = True
                    break

        # Check if API fetch interval has passed
        if not need_api_fetch and last_fetch:
            time_since_fetch = (now - last_fetch).total_seconds() / 60
            if time_since_fetch >= fetch_interval:
                reason = f"API fetch interval ({fetch_interval} minutes) passed, fetching new data"
                _LOGGER.info(reason)
                need_api_fetch = True

        # If we've never fetched, we need to fetch
        if not need_api_fetch and not last_fetch:
            reason = "Initial startup or forced refresh, fetching from API"
            _LOGGER.info(reason)
            need_api_fetch = True

        # If we have no cached data for the current hour, we need to fetch
        if not need_api_fetch and not has_current_hour_price:
            current_hour_key = self._tz_service.get_current_hour_key()
            reason = f"No cached data for current hour {current_hour_key}, fetching from API"
            _LOGGER.info(reason)
            need_api_fetch = True

        return need_api_fetch, reason
