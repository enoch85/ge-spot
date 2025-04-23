"""Data processor for electricity spot prices."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..price import ElectricityPriceAdapter
from ..utils.exchange_service import get_exchange_service
from ..timezone.source_tz import get_source_timezone

_LOGGER = logging.getLogger(__name__)

# NOTE: All API modules should return raw, unprocessed data in this standardized format:
# {
#     "hourly_prices": {"HH:00" or ISO: price, ...},
#     "currency": str,
#     "timezone": str,
#     "area": str,
#     "raw_data": dict (original API response),
#     "source": str,
#     "last_updated": ISO8601 str,
#     ...
# }
# All timezone, currency, and statistics logic must be handled here or in the adapter, not in the API modules.
# TODO: Refactor all remaining API modules to follow this pattern for consistency and maintainability.

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

    def process(self, data: Dict[str, Any], source: str) -> Dict[str, Any]:
        """Process data from the simplified fallback mechanism.
        
        Args:
            data: Raw data from API
            source: Source identifier
            
        Returns:
            Dictionary with processed data
            
        Raises:
            ValueError: If required timezone information cannot be determined
        """
        # Ensure we don't double-convert timezones
        # If the data already has timezone info, use it as is
        has_timezone_info = (
            data.get("api_timezone") is not None or 
            data.get("area_timezone") is not None or
            data.get("ha_timezone") is not None
        )
        
        if not has_timezone_info:
            # First try to extract timezone from the API response
            api_timezone = None
            
            # Check common timezone fields in the API response
            timezone_fields = ["timezone", "tz", "time_zone", "api_timezone"]
            for field in timezone_fields:
                if field in data and data[field]:
                    api_timezone = data[field]
                    _LOGGER.debug(f"Extracted timezone {api_timezone} from API response field '{field}'")
                    break
            
            # If we couldn't extract from the API, fall back to the source's predefined timezone
            if not api_timezone:
                api_timezone = get_source_timezone(source)
                if api_timezone:
                    _LOGGER.debug(f"Using predefined timezone {api_timezone} for source {source}")
                else:
                    error_msg = f"Cannot determine timezone for source {source}. Processing aborted."
                    _LOGGER.error(error_msg)
                    raise ValueError(error_msg)
            
            # Set the API timezone
            data["api_timezone"] = api_timezone
            
            # Set HA timezone - must have valid timezone
            if not self.hass or not self.hass.config.time_zone:
                error_msg = "Home Assistant timezone not available. Processing aborted."
                _LOGGER.error(error_msg)
                raise ValueError(error_msg)
            
            data["ha_timezone"] = str(self.hass.config.time_zone)
            
            # Set area timezone - must have valid timezone if area is set
            if self.area and not self._tz_service.area_timezone:
                error_msg = f"Area timezone not available for {self.area}. Processing aborted."
                _LOGGER.error(error_msg)
                raise ValueError(error_msg)
            elif self._tz_service.area_timezone:
                data["area_timezone"] = str(self._tz_service.area_timezone)
            
            # Log timezone info for debugging
            _LOGGER.debug(f"Added timezone info for {self.area}: API={data['api_timezone']}, Area={data.get('area_timezone')}, HA={data['ha_timezone']}")
        else:
            # Skip any additional timezone conversion to avoid double-conversion
            _LOGGER.debug(f"Using existing timezone info for {self.area}: {data.get('api_timezone', 'unknown')} -> {data.get('area_timezone', data.get('ha_timezone', 'unknown'))}")
        
        # Ensure current_price and next_hour_price are set
        if "current_price" not in data or "next_hour_price" not in data:
            # Calculate current and next hour prices
            current_hour_key = self._tz_service.get_current_hour_key()
            next_hour_key = self._tz_service.get_next_hour_key()
            
            if "hourly_prices" in data and current_hour_key in data["hourly_prices"]:
                data["current_price"] = data["hourly_prices"][current_hour_key]
                _LOGGER.debug(f"Set current_price to {data['current_price']} for hour {current_hour_key}")
            else:
                error_msg = f"Cannot find current price for hour {current_hour_key} in hourly_prices"
                _LOGGER.error(error_msg)
                if "hourly_prices" in data:
                    _LOGGER.error(f"Available hours: {list(data['hourly_prices'].keys())}")
                raise ValueError(error_msg)
            
            if "hourly_prices" in data and next_hour_key in data["hourly_prices"]:
                data["next_hour_price"] = data["hourly_prices"][next_hour_key]
                _LOGGER.debug(f"Set next_hour_price to {data['next_hour_price']} for hour {next_hour_key}")
            else:
                error_msg = f"Cannot find next hour price for hour {next_hour_key} in hourly_prices"
                _LOGGER.error(error_msg)
                raise ValueError(error_msg)
        
        # Add/update metadata
        now = dt_util.now()
        data["last_updated"] = now.isoformat()
        data["source"] = source
        data["area"] = self.area
        data["currency"] = data.get("currency", self.currency)
        data["current_hour_key"] = self._tz_service.get_current_hour_key()
        
        # Calculate missing statistics if needed
        if "today_stats" not in data and "hourly_prices" in data:
            today_range = self._tz_service.get_today_range()
            data["today_stats"] = self._calculate_statistics(data["hourly_prices"], today_range)
            _LOGGER.debug(f"Calculated today_stats for range {today_range[0]} to {today_range[-1]}")
        
        if "tomorrow_stats" not in data and "tomorrow_hourly_prices" in data:
            tomorrow_range = self._tz_service.get_tomorrow_range()
            data["tomorrow_stats"] = self._calculate_statistics(data["tomorrow_hourly_prices"], tomorrow_range)
            _LOGGER.debug(f"Calculated tomorrow_stats for range {tomorrow_range[0]} to {tomorrow_range[-1]}")
        
        # Cache this as last successful data
        self._last_successful_data = data
        
        return data
    
    def _calculate_statistics(self, hourly_prices: Dict[str, float], date_range: List[str]) -> Dict[str, Any]:
        """Calculate statistics for a set of hourly prices.
        
        Args:
            hourly_prices: Dictionary mapping hour keys to prices
            date_range: List of hour keys to include
            
        Returns:
            Dictionary with statistics
        """
        # Filter prices to the given range
        prices = [hourly_prices.get(hour) for hour in date_range if hour in hourly_prices]
        
        if not prices:
            return {
                "min": None,
                "max": None,
                "average": None,
                "median": None,
                "off_peak_1": None,
                "off_peak_2": None,
                "peak": None,
                "current": None
            }
        
        # Calculate basic statistics
        try:
            min_price = min(prices)
            max_price = max(prices)
            avg_price = sum(prices) / len(prices)
            
            # Calculate median
            sorted_prices = sorted(prices)
            mid = len(sorted_prices) // 2
            median_price = sorted_prices[mid] if len(sorted_prices) % 2 == 1 else (sorted_prices[mid-1] + sorted_prices[mid]) / 2
            
            # Get current price if available
            current_hour_key = self._tz_service.get_current_hour_key()
            current_price = hourly_prices.get(current_hour_key)
            
            # Calculate peak/off-peak if possible
            peak_hours = list(range(6, 22))  # 06:00-22:00, adjust as needed
            off_peak_1 = list(range(0, 6))   # 00:00-06:00
            off_peak_2 = list(range(22, 24)) # 22:00-00:00
            
            # Get prices for each period, filtering out missing hours
            peak_prices = []
            off_peak_1_prices = []
            off_peak_2_prices = []
            
            for hour_key in date_range:
                if hour_key in hourly_prices:
                    hour = int(hour_key.split(":")[0])
                    if hour in peak_hours:
                        peak_prices.append(hourly_prices[hour_key])
                    elif hour in off_peak_1:
                        off_peak_1_prices.append(hourly_prices[hour_key])
                    elif hour in off_peak_2:
                        off_peak_2_prices.append(hourly_prices[hour_key])
            
            # Calculate averages for each period
            peak_avg = sum(peak_prices) / len(peak_prices) if peak_prices else None
            off_peak_1_avg = sum(off_peak_1_prices) / len(off_peak_1_prices) if off_peak_1_prices else None
            off_peak_2_avg = sum(off_peak_2_prices) / len(off_peak_2_prices) if off_peak_2_prices else None
            
            return {
                "min": min_price,
                "max": max_price,
                "average": avg_price,
                "median": median_price,
                "off_peak_1": off_peak_1_avg,
                "off_peak_2": off_peak_2_avg,
                "peak": peak_avg,
                "current": current_price
            }
        except Exception as e:
            _LOGGER.error(f"Error calculating statistics: {e}")
            return {
                "min": None,
                "max": None,
                "average": None,
                "median": None,
                "off_peak_1": None,
                "off_peak_2": None,
                "peak": None,
                "current": None,
                "error": str(e)
            }
