"""Data processor for electricity spot prices."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..price import ElectricityPriceAdapter
from ..utils.exchange_service import get_exchange_service

_LOGGER = logging.getLogger(__name__)

class DataProcessor:
    """Processor for formatting and enriching price data."""

    def __init__(
        self,
        hass: HomeAssistant,
        area: str,
        currency: str,
        config: Dict[str, Any],
        tz_service: Any
    ):
        """Initialize the data processor.

        Args:
            hass: Home Assistant instance
            area: Area code
            currency: Currency code
            config: Configuration dictionary
            tz_service: Timezone service instance
        """
        self.hass = hass
        self.area = area
        self.currency = currency
        self.config = config
        self._tz_service = tz_service
        self._last_successful_data = None

    async def process_api_result(
        self,
        result: Dict[str, Any],
        primary_adapter: ElectricityPriceAdapter,
        fallback_adapters: Dict[str, ElectricityPriceAdapter],
        last_api_fetch: datetime,
        next_scheduled_api_fetch: datetime,
        api_key_status: Dict[str, Any],
        session: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Process API result into final format.

        Args:
            result: Result from API fetch
            primary_adapter: Primary adapter
            fallback_adapters: Fallback adapters
            last_api_fetch: Last API fetch time
            next_scheduled_api_fetch: Next scheduled API fetch time
            api_key_status: API key status
            session: Optional session for API requests

        Returns:
            Dictionary with processed data
        """
        data = result["data"]

        # Check if any adapter has valid tomorrow data
        any_adapter_has_tomorrow = primary_adapter.is_tomorrow_valid()
        for fb_adapter in fallback_adapters.values():
            if fb_adapter.is_tomorrow_valid():
                any_adapter_has_tomorrow = True
                break

        # Get exchange rate info
        try:
            exchange_service = await get_exchange_service(session)
            exchange_rate_info = exchange_service.get_exchange_rate_info("EUR", self.currency)
            ecb_rate = exchange_rate_info.get("formatted")
            ecb_updated = exchange_rate_info.get("timestamp")
        except Exception as e:
            _LOGGER.error(f"Error getting exchange rate info: {e}")
            ecb_rate = None
            ecb_updated = None

        # Build result with actual API fetch timestamp
        final_result = {
            "adapter": primary_adapter,
            "fallback_adapters": fallback_adapters,
            "current_price": primary_adapter.get_current_price(self.area, self.config),
            "next_hour_price": primary_adapter.find_next_price(self.area, self.config),
            "today_stats": primary_adapter.get_day_statistics(0),
            "tomorrow_stats": primary_adapter.get_day_statistics(1),
            "tomorrow_valid": any_adapter_has_tomorrow,
            "last_updated": dt_util.now().isoformat(),
            "last_api_fetch": last_api_fetch.isoformat(),
            "next_api_fetch": next_scheduled_api_fetch.isoformat(),
            "api_key_status": api_key_status,
            "raw_values": data.get("raw_values", {}),
            "source": result["source"],
            "active_source": result["active_source"],
            "attempted_sources": result["attempted_sources"],
            "skipped_sources": result.get("skipped_sources", []),
            "fallback_sources": result.get("fallback_sources", []),
            "fallback_used": result.get("fallback_used", False),
            "primary_source": result.get("primary_source"),
            "ecb_rate": ecb_rate,
            "ecb_updated": ecb_updated,
            "ha_timezone": str(self.hass.config.time_zone) if self.hass else None,
            "api_timezone": data.get("api_timezone"),
            "area_timezone": str(self._tz_service.area_timezone) if self._tz_service.area_timezone else None,
            "current_hour_key": self._tz_service.get_current_hour_key()
        }

        self._last_successful_data = final_result
        return final_result

    def process_cached_data(
        self,
        data: Dict[str, Any],
        last_api_fetch: Optional[datetime] = None,
        next_scheduled_api_fetch: Optional[datetime] = None,
        consecutive_failures: int = 0
    ) -> Dict[str, Any]:
        """Process cached data into consistent format.

        Args:
            data: Cached data
            last_api_fetch: Last API fetch time
            next_scheduled_api_fetch: Next scheduled API fetch time
            consecutive_failures: Number of consecutive failures

        Returns:
            Dictionary with processed data
        """
        now = dt_util.now()
        result = dict(data)

        # Add metadata
        result["last_checked"] = now.isoformat()
        result["last_updated"] = now.isoformat()  # Keep last_updated for compatibility
        result["using_cached_data"] = True
        result["error_recovery"] = True

        # Make sure we have all necessary fields
        if "current_hour_key" not in result:
            result["current_hour_key"] = self._tz_service.get_current_hour_key()

        # Include API status info
        if last_api_fetch:
            result["last_api_fetch"] = last_api_fetch.isoformat()

        if next_scheduled_api_fetch:
            result["next_api_fetch"] = next_scheduled_api_fetch.isoformat()
        else:
            # Schedule next fetch after a backoff period
            backoff = min(60, 5 * (2 ** min(consecutive_failures - 1, 3)))  # Exponential backoff
            next_fetch = now + timedelta(minutes=backoff)
            result["next_api_fetch"] = next_fetch.isoformat()

        return result

    def get_last_successful_data(self) -> Optional[Dict[str, Any]]:
        """Get last successful data.

        Returns:
            Dictionary with last successful data, or None if not available
        """
        return self._last_successful_data
