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
    SOURCE_AWATTAR, # This will be added to sources.py
)
from custom_components.ge_spot.utils.network import async_get_json_or_raise # Assuming this utility
from custom_components.ge_spot.utils.time import ( # Assuming these utilities
    get_date_range_for_target_day,
    parse_iso_datetime_with_fallback,
)


_LOGGER = logging.getLogger(__name__)

# Defined market areas for Awattar
AWATTAR_MARKET_AREAS = {
    "AT": "at",
    "DE": "de",
}
API_URL_TEMPLATE = "https://api.awattar.{market_area_code}/v1/marketdata"

@register_adapter(
    name=SOURCE_AWATTAR,
    regions=list(AWATTAR_MARKET_AREAS.keys()),
    default_priority=10,
    currencies=[CURRENCY_EUR]
)
class AwattarAdapter(BaseAPIAdapter):
    """
    Adapter for the Awattar API.
    Fetches day-ahead electricity prices for Austria and Germany.
    """

    def __init__(self, hass, api_key_manager, source_name: str, market_area: str, session: aiohttp.ClientSession, **kwargs):
        super().__init__(hass, api_key_manager, source_name, market_area, session, **kwargs)
        self._api_url = API_URL_TEMPLATE.format(market_area_code=AWATTAR_MARKET_AREAS.get(self.market_area.upper(), "de"))

    def _to_epoch_milli_sec(self, dt: datetime) -> int:
        """Converts a datetime object to epoch milliseconds."""
        return int(dt.timestamp() * 1000)

    async def async_fetch_data(self, target_datetime: datetime) -> PriceData:
        """
        Fetches electricity prices for the specified target_datetime.
        Awattar API provides data for a range, so we fetch for yesterday, today and tomorrow
        to ensure we have data for the target_datetime and the next day.
        """
        start_fetch_day = target_datetime.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        end_fetch_day = start_fetch_day + timedelta(days=3) # Fetch a 3-day window

        params = {
            "start": self._to_epoch_milli_sec(start_fetch_day),
            "end": self._to_epoch_milli_sec(end_fetch_day),
        }

        _LOGGER.debug(
            "Fetching Awattar data for market_area %s, from %s to %s. URL: %s, Params: %s",
            self.market_area,
            start_fetch_day,
            end_fetch_day,
            self._api_url,
            params
        )

        try:
            response_data = await async_get_json_or_raise(self._session, self._api_url, params=params, timeout=NETWORK_TIMEOUT)
            
            if not response_data or "data" not in response_data or not isinstance(response_data["data"], list):
                _LOGGER.error("Awattar API returned no data or unexpected format: %s", response_data)
                return PriceData(hourly_raw=[], timezone="UTC", currency=CURRENCY_EUR, source=self.source_name)

            hourly_prices: List[Dict[str, Any]] = []
            for entry in response_data["data"]:
                if not all(k in entry for k in ["start_timestamp", "end_timestamp", "marketprice", "unit"]):
                    _LOGGER.warning("Skipping malformed entry from Awattar: %s", entry)
                    continue

                # Price is in EUR/MWh, convert to EUR/kWh
                price_eur_mwh = float(entry["marketprice"])
                price_eur_kwh = round(price_eur_mwh / 1000.0, 5) # 5 decimal places as per Awattar example

                start_time_ts = entry["start_timestamp"] / 1000
                start_time_utc = datetime.fromtimestamp(start_time_ts, timezone.utc)

                hourly_prices.append({
                    API_RESPONSE_START_TIME: start_time_utc,
                    API_RESPONSE_PRICE: price_eur_kwh,
                })
            
            _LOGGER.info("Successfully fetched %d price points from Awattar for %s", len(hourly_prices), self.market_area)
            return PriceData(
                hourly_raw=hourly_prices,
                timezone="UTC", # Awattar returns UTC timestamps
                currency=CURRENCY_EUR,
                source=self.source_name,
                meta={"api_url": self._api_url, "raw_unit": "EUR/MWh"}
            )

        except aiohttp.ClientError as e:
            _LOGGER.error("Network error fetching Awattar data for %s: %s", self.market_area, e)
            raise # Re-raise to be handled by UnifiedPriceManager
        except Exception as e:
            _LOGGER.error("Error processing Awattar data for %s: %s", self.market_area, e)
            raise # Re-raise

    @property
    def name(self) -> str:
        return f"Awattar ({self.market_area})"
