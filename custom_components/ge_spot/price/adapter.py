"""Price data adapter for electricity spot prices."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..timezone import (
    parse_datetime,
    localize_datetime,
    find_current_price,
    find_current_price_period,
    process_price_data,
    get_prices_for_day,
    get_raw_prices_for_day,
    get_price_list,
    classify_price_periods,
)
from .currency import convert_to_subunit
from .statistics import get_statistics

_LOGGER = logging.getLogger(__name__)

class ElectricityPriceAdapter:
    """A robust adapter for electricity price data with proper timezone handling."""

    def __init__(self, hass: HomeAssistant, raw_data: List[Dict], use_subunit: bool = False, using_cached_data: bool = False) -> None:
        """Initialize the price adapter."""
        self.hass = hass
        self.raw_data = raw_data or []
        self.use_subunit = use_subunit
        self.using_cached_data = using_cached_data
        self.local_tz = dt_util.get_time_zone(hass.config.time_zone)
        
        # Initialize empty structures
        self.processed_raw_data = []
        self.price_periods = []
        self.classified_periods = {
            "today": [],
            "tomorrow": []
        }

        _LOGGER.debug(f"Initializing price adapter (cached: {using_cached_data}, subunit: {use_subunit})")

        # Skip processing if using cached data
        if not using_cached_data:
            self._process_raw_data()
            self.price_periods = process_price_data(self.processed_raw_data, self.local_tz)
            self.classified_periods = classify_price_periods(self.price_periods, self.hass)
            
            if self.price_periods:
                _LOGGER.debug(f"Created {len(self.price_periods)} price periods "
                            f"(today: {len(self.classified_periods['today'])}, "
                            f"tomorrow: {len(self.classified_periods['tomorrow'])})")

    def _process_raw_data(self):
        """Process various raw data formats into a standardized structure."""
        if self.using_cached_data:
            return
            
        for item in self.raw_data:
            if not isinstance(item, dict):
                continue

            # Extract currency information
            currency = item.get("currency")

            # Handle API response with hourly_prices dictionary
            if "hourly_prices" in item:
                self._process_hourly_prices(item, currency)

            # Process raw_today entries
            if "raw_today" in item:
                self._process_raw_prices(item.get("raw_today", []), currency)

            # Process raw_tomorrow entries if available
            if "raw_tomorrow" in item:
                self._process_raw_prices(item.get("raw_tomorrow", []), currency)

            # Process direct price entry format
            elif all(key in item for key in ["start", "end", "value"]) or all(key in item for key in ["start", "end", "price"]):
                self._process_direct_entry(item, currency)

    def _process_hourly_prices(self, item, currency=None):
        """Process hourly_prices dictionary format."""
        current_date = dt_util.now().date()
        tomorrow_date = current_date + timedelta(days=1)

        # Determine if this item contains today's or tomorrow's prices
        is_tomorrow = "tomorrow" in item or "tomorrow_hourly_prices" in item or item.get("tomorrow_valid", False)
        base_date = tomorrow_date if is_tomorrow else current_date

        # Process hourly prices
        for hour_str, price in item.get("hourly_prices", {}).items():
            try:
                hour = int(hour_str.split(":")[0])
                start_time = dt_util.as_local(dt_util.start_of_local_day(base_date))
                start_time = start_time.replace(hour=hour)
                end_time = start_time + timedelta(hours=1)

                self.processed_raw_data.append({
                    "start": start_time,
                    "end": end_time,
                    "value": price,
                    "currency": currency or item.get("currency")
                })
            except Exception as e:
                _LOGGER.warning(f"Error processing hourly price {hour_str}: {e}")

        # Also check for tomorrow_hourly_prices
        if not is_tomorrow and "tomorrow_hourly_prices" in item:
            for hour_str, price in item.get("tomorrow_hourly_prices", {}).items():
                try:
                    hour = int(hour_str.split(":")[0])
                    start_time = dt_util.as_local(dt_util.start_of_local_day(tomorrow_date))
                    start_time = start_time.replace(hour=hour)
                    end_time = start_time + timedelta(hours=1)

                    self.processed_raw_data.append({
                        "start": start_time,
                        "end": end_time,
                        "value": price,
                        "currency": currency or item.get("currency")
                    })
                except Exception as e:
                    _LOGGER.warning(f"Error processing tomorrow hourly price {hour_str}: {e}")

    def _process_raw_prices(self, entries, currency=None):
        """Process raw_prices entries."""
        for entry in entries:
            if isinstance(entry, dict) and "start" in entry and ("price" in entry or "value" in entry):
                start_time = parse_datetime(entry["start"])
                end_time = parse_datetime(entry["end"]) if "end" in entry and entry["end"] else start_time + timedelta(hours=1)
                price = entry.get("price") if "price" in entry else entry.get("value")

                self.processed_raw_data.append({
                    "start": start_time,
                    "end": end_time,
                    "value": price,
                    "currency": currency or entry.get("currency")
                })

    def _process_direct_entry(self, item, currency=None):
        """Process entries already in start/end/value format."""
        try:
            start_time = parse_datetime(item["start"]) if isinstance(item["start"], str) else item["start"]
            end_time = parse_datetime(item["end"]) if isinstance(item["end"], str) else item["end"]
            price = item.get("value", item.get("price"))

            self.processed_raw_data.append({
                "start": start_time,
                "end": end_time,
                "value": price,
                "currency": currency or item.get("currency")
            })
        except Exception as e:
            _LOGGER.warning(f"Error processing price entry: {e}")

    def get_current_price(self, reference_time: Optional[datetime] = None) -> Optional[float]:
        """Get price for the current period."""
        # For cached data, access directly from the raw_data
        if self.using_cached_data and self.raw_data and isinstance(self.raw_data[0], dict):
            return self.raw_data[0].get("current_price")
            
        # Otherwise use the utility function
        return find_current_price(self.price_periods, reference_time)

    def get_prices_for_day(self, day_offset: int = 0) -> List[Dict]:
        """Get all prices for a specific day (today + offset)."""
        # For cached data, use the data directly
        if self.using_cached_data and self.raw_data:
            if day_offset == 0 and "today" in self.raw_data[0]:
                return self.raw_data[0]["today"]
            elif day_offset == 1 and "tomorrow" in self.raw_data[0]:
                return self.raw_data[0]["tomorrow"]

        # Otherwise use the classified periods
        if day_offset == 0:
            return self.classified_periods["today"]
        elif day_offset == 1:
            return self.classified_periods["tomorrow"]
        else:
            return get_prices_for_day(self.price_periods, day_offset, self.hass)

    def get_raw_prices_for_day(self, day_offset: int = 0) -> List[Dict]:
        """Get raw price data formatted for Home Assistant attributes."""
        day_data = self.get_prices_for_day(day_offset)
        return get_raw_prices_for_day(day_data)

    def get_today_prices(self) -> List[float]:
        """Get list of today's prices in chronological order."""
        # For cached data, directly return the stored list
        if self.using_cached_data and self.raw_data:
            if "today" in self.raw_data[0]:
                return self.raw_data[0]["today"]
        
        return get_price_list(self.classified_periods["today"])

    def get_tomorrow_prices(self) -> List[float]:
        """Get list of tomorrow's prices in chronological order."""
        # For cached data, directly return the stored list
        if self.using_cached_data and self.raw_data:
            if "tomorrow" in self.raw_data[0]:
                return self.raw_data[0]["tomorrow"]
            
        return get_price_list(self.classified_periods["tomorrow"])

    def get_day_statistics(self, day_offset: int = 0) -> Dict[str, Any]:
        """Calculate statistics for a particular day."""
        # For cached data, use the stored statistics
        if self.using_cached_data and self.raw_data:
            if day_offset == 0 and "today_stats" in self.raw_data[0]:
                return self.raw_data[0]["today_stats"]
            elif day_offset == 1 and "tomorrow_stats" in self.raw_data[0]:
                return self.raw_data[0]["tomorrow_stats"]

        # Otherwise calculate statistics
        day_data = self.get_prices_for_day(day_offset)
        return get_statistics(day_data)

    def is_tomorrow_valid(self) -> bool:
        """Check if tomorrow's data is available."""
        # For cached data, use the stored flag
        if self.using_cached_data and self.raw_data:
            return self.raw_data[0].get("tomorrow_valid", False)
            
        return len(self.classified_periods["tomorrow"]) >= 20
