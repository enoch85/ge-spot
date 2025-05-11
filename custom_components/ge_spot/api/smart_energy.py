import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, cast
from zoneinfo import ZoneInfo

import aiohttp

from custom_components.ge_spot.api.base_adapter import BaseAPIAdapter, PriceData
from custom_components.ge_spot.api.registry import register_adapter
from custom_components.ge_spot.const import (
    API_RESPONSE_PRICE,
    API_RESPONSE_START_TIME,
    CURRENCY_EUR,
    NETWORK_TIMEOUT,
)
from custom_components.ge_spot.const.sources import SOURCE_SMART_ENERGY
from custom_components.ge_spot.utils.network import async_get_json_or_raise
from custom_components.ge_spot.utils.time import parse_iso_datetime_with_fallback

_LOGGER = logging.getLogger(__name__)

SMART_ENERGY_API_URL = "https://apis.smartenergy.at/market/v1/price"

# smartENERGY API seems to be specific to Austria ("at")
# and returns prices in Euro Cents / kWh including 20% Austrian VAT.
# The API also returns an "interval" field (e.g., 15 minutes).
# GE-Spot needs hourly prices, so these will need to be averaged if interval is sub-hourly.
SMART_ENERGY_MARKET_CONFIG = {
    "AT": {"currency": CURRENCY_EUR, "timezone_hint": "Europe/Vienna", "vat_rate": 0.20}
}

