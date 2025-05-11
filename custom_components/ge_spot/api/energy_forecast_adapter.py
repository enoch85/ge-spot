\
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, cast

import aiohttp

from custom_components.ge_spot.api.base_adapter import BaseAPIAdapter, PriceData
from custom_components.ge_spot.api.registry import register_adapter
from custom_components.ge_spot.const import (
    API_RESPONSE_HOUR,
    API_RESPONSE_PRICE,
    API_RESPONSE_START_TIME,
    CURRENCY_EUR,
    NETWORK_TIMEOUT,
    SOURCE_ENERGY_FORECAST, # This will be added to sources.py
)
from custom_components.ge_spot.utils.network import async_get_json_or_raise
from custom_components.ge_spot.utils.time import parse_iso_datetime_with_fallback

_LOGGER = logging.getLogger(__name__)

API_URL = "https://www.energyforecast.de/api/v1/predictions/prices_for_ha"
# Energyforecast seems to primarily support "DE" or "DE-LU"
ENERGY_FORECAST_MARKET_AREAS = ["DE"] 

@register_adapter(
    name=SOURCE_ENERGY_FORECAST,
    regions=ENERGY_FORECAST_MARKET_AREAS, # Typically "DE"
    default_priority=30,
    currencies=[CURRENCY_EUR],
    requires_api_key=True # Indicates this adapter needs an API key
)
class EnergyForecastAdapter(BaseAPIAdapter):
    """
    Adapter for the Energyforecast.de API.
    Fetches forecasted electricity prices. Requires an API token.
    """

    def __init__(self, hass, api_key_manager, source_name: str, market_area: str, session: aiohttp.ClientSession, **kwargs):
        super().__init__(hass, api_key_manager, source_name, market_area, session, **kwargs)
        self._api_token = self.api_key_manager.get_api_key(self.source_name, self.market_area)
        if not self._api_token:
            _LOGGER.error("API token for Energyforecast (%s) not found.", self.market_area)
            # Adapter will likely fail to fetch, or UnifiedPriceManager should not select it.
            # Consider raising an error here or letting it fail in fetch_data.

    async def async_fetch_data(self, target_datetime: datetime) -> PriceData:
        """
        Fetches electricity prices. Energyforecast provides current and future forecasts.
        """
        if not self._api_token:
            _LOGGER.warning("Cannot fetch Energyforecast data for %s: API token is missing.", self.market_area)
            return PriceData(hourly_raw=[], timezone="Europe/Berlin", currency=CURRENCY_EUR, source=self.source_name)

        params = {
            "token": self._api_token,
            "fixed_cost_cent": 0, # Request raw prices
            "vat": 0,             # Request raw prices
        }
        _LOGGER.debug("Fetching Energyforecast data for %s. URL: %s", self.market_area, API_URL)

        try:
            response_data = await async_get_json_or_raise(self._session, API_URL, params=params, timeout=NETWORK_TIMEOUT)

            if not response_data or "forecast" not in response_data or "data" not in response_data["forecast"]:
                _LOGGER.error("Energyforecast API returned no data or unexpected format: %s", response_data)
                return PriceData(hourly_raw=[], timezone="Europe/Berlin", currency=CURRENCY_EUR, source=self.source_name)

            api_prices = response_data["forecast"]["data"]
            hourly_prices: List[Dict[str, Any]] = []

            for entry in api_prices:
                if not all(k in entry for k in ["start", "end", "price"]):
                    _LOGGER.warning("Skipping malformed entry from Energyforecast: %s", entry)
                    continue
                
                # Timestamps are ISO strings, e.g., "2023-10-27T00:00:00+02:00"
                # Price is in EUR/kWh directly
                start_time = parse_iso_datetime_with_fallback(entry["start"])
                price_eur_kwh = round(float(entry["price"]), 5)

                if start_time is None:
                    _LOGGER.warning("Could not parse start_time from Energyforecast entry: %s", entry)
                    continue
                
                # Ensure start_time is UTC for internal consistency if it's not already
                # The parse_iso_datetime_with_fallback should handle timezone conversion to UTC if tz info is present.
                # If it returns naive, assume it's local to the API (Europe/Berlin) and convert.
                if start_time.tzinfo is None:
                     start_time = start_time.replace(tzinfo=ZoneInfo("Europe/Berlin")).astimezone(timezone.utc)
                else: # If it has timezone info, ensure it's UTC
                     start_time = start_time.astimezone(timezone.utc)


                hourly_prices.append({
                    API_RESPONSE_START_TIME: start_time, # Store as UTC
                    API_RESPONSE_PRICE: price_eur_kwh,
                })
            
            _LOGGER.info("Successfully fetched %d price points from Energyforecast for %s", len(hourly_prices), self.market_area)
            return PriceData(
                hourly_raw=hourly_prices,
                timezone="Europe/Berlin", # Original timezone of the data context
                currency=CURRENCY_EUR,
                source=self.source_name,
                meta={"api_url": API_URL, "raw_unit": "EUR/kWh"}
            )

        except aiohttp.ClientError as e:
            _LOGGER.error("Network error fetching Energyforecast data for %s: %s", self.market_area, e)
            raise
        except Exception as e:
            _LOGGER.error("Error processing Energyforecast data for %s: %s", self.market_area, e)
            raise

    @property
    def name(self) -> str:
        return f"Energyforecast.de ({self.market_area})"

