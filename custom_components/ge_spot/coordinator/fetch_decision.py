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
        has_current_hour_price: bool,
        # Add the new parameter
        has_complete_data_for_today: bool
    ) -> Tuple[bool, str]:
        """Determine if we need to fetch from API.

        Args:
            now: Current datetime
            last_fetch: Last API fetch time
            fetch_interval: API fetch interval in minutes
            has_current_hour_price: Whether cache has current hour price
            has_complete_data_for_today: Whether cache has complete data for today (20+ hours)

        Returns:
            Tuple of (need_api_fetch, reason)
        """
        need_api_fetch = False
        reason = ""

        # Check special time windows first
        hour = now.hour
        for start_hour, end_hour in Network.Defaults.SPECIAL_HOUR_WINDOWS:
            if start_hour <= hour < end_hour:
                # During special windows, only fetch if we don't have data for the current hour
                if not has_current_hour_price:
                    reason = f"Special time window ({start_hour}-{end_hour}), no data for current hour, fetching from API"
                    _LOGGER.info(reason)
                    need_api_fetch = True
                    break
                else:
                    # We have current hour data, no need to fetch during special window
                    reason = f"Special time window ({start_hour}-{end_hour}), but we already have current hour data, skipping"
                    _LOGGER.debug(reason)
                    return False, reason

        # Use the rate limiter to make the decision
        from ..utils.rate_limiter import RateLimiter
        should_skip, skip_reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetch,
            current_time=now,
            min_interval=fetch_interval
        )

        # If rate limiter says skip, and we have current hour data, definitely skip.
        if should_skip and has_current_hour_price:
            reason = f"Rate limiter suggests skipping fetch: {skip_reason}"
            _LOGGER.debug(reason)
            return False, reason

        # If we have complete data for today, don't fetch unless forced by other critical reasons.
        if has_complete_data_for_today:
            reason = "Valid processed data for the complete_data period (20+ hours) exists. Fetch not needed based on this rule."
            _LOGGER.debug(reason)
            # This condition should take precedence unless other critical flags are set.
            # We will re-evaluate need_api_fetch at the end based on critical needs like no current_hour_price.
        else:
            # If we don't have complete data, this is a reason to fetch.
            reason = "Complete_data quota (20+ hours) not met for today. Fetching new data."
            _LOGGER.info(reason)
            need_api_fetch = True

        # Check if API fetch interval has passed
        if not need_api_fetch and last_fetch:
            time_since_fetch = (now - last_fetch).total_seconds() / 60
            if time_since_fetch >= fetch_interval:
                if not has_current_hour_price:
                    reason = (
                        f"API fetch interval ({fetch_interval} minutes) passed "
                        f"and no current_hour_price, fetching new data"
                    )
                    _LOGGER.info(reason)
                    need_api_fetch = True
                elif has_current_hour_price: # Log when interval passed but we have current hour data
                    reason = (
                        f"API fetch interval ({fetch_interval} minutes) passed, "
                        f"but current_hour_price is available. "
                        f"Fetch not triggered by this specific interval rule."
                    )
                    _LOGGER.debug(reason)

        # If we've never fetched, we need to fetch
        if not need_api_fetch and not last_fetch:
            reason = "Initial startup or forced refresh, fetching from API"
            _LOGGER.info(reason)
            need_api_fetch = True

        # If we have no cached data for the current hour, this is a critical reason to fetch.
        if not has_current_hour_price:
            current_hour_key = self._tz_service.get_current_hour_key()
            reason = f"No cached data for current hour {current_hour_key}, fetching from API (overrides complete_data check if necessary)"
            _LOGGER.info(reason)
            need_api_fetch = True
        # If we decided to fetch because complete_data quota was not met, but we DO have current hour price,
        # and the rate limiter didn't say to skip, then proceed with the fetch.
        elif need_api_fetch and has_current_hour_price:
            _LOGGER.debug(
                "Proceeding with fetch because complete_data quota not met, even though current hour price is available."
            )

        return need_api_fetch, reason
