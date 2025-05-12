import asyncio
import logging
from datetime import datetime, timezone # Removed timedelta as it's not used directly
from typing import Any, Dict, List

import aiohttp

from .base_api import BaseAPI, PriceData # Changed from BaseAPIAdapter
from .registry import register_api # Changed from register_adapter
from ..const import (
    API_RESPONSE_PRICE,
    API_RESPONSE_START_TIME,
    CURRENCY_EUR,
    NETWORK_TIMEOUT,
)
from ..const.sources import SOURCE_ENERGY_FORECAST # Ensure this is defined in const.sources
from ..utils.time import parse_iso_datetime_with_fallback
from ..utils.network import async_get_json_or_raise # Re-using existing utility

_LOGGER = logging.getLogger(__name__)

ENERGY_FORECAST_API_URL = "https://www.energyforecast.de/api/v1/predictions/prices_for_ha"

ENERGY_FORECAST_MARKET_CONFIG = {
    "DE-LU": {"currency": CURRENCY_EUR} # timezone_hint removed, not used for fetch logic
}

@register_api(
    name=SOURCE_ENERGY_FORECAST,
    regions=list(ENERGY_FORECAST_MARKET_CONFIG.keys()),
    default_priority=50
)
class EnergyForecastAPI(BaseAPI):
    """
    API for Energyforecast.de.
    Fetches forecasted energy prices, typically for Germany.
    Requires an API token.
    Prices are returned in EUR/kWh.
    """

    def __init__(self, config: Dict[str, Any], session: aiohttp.ClientSession):
        super().__init__(config, session)
        self._api_token = self._config.get("api_token")
        if not self._api_token:
            _LOGGER.error(
                "Energy Forecast API token not provided in configuration for source %s.",
                SOURCE_ENERGY_FORECAST
            )
        # self.market_area and self._market_config are set in fetch_data

    async def fetch_data(self, area: str) -> PriceData:
        if not self._api_token:
            _LOGGER.warning("Cannot fetch Energy Forecast data: API token is missing. Area: %s", area)
            return PriceData(hourly_raw=[], timezone="UTC", currency=CURRENCY_EUR, source=SOURCE_ENERGY_FORECAST, meta={"error": "API token missing", "area": area})

        market_area_upper = area.upper()
        market_config = ENERGY_FORECAST_MARKET_CONFIG.get(market_area_upper)

        if not market_config:
            _LOGGER.error(
                "Cannot fetch Energy Forecast data for %s: market area configuration is missing.", market_area_upper
            )
            return PriceData(hourly_raw=[], timezone="UTC", currency=CURRENCY_EUR, source=SOURCE_ENERGY_FORECAST, meta={"error": f"Market area {market_area_upper} not configured for Energy Forecast", "area": market_area_upper})

        params = {
            "token": self._api_token,
            "fixed_cost_cent": 0, 
            "vat": 0              
        }

        _LOGGER.debug("Fetching Energy Forecast data for area %s from %s", market_area_upper, ENERGY_FORECAST_API_URL)
        
        raw_response_preview = None
        price_data_currency = market_config["currency"]

        try:
            json_response = await async_get_json_or_raise(
                self._session, 
                ENERGY_FORECAST_API_URL, 
                params=params, 
                timeout=NETWORK_TIMEOUT
            )
            raw_response_preview = str(json_response)[:300]

            if not json_response or "forecast" not in json_response or \
               not isinstance(json_response.get("forecast"), dict) or \
               "data" not in json_response["forecast"] or \
               not isinstance(json_response["forecast"]["data"], list):
                _LOGGER.warning(
                    "Energy Forecast response malformed or missing critical data for area %s: %s",
                    market_area_upper, raw_response_preview
                )
                return PriceData(hourly_raw=[], timezone="UTC", currency=price_data_currency, source=SOURCE_ENERGY_FORECAST, meta={"error": "Malformed API response", "raw_response_preview": raw_response_preview, "api_url": ENERGY_FORECAST_API_URL, "area": market_area_upper})

            api_price_entries = json_response["forecast"]["data"]
            if not api_price_entries:
                _LOGGER.info("No price entries found in Energy Forecast response for area %s.", market_area_upper)
                # It's not an error if API returns no data, but good to note area.
                return PriceData(hourly_raw=[], timezone="UTC", currency=price_data_currency, source=SOURCE_ENERGY_FORECAST, meta={"info": "No price entries in API response", "raw_response_preview": raw_response_preview, "api_url": ENERGY_FORECAST_API_URL, "area": market_area_upper})

            hourly_prices: List[Dict[str, Any]] = []
            processed_timestamps = set()

            for entry in api_price_entries:
                try:
                    start_time_str = entry.get("start")
                    price_eur_kwh_str = entry.get("price")

                    if not all([start_time_str, price_eur_kwh_str]):
                        _LOGGER.debug("Skipping Energy Forecast entry with missing data: %s", entry)
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
                    
                    price_eur_kwh = round(float(price_eur_kwh_str), 5)

                    hourly_prices.append({
                        API_RESPONSE_START_TIME: start_time_utc,
                        API_RESPONSE_PRICE: price_eur_kwh,
                    })
                except (ValueError, TypeError, KeyError) as e:
                    _LOGGER.warning("Could not parse price entry from Energy Forecast for %s: %s (entry: %s)", market_area_upper, e, entry)
                    continue
            
            hourly_prices.sort(key=lambda x: x[API_RESPONSE_START_TIME])

            _LOGGER.info("Successfully processed %d unique hourly price points from Energy Forecast for %s", len(hourly_prices), market_area_upper)
            return PriceData(
                hourly_raw=hourly_prices,
                timezone="UTC", 
                currency=price_data_currency, 
                source=SOURCE_ENERGY_FORECAST,
                meta={
                    "api_url": ENERGY_FORECAST_API_URL, 
                    "raw_unit_from_api": f"{price_data_currency}/kWh", 
                    "raw_response_preview": raw_response_preview,
                    "area": market_area_upper
                    }
            )

        except aiohttp.ClientError as e:
            _LOGGER.error("Network error fetching Energy Forecast data for %s: %s", market_area_upper, e)
            # Add area to meta for re-raised exceptions if PriceData is constructed by FallbackManager
            # However, FallbackManager might not use this meta directly. For now, just raise.
            raise 
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout fetching Energy Forecast data for %s", market_area_upper)
            return PriceData(hourly_raw=[], timezone="UTC", currency=price_data_currency, source=SOURCE_ENERGY_FORECAST, meta={"error": "Timeout during API call", "api_url": ENERGY_FORECAST_API_URL, "area": market_area_upper})
        except Exception as e:
            _LOGGER.error("Unexpected error processing Energy Forecast data for %s: %s. Preview: %s", market_area_upper, e, raw_response_preview)
            # As above, consider how meta is used by error handlers upstream.
            raise

