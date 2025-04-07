"""API module for Nordpool."""
import logging
import datetime
from .base import BaseEnergyAPI
from ..timezone import parse_datetime, localize_datetime
from ..const import (
    NORDPOOL_DELIVERY_AREA_MAPPING,
)

_LOGGER = logging.getLogger(__name__)

class NordpoolAPI(BaseEnergyAPI):
    """API handler for Nordpool."""

    BASE_URL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"

    async def _fetch_data(self):
        """Fetch data from Nordpool."""
        try:
            now = self._get_now()
            _LOGGER.debug(f"Current local time from _get_now: {now.isoformat()}")

            today = now.strftime("%Y-%m-%d")
            tomorrow = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

            area = self.config.get("area", "Oslo")

            # Map the area names to the API's delivery area codes
            delivery_area = NORDPOOL_DELIVERY_AREA_MAPPING.get(area, area)
            _LOGGER.debug(f"Fetching Nordpool data for area: {delivery_area}")

            # Fetch today's data
            params = {
                "currency": "EUR",  # Always request in EUR, we'll convert later
                "date": today,
                "market": "DayAhead",
                "deliveryArea": delivery_area
            }

            today_data = await self.data_fetcher.fetch_with_retry(self.BASE_URL, params=params)

            if today_data is None:
                _LOGGER.error(f"Failed to fetch today's data for {delivery_area}")
                return None

            # Fetch tomorrow's data if after 13:00 CET
            tomorrow_data = None
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_cet = now_utc.astimezone(datetime.timezone(datetime.timedelta(hours=1)))

            if now_cet.hour >= 13:
                params["date"] = tomorrow
                tomorrow_data = await self.data_fetcher.fetch_with_retry(self.BASE_URL, params=params)

            return {
                "today": today_data,
                "tomorrow": tomorrow_data,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

        except Exception as e:
            _LOGGER.error(f"Error in _fetch_data: {str(e)}", exc_info=True)
            return None

    async def _process_data(self, raw_data):
        """Process the data from Nordpool."""
        if not raw_data or "today" not in raw_data:
            return None

        today_data = raw_data["today"]
        tomorrow_data = raw_data.get("tomorrow")

        if "multiAreaEntries" not in today_data:
            _LOGGER.error("Missing multiAreaEntries in Nordpool data")
            return None

        area = self.config.get("area", "Oslo")

        # Get current time from Home Assistant in local timezone
        now = self._get_now()
        current_hour = now.hour
        _LOGGER.debug(f"Current local time: {now.isoformat()}, hour: {current_hour}")

        # Dictionary to store results
        result = {
            "current_price": None,
            "next_hour_price": None,
            "day_average_price": None,
            "peak_price": None,
            "off_peak_price": None,
            "hourly_prices": {},
            "last_updated": raw_data.get("timestamp"),
            "raw_today": [],
            "raw_tomorrow": [],
            "raw_values": {},
            "currency": self._currency
        }

        # Extract exchange rate if available
        exchange_rate = None
        if "exchangeRate" in today_data:
            try:
                exchange_rate = float(today_data["exchangeRate"])
                _LOGGER.debug(f"Using exchange rate from API: {exchange_rate}")
            except (ValueError, TypeError):
                _LOGGER.warning(f"Invalid exchange rate in API data: {today_data.get('exchangeRate')}")

        # Process today's data
        entries = today_data.get("multiAreaEntries", [])
        all_prices = []

        for entry in entries:
            if not isinstance(entry, dict) or "entryPerArea" not in entry:
                continue

            if area not in entry["entryPerArea"]:
                continue

            # Extract values
            start_time = entry.get("deliveryStart")
            end_time = entry.get("deliveryEnd")
            raw_price = entry["entryPerArea"][area]

            # Store in raw data
            result["raw_today"].append({
                "start": start_time,
                "end": end_time,
                "price": raw_price
            })

            # Convert to float if needed
            if isinstance(raw_price, str):
                try:
                    raw_price = float(raw_price)
                except (ValueError, TypeError):
                    continue

            try:
                # Parse the datetime correctly without timezone assumptions
                dt = parse_datetime(start_time)

                # Debug the timestamps to check timezone handling
                _LOGGER.debug(f"Original timestamp: {start_time}, Parsed: {dt.isoformat()}")

                # Convert to HA's local timezone
                local_dt = dt
                if hasattr(self, "hass") and self.hass:
                    local_dt = localize_datetime(dt, self.hass)
                    _LOGGER.debug(f"Localized using HA timezone: {local_dt.isoformat()}")
                else:
                    from homeassistant.util import dt as dt_util
                    local_dt = dt.astimezone(dt_util.DEFAULT_TIME_ZONE)
                    _LOGGER.debug(f"Localized using default timezone: {local_dt.isoformat()}")

                # Convert price using the centralized method
                converted_price = await self._convert_price(
                    price=raw_price,
                    from_currency="EUR",
                    exchange_rate=exchange_rate
                )

                # Store in hourly prices using local hour
                hour = local_dt.hour
                hour_str = f"{hour:02d}:00"
                result["hourly_prices"][hour_str] = converted_price
                all_prices.append(converted_price)

                # Check if this is current hour based on local time comparison
                if hour == current_hour:
                    result["current_price"] = converted_price
                    _LOGGER.debug(f"Found current hour price ({hour_str}): {converted_price}")
                    # Store raw value information with detailed timestamp info
                    result["raw_values"]["current_price"] = {
                        "raw": raw_price,
                        "unit": "EUR/MWh",
                        "converted": converted_price,
                        "hour_str": hour_str,
                        "local_hour": hour,
                        "api_timestamp": start_time,
                        "local_time": local_dt.isoformat(),
                        "exchange_rate": exchange_rate
                    }

                # Check if this is next hour
                elif hour == (current_hour + 1) % 24:
                    result["next_hour_price"] = converted_price
                    _LOGGER.debug(f"Found next hour price ({hour_str}): {converted_price}")
                    # Store raw value information
                    result["raw_values"]["next_hour_price"] = {
                        "raw": raw_price,
                        "unit": "EUR/MWh",
                        "converted": converted_price,
                        "hour_str": hour_str,
                        "local_hour": hour,
                        "api_timestamp": start_time,
                        "local_time": local_dt.isoformat(),
                        "exchange_rate": exchange_rate
                    }
            except (ValueError, TypeError) as e:
                _LOGGER.error(f"Error processing timestamp {start_time}: {e}")
                continue

        # Calculate statistics
        if all_prices:
            result["day_average_price"] = sum(all_prices) / len(all_prices)
            result["peak_price"] = max(all_prices)
            result["off_peak_price"] = min(all_prices)

            # Store raw value information for statistics
            result["raw_values"]["day_average_price"] = {
                "value": result["day_average_price"],
                "calculation": "average of all hourly prices"
            }
            result["raw_values"]["peak_price"] = {
                "value": result["peak_price"],
                "calculation": "maximum of all hourly prices"
            }
            result["raw_values"]["off_peak_price"] = {
                "value": result["off_peak_price"],
                "calculation": "minimum of all hourly prices"
            }

        # Process tomorrow's data if available
        if tomorrow_data and "multiAreaEntries" in tomorrow_data:
            tomorrow_entries = tomorrow_data.get("multiAreaEntries", [])
            tomorrow_prices = []
            result["tomorrow_hourly_prices"] = {}

            # Extract exchange rate for tomorrow if available
            tomorrow_exchange_rate = None
            if "exchangeRate" in tomorrow_data:
                try:
                    tomorrow_exchange_rate = float(tomorrow_data["exchangeRate"])
                    _LOGGER.debug(f"Using exchange rate from API for tomorrow: {tomorrow_exchange_rate}")
                except (ValueError, TypeError):
                    _LOGGER.warning(f"Invalid exchange rate in API data for tomorrow: {tomorrow_data.get('exchangeRate')}")
                    tomorrow_exchange_rate = exchange_rate  # Fallback to today's rate

            for entry in tomorrow_entries:
                if not isinstance(entry, dict) or "entryPerArea" not in entry:
                    continue

                if area not in entry["entryPerArea"]:
                    continue

                # Extract values
                start_time = entry.get("deliveryStart")
                end_time = entry.get("deliveryEnd")
                raw_price = entry["entryPerArea"][area]

                # Store in raw data
                result["raw_tomorrow"].append({
                    "start": start_time,
                    "end": end_time,
                    "price": raw_price
                })

                # Convert to float if needed
                if isinstance(raw_price, str):
                    try:
                        raw_price = float(raw_price)
                    except (ValueError, TypeError):
                        continue

                try:
                    # Parse the datetime correctly
                    dt = parse_datetime(start_time)

                    # Convert to local time
                    local_dt = dt
                    if hasattr(self, "hass") and self.hass:
                        local_dt = localize_datetime(dt, self.hass)
                    else:
                        from homeassistant.util import dt as dt_util
                        local_dt = dt.astimezone(dt_util.DEFAULT_TIME_ZONE)

                    # Convert price using the centralized method
                    converted_price = await self._convert_price(
                        price=raw_price,
                        from_currency="EUR",
                        exchange_rate=tomorrow_exchange_rate
                    )

                    # Store in hourly prices using local hour
                    hour = local_dt.hour
                    hour_str = f"{hour:02d}:00"
                    result["tomorrow_hourly_prices"][hour_str] = converted_price
                    tomorrow_prices.append(converted_price)

                except (ValueError, TypeError) as e:
                    _LOGGER.error(f"Error processing tomorrow timestamp {start_time}: {e}")
                    continue

            # Calculate tomorrow statistics
            if tomorrow_prices:
                result["tomorrow_average_price"] = sum(tomorrow_prices) / len(tomorrow_prices)
                result["tomorrow_peak_price"] = max(tomorrow_prices)
                result["tomorrow_off_peak_price"] = min(tomorrow_prices)
                result["tomorrow_valid"] = len(tomorrow_prices) >= 20  # At least 20 hours

                # Store raw values for tomorrow
                result["raw_values"]["tomorrow_average_price"] = {
                    "value": result["tomorrow_average_price"],
                    "calculation": "average of all tomorrow's prices"
                }
                result["raw_values"]["tomorrow_peak_price"] = {
                    "value": result["tomorrow_peak_price"],
                    "calculation": "maximum of all tomorrow's prices"
                }
                result["raw_values"]["tomorrow_off_peak_price"] = {
                    "value": result["tomorrow_off_peak_price"],
                    "calculation": "minimum of all tomorrow's prices"
                }

        # Include meta-information
        from homeassistant.util import dt as dt_util
        result["state_class"] = "total"
        result["vat"] = self.vat
        result["data_source"] = "NordpoolAPI"
        result["timezone"] = str(dt_util.DEFAULT_TIME_ZONE)

        return result
