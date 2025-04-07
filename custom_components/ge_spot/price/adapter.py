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

    def __init__(self, hass: HomeAssistant, raw_data: List[Dict], use_subunit: bool = False) -> None:
        """Initialize the price adapter."""
        self.hass = hass
        self.raw_data = raw_data or []
        self.use_subunit = use_subunit
        self.local_tz = dt_util.get_time_zone(hass.config.time_zone)
        _LOGGER.debug(f"Initializing price adapter with Home Assistant timezone: {self.local_tz}")
        _LOGGER.debug(f"Price adapter using subunit conversion: {self.use_subunit}")

        # Transform raw data format if necessary
        self.processed_raw_data = []

        # Process all available raw data formats
        self._process_raw_data()

        # Process data into periods with proper timezone handling
        self.price_periods = process_price_data(self.processed_raw_data, self.local_tz)

        # Classify periods by date (today, tomorrow, etc.)
        self.classified_periods = classify_price_periods(self.price_periods, self.hass)

        # Log first and last periods for debugging
        if self.price_periods:
            first_period = self.price_periods[0]
            last_period = self.price_periods[-1]
            _LOGGER.debug(f"First period: {first_period['start'].isoformat()} - {first_period['price']}")
            _LOGGER.debug(f"Last period: {last_period['start'].isoformat()} - {last_period['price']}")

        _LOGGER.debug(f"Created {len(self.price_periods)} price periods "
                     f"(today: {len(self.classified_periods['today'])}, "
                     f"tomorrow: {len(self.classified_periods['tomorrow'])})")

    def _process_raw_data(self):
        """Process various raw data formats into a standardized structure."""
        for item in self.raw_data:
            # Skip non-dictionary items
            if not isinstance(item, dict):
                continue

            # Extract currency information - used for subunit conversion
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
                # Parse hour string (format: "HH:00")
                hour = int(hour_str.split(":")[0])

                # Create timestamps for this hour in local time
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

        # Also check for tomorrow_hourly_prices if this data contains today's prices
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

                # Handle end time
                if "end" in entry and entry["end"]:
                    end_time = parse_datetime(entry["end"])
                else:
                    end_time = start_time + timedelta(hours=1)

                # Handle price/value field name variations
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
            # Parse timestamps if needed
            start_time = parse_datetime(item["start"]) if isinstance(item["start"], str) else item["start"]
            end_time = parse_datetime(item["end"]) if isinstance(item["end"], str) else item["end"]

            # Handle price field name variations
            price = item.get("value", item.get("price"))

            self.processed_raw_data.append({
                "start": start_time,
                "end": end_time,
                "value": price,
                "currency": currency or item.get("currency")
            })
        except Exception as e:
            _LOGGER.warning(f"Error processing price entry: {e}")

    def _get_currency(self):
        """Get the currency from the raw data."""
        # First check if any period has currency
        for period in self.price_periods:
            if "currency" in period and period["currency"]:
                return period["currency"]

        # Then check raw data
        for item in self.raw_data:
            if isinstance(item, dict) and "currency" in item and item["currency"]:
                return item["currency"]

        # Default fallback
        return "EUR"

    def get_current_price(self, reference_time: Optional[datetime] = None) -> Optional[float]:
        """Get price for the current period."""
        if reference_time is None:
            reference_time = dt_util.now()
            _LOGGER.debug(f"Using current time as reference: {reference_time.isoformat()}")

        # Use the utility function to find the current price
        price = find_current_price(self.price_periods, reference_time)

        return price

    def get_prices_for_day(self, day_offset: int = 0) -> List[Dict]:
        """Get all prices for a specific day (today + offset)."""
        if day_offset == 0:
            return self.classified_periods["today"]
        elif day_offset == 1:
            return self.classified_periods["tomorrow"]
        else:
            # For other offsets, fallback to the original method
            return get_prices_for_day(self.price_periods, day_offset, self.hass)

    def get_raw_prices_for_day(self, day_offset: int = 0) -> List[Dict]:
        """Get raw price data formatted for Home Assistant attributes."""
        day_data = self.get_prices_for_day(day_offset)
        return get_raw_prices_for_day(day_data)

    def get_today_prices(self) -> List[float]:
        """Get list of today's prices in chronological order."""
        return get_price_list(self.classified_periods["today"])

    def get_tomorrow_prices(self) -> List[float]:
        """Get list of tomorrow's prices in chronological order."""
        return get_price_list(self.classified_periods["tomorrow"])

    def get_day_statistics(self, day_offset: int = 0) -> Dict[str, Any]:
        """Calculate statistics for a particular day."""
        from ..utils.debug_utils import log_statistics

        day_data = self.get_prices_for_day(day_offset)
        stats = get_statistics(day_data)

        # Log calculation details
        log_statistics(stats, day_offset)

        return stats

    def is_tomorrow_valid(self) -> bool:
        """Check if tomorrow's data is available."""
        return len(self.classified_periods["tomorrow"]) >= 20
