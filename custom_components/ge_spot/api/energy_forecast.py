import asyncio
import logging
from datetime import datetime, timezone # Removed timedelta as it's not used directly
from typing import Any, Dict, List

import aiohttp

from custom_components.ge_spot.api.base_adapter import BaseAPIAdapter, PriceData
from custom_components.ge_spot.api.registry import register_adapter
from custom_components.ge_spot.const.api import API_RESPONSE_PRICE, API_RESPONSE_START_TIME
from custom_components.ge_spot.const.currencies import CURRENCY_EUR
from custom_components.ge_spot.const.network import NETWORK_TIMEOUT
from custom_components.ge_spot.const.sources import SOURCE_ENERGY_FORECAST # Will be added to const/sources.py
from custom_components.ge_spot.utils.network import async_get_json_or_raise
from custom_components.ge_spot.utils.time import parse_iso_datetime_with_fallback # For robust datetime parsing

_LOGGER = logging.getLogger(__name__)

ENERGY_FORECAST_API_URL = "https://www.energyforecast.de/api/v1/predictions/prices_for_ha"

# Mapping from ge-spot market areas to Energy Forecast API (if specific mapping were needed)
# For now, it seems to be primarily for "DE" or a general token-based access.
# The original code had market_area="de" hardcoded for the class instance,
# but the API call itself doesn't seem to use market_area in params.
# We will assume the token dictates the region or it's a general forecast.
# If specific regions are supported via API params later, this can be expanded.
ENERGY_FORECAST_MARKET_CONFIG = {
    "DE-LU": {"currency": CURRENCY_EUR, "timezone_hint": "Europe/Berlin"},
    # Add other regions if the API supports them and they are distinct
    # For now, let's assume it's mainly DE focused as per original class
}

@register_adapter(
    name=SOURCE_ENERGY_FORECAST,
    regions=list(ENERGY_FORECAST_MARKET_CONFIG.keys()), # Or a more generic list if token defines region
    default_priority=70 # Arbitrary, can be adjusted
)
class EnergyForecastAdapter(BaseAPIAdapter):
    """
    Adapter for the Energyforecast.de API.
    Fetches forecast prices. Requires an API token.
    """

    def __init__(self, hass, api_key_manager, source_name: str, market_area: str, session: aiohttp.ClientSession, **kwargs):
        super().__init__(hass, api_key_manager, source_name, market_area, session, **kwargs)
        # The API token is managed by ApiKeyManager and passed via self.api_key
        self._market_config = ENERGY_FORECAST_MARKET_CONFIG.get(self.market_area.upper())
        if not self._market_config:
            # Fallback for a generic setup if market area not in specific config
            # This might occur if the adapter is registered for regions not explicitly in ENERGY_FORECAST_MARKET_CONFIG
            # but the API token itself is region-specific or general.
            _LOGGER.warning(
                f"Market area {self.market_area} not in ENERGY_FORECAST_MARKET_CONFIG, "
                f"using default EUR and UTC. Ensure API token is valid for this context."
            )
            self._market_config = {"currency": CURRENCY_EUR, "timezone_hint": "UTC"}


    async def async_fetch_data(self, target_datetime: datetime) -> PriceData:
        """
        Fetches Energyforecast.de data.
        The API provides a forecast, so target_datetime helps in logging/context but the API returns available forecast.
        """
        api_token = self.api_key # Fetched by ApiKeyManager

        if not api_token:
            _LOGGER.error("Energy Forecast API token is missing. Cannot fetch data.")
            return PriceData(hourly_raw=[], timezone=self._market_config["timezone_hint"], currency=self._market_config["currency"], source=self.source_name, meta={"error": "API token missing"})

        params = {
            "token": api_token,
            "fixed_cost_cent": 0, # As per original component's call
            "vat": 0              # As per original component's call
        }

        _LOGGER.debug(
            "Fetching Energy Forecast data for area %s with URL %s", 
            self.market_area, ENERGY_FORECAST_API_URL
        )

        raw_response_preview = None
        try:
            json_response = await async_get_json_or_raise(self._session, ENERGY_FORECAST_API_URL, params=params, timeout=NETWORK_TIMEOUT)
            raw_response_preview = str(json_response)[:200]

            if not json_response or "forecast" not in json_response or \
               not isinstance(json_response["forecast"], dict) or \
               "data" not in json_response["forecast"] or \
               not isinstance(json_response["forecast"]["data"], list):
                _LOGGER.warning(
                    "Energy Forecast response malformed or missing 'forecast.data' list for area %s: %s",
                    self.market_area, raw_response_preview
                )
                return PriceData(hourly_raw=[], timezone=self._market_config["timezone_hint"], currency=self._market_config["currency"], source=self.source_name, meta={"error": "Malformed or empty API response", "raw_response_preview": raw_response_preview})
            
            api_data_list = json_response["forecast"]["data"]
            hourly_prices: List[Dict[str, Any]] = []
            processed_timestamps = set()

            for entry in api_data_list:
                try:
                    # Timestamps are full ISO strings like "2023-10-26T00:00:00+02:00"
                    # The original component uses datetime.fromisoformat directly.
                    # We should ensure they are parsed into timezone-aware UTC datetimes.
                    start_time_str = entry.get("start")
                    # end_time_str = entry.get("end") # Not strictly needed if we trust hourly data points
                    price_eur_kwh_str = entry.get("price")

                    if not all([start_time_str, price_eur_kwh_str]):
                        _LOGGER.debug("Skipping entry with missing data: %s", entry)
                        continue

                    start_time_dt = parse_iso_datetime_with_fallback(start_time_str)
                    if not start_time_dt:
                        _LOGGER.warning("Could not parse start time from Energy Forecast entry: %s", entry)
                        continue
                    
                    start_time_utc = start_time_dt.astimezone(timezone.utc)

                    if start_time_utc in processed_timestamps:
                        _LOGGER.debug("Skipping duplicate timestamp from Energy Forecast: %s", start_time_utc)
                        continue
                    processed_timestamps.add(start_time_utc)

                    price_eur_kwh = round(float(price_eur_kwh_str), 5) # Original used 6, 5 is common for kWh

                    hourly_prices.append({
                        API_RESPONSE_START_TIME: start_time_utc,
                        API_RESPONSE_PRICE: price_eur_kwh,
                    })
                except (ValueError, TypeError, KeyError) as e:
                    _LOGGER.warning(
                        "Could not parse price/timestamp from Energy Forecast entry for %s: %s (entry: %s)",
                        self.market_area, e, entry
                    )
                    continue
            
            hourly_prices.sort(key=lambda x: x[API_RESPONSE_START_TIME])

            _LOGGER.info("Successfully processed %d unique price points from Energy Forecast for %s", len(hourly_prices), self.market_area)
            return PriceData(
                hourly_raw=hourly_prices,
                timezone="UTC", # Data is converted to UTC start times
                currency=CURRENCY_EUR, # API seems to provide EUR
                source=self.source_name,
                meta={"api_url": ENERGY_FORECAST_API_URL, "raw_unit": "EUR/kWh", "raw_response_preview": raw_response_preview}
            )

        except aiohttp.ClientError as e:
            _LOGGER.error("Network error fetching Energy Forecast data for %s: %s", self.market_area, e)
            raise # Let FallbackManager handle retries/fallback
        except Exception as e:
            _LOGGER.error(
                "Unexpected error processing Energy Forecast data for %s: %s. Response preview: %s",
                self.market_area, e, raw_response_preview
            )
            raise # Let FallbackManager handle retries/fallback

    @property
    def name(self) -> str:
        return f"Energyforecast.de ({self.market_area})"

