import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import aiohttp

from custom_components.ge_spot.api.base_adapter import BaseAPIAdapter, PriceData
from custom_components.ge_spot.api.registry import register_adapter
from custom_components.ge_spot.const.api import API_RESPONSE_PRICE, API_RESPONSE_START_TIME
from custom_components.ge_spot.const.currencies import CURRENCY_EUR
from custom_components.ge_spot.const.network import NETWORK_TIMEOUT
from custom_components.ge_spot.const.sources import SOURCE_AWATTAR
from custom_components.ge_spot.utils.network import async_get_json_or_raise

_LOGGER = logging.getLogger(__name__)

AWATTAR_API_URL_BASE = "https://api.awattar.{market_area}/v1/marketdata"

# Mapping from ge-spot market areas to Awattar API market area codes
AWATTAR_MARKET_AREA_MAP = {
    "AT": "at",
    "DE-LU": "de",
}

def _to_epoch_milliseconds(dt: datetime) -> int:
    """Converts a datetime object to epoch milliseconds."""
    return int(dt.timestamp() * 1000)

@register_adapter(
    name=SOURCE_AWATTAR,
    regions=list(AWATTAR_MARKET_AREA_MAP.keys()),
    default_priority=50, # Arbitrary, can be adjusted
)
class AwattarAdapter(BaseAPIAdapter):
    """
    Adapter for the aWATTar API.
    Fetches day-ahead market prices for Austria and Germany.
    """

    def __init__(self, hass, api_key_manager, source_name: str, market_area: str, session: aiohttp.ClientSession, **kwargs):
        super().__init__(hass, api_key_manager, source_name, market_area, session, **kwargs)
        self._api_market_area = AWATTAR_MARKET_AREA_MAP.get(self.market_area.upper())

    async def async_fetch_data(self, target_datetime: datetime) -> PriceData:
        """
        Fetches aWATTar data for the given target_datetime (typically today).
        The API fetches data for a range, so we'll request data covering
        the target_datetime and the following day to ensure we get all relevant prices.
        """
        if not self._api_market_area:
            _LOGGER.error(
                "Cannot fetch aWATTar data for %s: market area not configured for aWATTar adapter.",
                self.market_area
            )
            return PriceData(
                hourly_raw=[],
                timezone="UTC",
                currency=CURRENCY_EUR,
                source=self.source_name,
                meta={"error": f"Market area {self.market_area} not configured for aWATTar"}
            )

        # Define the time window for the API request
        # Fetch from the start of the target day up to the end of the next day.
        start_of_target_day = target_datetime.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        # Awattar API expects start and end. We'll fetch for 2 full days.
        # Example: if target_datetime is for 15th, fetch from 15th 00:00 to 17th 00:00 (exclusive for end)
        # This covers all hours of the 15th and 16th.
        start_param_dt = start_of_target_day
        end_param_dt = start_of_target_day + timedelta(days=2)

        api_url = AWATTAR_API_URL_BASE.format(market_area=self._api_market_area)
        params = {
            "start": _to_epoch_milliseconds(start_param_dt),
            "end": _to_epoch_milliseconds(end_param_dt),
        }

        _LOGGER.debug(
            "Fetching aWATTar data for area %s (API area %s) from %s with params %s",
            self.market_area, self._api_market_area, api_url, params
        )

        raw_response_preview = None
        try:
            json_response = await async_get_json_or_raise(self._session, api_url, params=params, timeout=NETWORK_TIMEOUT)
            raw_response_preview = str(json_response)[:200]

            if not json_response or "data" not in json_response or not isinstance(json_response["data"], list):
                _LOGGER.warning(
                    "aWATTar response malformed or missing 'data' list for area %s: %s",
                    self.market_area, raw_response_preview
                )
                return PriceData(hourly_raw=[], timezone="UTC", currency=CURRENCY_EUR, source=self.source_name, meta={"error": "Malformed or empty API response", "raw_response_preview": raw_response_preview})

            hourly_prices: List[Dict[str, Any]] = []
            processed_timestamps = set()

            for entry in json_response["data"]:
                try:
                    # Timestamps are in milliseconds UTC
                    start_timestamp_ms = int(entry["start_timestamp"])
                    # end_timestamp_ms = int(entry["end_timestamp"]) # Not strictly needed for hourly start
                    price_eur_mwh = float(entry["marketprice"])
                    unit = entry.get("unit", "").lower()

                    if unit != "eur/mwh":
                        _LOGGER.warning(
                            "Unexpected unit '%s' in aWATTar data for area %s, expected 'eur/mwh'. Entry: %s",
                            unit, self.market_area, entry
                        )
                        # Depending on strictness, might want to skip or raise
                        # For now, we'll try to process if price is float, but log a warning.

                    start_time_utc = datetime.fromtimestamp(start_timestamp_ms / 1000, timezone.utc)
                    
                    # Avoid duplicate entries if API were to return overlapping intervals
                    if start_time_utc in processed_timestamps:
                        continue
                    processed_timestamps.add(start_time_utc)

                    price_eur_kwh = round(price_eur_mwh / 1000.0, 5) # Convert MWh to kWh and round

                    hourly_prices.append({
                        API_RESPONSE_START_TIME: start_time_utc,
                        API_RESPONSE_PRICE: price_eur_kwh,
                    })
                except (ValueError, TypeError, KeyError) as e:
                    _LOGGER.warning(
                        "Could not parse price/timestamp from aWATTar entry for %s: %s (entry: %s)",
                        self.market_area, e, entry
                    )
                    continue
            
            hourly_prices.sort(key=lambda x: x[API_RESPONSE_START_TIME])

            _LOGGER.info("Successfully processed %d unique price points from aWATTar for %s", len(hourly_prices), self.market_area)
            return PriceData(
                hourly_raw=hourly_prices,
                timezone="UTC", # Awattar API returns UTC timestamps
                currency=CURRENCY_EUR,
                source=self.source_name,
                meta={"api_url": api_url, "raw_unit": "EUR/MWh", "raw_response_preview": raw_response_preview}
            )

        except aiohttp.ClientError as e:
            _LOGGER.error("Network error fetching aWATTar data for %s: %s", self.market_area, e)
            # Let the FallbackManager handle retries/fallback by raising the error
            raise
        except Exception as e:
            _LOGGER.error(
                "Unexpected error processing aWATTar data for %s: %s. Response preview: %s",
                self.market_area, e, raw_response_preview
            )
            # Let the FallbackManager handle retries/fallback by raising the error
            raise

    @property
    def name(self) -> str:
        return f"aWATTar ({self.market_area})"