@register_adapter(
    name=SOURCE_SMART_ENERGY,
    regions=list(SMART_ENERGY_MARKET_CONFIG.keys()),
    default_priority=75, # Adjust as needed
)
class SmartEnergyAdapter(BaseAPIAdapter):
    """
    Adapter for the smartENERGY API (apis.smartenergy.at).
    Fetches market prices, typically for Austria.
    Handles potential sub-hourly data by averaging to hourly prices.
    Removes VAT from prices as GE-Spot handles VAT application later.
    """

    def __init__(self, hass, api_key_manager, source_name: str, market_area: str, session: aiohttp.ClientSession, **kwargs):
        super().__init__(hass, api_key_manager, source_name, market_area, session, **kwargs)
        self._market_config = SMART_ENERGY_MARKET_CONFIG.get(self.market_area.upper())
        if not self._market_config:
            # This case should ideally not be hit if registration is correct
            _LOGGER.error(
                f"smartENERGY adapter configured for unsupported market area {self.market_area}. "
                f"Supported: {list(SMART_ENERGY_MARKET_CONFIG.keys())}"
            )
            # Fallback to a generic config to avoid crashing, though fetching will likely fail or be incorrect
            self._market_config = {"currency": CURRENCY_EUR, "timezone_hint": "UTC", "vat_rate": 0.0}

    async def async_fetch_data(self, target_datetime: datetime) -> PriceData:
        """
        Fetches smartENERGY data.
        The API returns current and future prices. Target_datetime is for context.
        """
        if not self._market_config or self.market_area.upper() not in SMART_ENERGY_MARKET_CONFIG:
            # Logged in init, but double check to prevent issues if init logic changes
            return PriceData(hourly_raw=[], timezone="UTC", currency=CURRENCY_EUR, source=self.source_name, meta={"error": f"Market area {self.market_area} not supported by smartENERGY adapter"})

        _LOGGER.debug("Fetching smartENERGY data for area %s from %s", self.market_area, SMART_ENERGY_API_URL)

        raw_response_preview = None
        try:
            json_response = await async_get_json_or_raise(self._session, SMART_ENERGY_API_URL, timeout=NETWORK_TIMEOUT)
            raw_response_preview = str(json_response)[:300]

            # Refined condition for clarity and safety
            if (not json_response or
                    "data" not in json_response or
                    not isinstance(json_response.get("data"), list) or
                    "unit" not in json_response or
                    "interval" not in json_response):
                _LOGGER.warning(
                    "smartENERGY response malformed or missing critical fields for area %s: %s",
                    self.market_area, raw_response_preview
                )
                return PriceData(hourly_raw=[], timezone=self._market_config["timezone_hint"], currency=self._market_config["currency"], source=self.source_name, meta={"error": "Malformed API response", "raw_response_preview": raw_response_preview})

            api_data_list = json_response["data"]
            price_unit = json_response["unit"].lower()
            interval_minutes = int(json_response["interval"])
            vat_rate = self._market_config["vat_rate"]

            if price_unit != "ct/kwh": # Original component used const CT_PER_KWH
                _LOGGER.error(
                    f"smartENERGY API returned unexpected unit '{price_unit}' for area {self.market_area}. Expected 'ct/kwh'."
                )
                return PriceData(hourly_raw=[], timezone=self._market_config["timezone_hint"], currency=self._market_config["currency"], source=self.source_name, meta={"error": f"Unexpected price unit: {price_unit}", "raw_response_preview": raw_response_preview})

            # Process raw entries: parse datetimes, convert price from cents to base unit, remove VAT
            processed_entries: List[Dict[str, Any]] = []
            for entry in api_data_list:
                try:
                    start_time_str = entry.get("date")
                    price_cents_kwh_vat_incl_str = entry.get("value")

                    if not all([start_time_str, price_cents_kwh_vat_incl_str]):
                        _LOGGER.debug("Skipping smartENERGY entry with missing data: %s", entry)
                        continue

                    start_time_dt = parse_iso_datetime_with_fallback(start_time_str)
                    if not start_time_dt:
                        _LOGGER.warning("Could not parse start time from smartENERGY entry: %s", entry)
                        continue
                    
                    start_time_utc = start_time_dt.astimezone(timezone.utc)
                    price_cents_kwh_vat_incl = float(price_cents_kwh_vat_incl_str)
                    
                    # Convert cents to EUR and remove VAT
                    price_eur_kwh_vat_incl = price_cents_kwh_vat_incl / 100.0
                    price_eur_kwh_vat_excl = price_eur_kwh_vat_incl / (1 + vat_rate)
                    
                    processed_entries.append({
                        "start_time_utc": start_time_utc,
                        "price_eur_kwh": round(price_eur_kwh_vat_excl, 5)
                    })
                except (ValueError, TypeError, KeyError) as e:
                    _LOGGER.warning("Could not parse data from smartENERGY entry for %s: %s (entry: %s)", self.market_area, e, entry)
                    continue
            
            if not processed_entries:
                _LOGGER.info("No valid price entries found after initial processing from smartENERGY for %s.", self.market_area)
                return PriceData(hourly_raw=[], timezone=self._market_config["timezone_hint"], currency=self._market_config["currency"], source=self.source_name, meta={"error": "No valid entries after parsing", "raw_response_preview": raw_response_preview})

            # Aggregate to hourly prices if interval is sub-hourly
            hourly_prices: List[Dict[str, Any]] = []
            if interval_minutes == 60:
                for entry in processed_entries:
                    hourly_prices.append({
                        API_RESPONSE_START_TIME: entry["start_time_utc"],
                        API_RESPONSE_PRICE: entry["price_eur_kwh"],
                    })
            elif interval_minutes < 60 and 60 % interval_minutes == 0:
                # Group by hour and average
                num_intervals_per_hour = 60 // interval_minutes
                current_hour_entries = []
                current_hour_start_utc = None

                for entry in sorted(processed_entries, key=lambda x: x["start_time_utc"]):
                    entry_hour_start_utc = entry["start_time_utc"].replace(minute=0, second=0, microsecond=0)
                    
                    if current_hour_start_utc is None:
                        current_hour_start_utc = entry_hour_start_utc
                    
                    if entry_hour_start_utc == current_hour_start_utc:
                        current_hour_entries.append(entry["price_eur_kwh"])
                    else:
                        # New hour, process previous hour's entries
                        if current_hour_entries:
                            avg_price = sum(current_hour_entries) / len(current_hour_entries)
                            hourly_prices.append({
                                API_RESPONSE_START_TIME: current_hour_start_utc,
                                API_RESPONSE_PRICE: round(avg_price, 5),
                            })
                        # Reset for new hour
                        current_hour_start_utc = entry_hour_start_utc
                        current_hour_entries = [entry["price_eur_kwh"]]
                
                # Process the last collected hour
                if current_hour_start_utc and current_hour_entries:
                    avg_price = sum(current_hour_entries) / len(current_hour_entries)
                    hourly_prices.append({
                        API_RESPONSE_START_TIME: current_hour_start_utc,
                        API_RESPONSE_PRICE: round(avg_price, 5),
                    })
            else:
                _LOGGER.error(
                    f"smartENERGY API returned unsupported interval {interval_minutes} minutes for area {self.market_area}. Cannot aggregate to hourly."
                )
                return PriceData(hourly_raw=[], timezone=self._market_config["timezone_hint"], currency=self._market_config["currency"], source=self.source_name, meta={"error": f"Unsupported interval: {interval_minutes} min", "raw_response_preview": raw_response_preview})

            # Deduplicate (shouldn't be necessary if aggregation is correct, but as a safeguard)
            final_hourly_prices: List[Dict[str, Any]] = []
            seen_timestamps = set()
            for entry in sorted(hourly_prices, key=lambda x: x[API_RESPONSE_START_TIME]):
                if entry[API_RESPONSE_START_TIME] not in seen_timestamps:
                    final_hourly_prices.append(entry)
                    seen_timestamps.add(entry[API_RESPONSE_START_TIME])

            _LOGGER.info("Successfully processed %d unique hourly price points from smartENERGY for %s", len(final_hourly_prices), self.market_area)
            return PriceData(
                hourly_raw=final_hourly_prices,
                timezone="UTC", # Data is converted to UTC start times
                currency=self._market_config["currency"],
                source=self.source_name,
                meta={"api_url": SMART_ENERGY_API_URL, "raw_unit": "ct/kWh (VAT incl.)", "interval_minutes": interval_minutes, "raw_response_preview": raw_response_preview}
            )

        except aiohttp.ClientError as e:
            _LOGGER.error("Network error fetching smartENERGY data for %s: %s", self.market_area, e)
            raise
        except Exception as e:
            _LOGGER.error("Unexpected error processing smartENERGY data for %s: %s. Preview: %s", self.market_area, e, raw_response_preview)
            raise

    @property
    def name(self) -> str:
        return f"smartENERGY ({self.market_area})"

