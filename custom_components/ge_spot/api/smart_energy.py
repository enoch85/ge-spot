import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import aiohttp

from .base_api import BaseAPI, PriceData
from .registry import register_api
from ..const import (
    API_RESPONSE_PRICE,
    API_RESPONSE_START_TIME,
    CURRENCY_EUR,
    NETWORK_TIMEOUT,
)
from ..const.sources import SOURCE_SMART_ENERGY
from ..utils.network import async_get_json_or_raise

_LOGGER = logging.getLogger(__name__)

SMART_ENERGY_API_URL_BASE = "https://api.smartenergy.at/marketdata/v1/"
ENDPOINT_PRICE_PROFILE = "priceprofile/{country_code}/{start_timestamp_ms}/{end_timestamp_ms}"

SMART_ENERGY_MARKET_CONFIG = {
    "AT": {"currency": CURRENCY_EUR, "api_country_code": "AT"} # timezone_hint removed as fetch is UTC based
}

@register_api(
    name=SOURCE_SMART_ENERGY,
    regions=list(SMART_ENERGY_MARKET_CONFIG.keys()),
    default_priority=70,
)
class SmartEnergyAPI(BaseAPI):
    """
    API for SmartEnergy.at (Austria).
    Fetches day-ahead market prices.
    The API endpoint used expects UTC timestamps in milliseconds and returns hourly prices.
    """

    def __init__(self, config: Dict[str, Any], session: aiohttp.ClientSession):
        super().__init__(config, session)
        # self.market_area and self._market_config are set in fetch_data

    async def fetch_data(self, area: str) -> PriceData:
        market_area_upper = area.upper() # Renamed for clarity
        market_config = SMART_ENERGY_MARKET_CONFIG.get(market_area_upper)

        if not market_config:
            _LOGGER.error(
                "Cannot fetch smartENERGY data for %s: market area configuration is missing.", market_area_upper
            )
            return PriceData(hourly_raw=[], timezone="UTC", currency=CURRENCY_EUR, source=SOURCE_SMART_ENERGY, meta={"error": f"Market area {market_area_upper} not configured for smartENERGY"})

        api_country_code = market_config["api_country_code"]
        price_data_currency = market_config["currency"]

        # Determine the time range for the query based on UTC.
        # Fetch data for today and tomorrow (UTC).
        now_utc = datetime.now(timezone.utc)
        start_time_utc_query = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        # Fetch up to the start of the day after tomorrow to cover all of tomorrow.
        end_time_utc_query = start_time_utc_query + timedelta(days=2)

        start_timestamp_ms = int(start_time_utc_query.timestamp() * 1000)
        end_timestamp_ms = int(end_time_utc_query.timestamp() * 1000)

        url = (
            f"{SMART_ENERGY_API_URL_BASE}"
            f"{ENDPOINT_PRICE_PROFILE.format(country_code=api_country_code, start_timestamp_ms=start_timestamp_ms, end_timestamp_ms=end_timestamp_ms)}"
        )

        _LOGGER.debug("Fetching smartENERGY data for area %s from URL: %s", market_area_upper, url)
        raw_response_preview = None
        try:
            json_response = await async_get_json_or_raise(self.session, url, timeout=NETWORK_TIMEOUT)
            raw_response_preview = str(json_response)[:300]

            if not json_response or "data" not in json_response or "marketdataItems" not in json_response["data"]:
                _LOGGER.warning(
                    "smartENERGY response malformed or missing critical data for area %s: %s",
                    market_area_upper, raw_response_preview
                )
                # Ensure timezone is UTC for error PriceData as well
                return PriceData(hourly_raw=[], timezone="UTC", currency=price_data_currency, source=SOURCE_SMART_ENERGY, meta={"error": "Malformed API response", "raw_response_preview": raw_response_preview, "api_url": url})

            marketdata_items = json_response["data"]["marketdataItems"]
            hourly_prices: List[Dict[str, Any]] = []
            processed_timestamps = set()

            for item in marketdata_items:
                if "ptuPrices" not in item or not isinstance(item["ptuPrices"], list):
                    continue
                for ptu_price_entry in item["ptuPrices"]:
                    try:
                        start_timestamp_ms_entry = ptu_price_entry.get("startTimestamp")
                        price_eur_mwh = ptu_price_entry.get("price")
                        resolution = ptu_price_entry.get("resolution", "PT60M")

                        if start_timestamp_ms_entry is None or price_eur_mwh is None:
                            _LOGGER.debug("Skipping smartENERGY entry with missing timestamp or price: %s", ptu_price_entry)
                            continue

                        start_time_utc = datetime.fromtimestamp(start_timestamp_ms_entry / 1000, tz=timezone.utc)
                        
                        if resolution != "PT60M":
                            _LOGGER.warning(
                                "smartENERGY API for %s returned non-hourly data (resolution: %s). "
                                "This adapter currently only processes PT60M. Entry: %s", 
                                market_area_upper, resolution, ptu_price_entry
                            )
                            continue

                        if start_time_utc in processed_timestamps:
                            continue 
                        processed_timestamps.add(start_time_utc)
                        
                        price_eur_kwh = round(float(price_eur_mwh) / 1000.0, 5)

                        hourly_prices.append({
                            API_RESPONSE_START_TIME: start_time_utc,
                            API_RESPONSE_PRICE: price_eur_kwh,
                        })
                    except (ValueError, TypeError, KeyError) as e:
                        _LOGGER.warning("Could not parse price entry from smartENERGY for %s: %s (entry: %s)", market_area_upper, e, ptu_price_entry)
                        continue
            
            hourly_prices.sort(key=lambda x: x[API_RESPONSE_START_TIME])

            _LOGGER.info("Successfully processed %d unique hourly price points from smartENERGY for %s", len(hourly_prices), market_area_upper)
            return PriceData(
                hourly_raw=hourly_prices,
                timezone="UTC", 
                currency=price_data_currency,
                source=SOURCE_SMART_ENERGY,
                meta={"api_url": url, "raw_unit_from_api": "EUR/MWh", "days_fetched": [start_time_utc_query.strftime('%Y-%m-%d'), (end_time_utc_query - timedelta(days=1)).strftime('%Y-%m-%d')]}
            )

        except aiohttp.ClientError as e:
            _LOGGER.error("Network error fetching smartENERGY data for %s from %s: %s", market_area_upper, url, e)
            raise 
        except Exception as e:
            _LOGGER.error("Unexpected error processing smartENERGY data for %s from %s: %s. Preview: %s", market_area_upper, url, e, raw_response_preview)
            raise

