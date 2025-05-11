\
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, cast
from zoneinfo import ZoneInfo

import aiohttp

from custom_components.ge_spot.api.base_adapter import BaseAPIAdapter, PriceData
from custom_components.ge_spot.api.registry import register_adapter
from custom_components.ge_spot.const import (
    API_RESPONSE_HOUR,
    API_RESPONSE_PRICE,
    API_RESPONSE_START_TIME,
    CURRENCY_EUR,
    NETWORK_TIMEOUT,
    SOURCE_SMART_ENERGY, # This will be added to sources.py
)
from custom_components.ge_spot.utils.network import async_get_json_or_raise
from custom_components.ge_spot.utils.time import parse_iso_datetime_with_fallback

_LOGGER = logging.getLogger(__name__)

API_URL = "https://apis.smartenergy.at/market/v1/price"
# smartENERGY primarily serves "AT"
SMART_ENERGY_MARKET_AREAS = ["AT"]

@register_adapter(
    name=SOURCE_SMART_ENERGY,
    regions=SMART_ENERGY_MARKET_AREAS, # Austria
    default_priority=60,
    currencies=[CURRENCY_EUR]
)
class SmartEnergyAdapter(BaseAPIAdapter):
    """
    Adapter for the smartENERGY.at API.
    Fetches electricity prices for Austria.
    API returns prices in ct/kWh including 20% VAT. Adapter will convert to EUR/kWh and remove VAT.
    API may return 15-minute intervals; adapter will aggregate to hourly.
    """

    def __init__(self, hass, api_key_manager, source_name: str, market_area: str, session: aiohttp.ClientSession, **kwargs):
        super().__init__(hass, api_key_manager, source_name, market_area, session, **kwargs)
        self._source_timezone = ZoneInfo("Europe/Vienna") # smartENERGY is Austrian

    async def async_fetch_data(self, target_datetime: datetime) -> PriceData:
        """
        Fetches electricity prices.
        """
        _LOGGER.debug("Fetching smartENERGY data for %s. URL: %s", self.market_area, API_URL)

        try:
            response_data = await async_get_json_or_raise(self._session, API_URL, timeout=NETWORK_TIMEOUT)

            if not response_data or "data" not in response_data or not isinstance(response_data["data"], list) or "unit" not in response_data:
                _LOGGER.error("smartENERGY API returned no data or unexpected format: %s", response_data)
                return PriceData(hourly_raw=[], timezone="Europe/Vienna", currency=CURRENCY_EUR, source=self.source_name)

            api_prices = response_data["data"]
            raw_unit = response_data.get("unit", "ct/kWh").lower()
            interval_minutes = response_data.get("interval", 15) # API states interval in minutes

            hourly_prices_intermediate: Dict[datetime, List[float]] = {} # Store prices for each hour start

            for entry in api_prices:
                if not all(k in entry for k in ["date", "value"]):
                    _LOGGER.warning("Skipping malformed entry from smartENERGY: %s", entry)
                    continue
                
                # Timestamp is ISO string, e.g., "2023-10-27T00:00:00+02:00"
                start_time_local = parse_iso_datetime_with_fallback(entry["date"])
                if start_time_local is None:
                    _LOGGER.warning("Could not parse 'date' from smartENERGY entry: %s", entry)
                    continue
                
                # Ensure it's timezone-aware using the source's timezone if naive
                if start_time_local.tzinfo is None:
                    start_time_local = start_time_local.replace(tzinfo=self._source_timezone)
                
                price_value_ct_kwh = float(entry["value"])

                # Convert price from ct/kWh to EUR/kWh and remove 20% Austrian VAT
                # Price in API is value / 100 (to EUR) / 1.2 (remove VAT)
                # Adapter should return raw spot price, so VAT removal is correct here.
                price_eur_kwh_excl_vat = round((price_value_ct_kwh / 100.0) / 1.2, 5)

                # Group prices by hour start (UTC)
                hour_start_utc = start_time_local.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
                
                if hour_start_utc not in hourly_prices_intermediate:
                    hourly_prices_intermediate[hour_start_utc] = []
                hourly_prices_intermediate[hour_start_utc].append(price_eur_kwh_excl_vat)

            # Aggregate to hourly by averaging if multiple entries per hour (e.g., 15-min data)
            final_hourly_prices: List[Dict[str, Any]] = []
            for hour_start_utc, prices_in_hour in sorted(hourly_prices_intermediate.items()):
                if prices_in_hour:
                    avg_price_eur_kwh = round(sum(prices_in_hour) / len(prices_in_hour), 5)
                    final_hourly_prices.append({
                        API_RESPONSE_START_TIME: hour_start_utc, # Already UTC
                        API_RESPONSE_PRICE: avg_price_eur_kwh,
                    })
            
            _LOGGER.info("Successfully fetched and processed %d hourly price points from smartENERGY for %s", len(final_hourly_prices), self.market_area)
            return PriceData(
                hourly_raw=final_hourly_prices,
                timezone="Europe/Vienna", # Original timezone context
                currency=CURRENCY_EUR,
                source=self.source_name,
                meta={"api_url": API_URL, "raw_unit_from_api": raw_unit, "original_interval_min": interval_minutes}
            )

        except aiohttp.ClientError as e:
            _LOGGER.error("Network error fetching smartENERGY data for %s: %s", self.market_area, e)
            raise
        except Exception as e:
            _LOGGER.error("Error processing smartENERGY data for %s: %s", self.market_area, e)
            raise

    @property
    def name(self) -> str:
        return f"smartENERGY.at ({self.market_area})"

