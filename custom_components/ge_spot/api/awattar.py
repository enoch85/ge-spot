import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import aiohttp

from .base_api import BaseAPI, PriceData
from .registry import register_api
from ..const.api import API_RESPONSE_PRICE, API_RESPONSE_START_TIME # Corrected import
from ..const.currencies import CURRENCY_EUR # Corrected import
from ..const.network import NETWORK_TIMEOUT # Corrected import
from ..const.sources import SOURCE_AWATTAR # Corrected import
# Removed unused utils.time import

_LOGGER = logging.getLogger(__name__)

AWATTAR_API_URL_BASE = "https://api.awattar.{market_area}/v1/marketdata"

# Mapping from ge-spot market areas to Awattar API market area codes
AWATTAR_MARKET_AREA_MAP = {
    "AT": "at",
    "DE-LU": "de", # DE-LU is a common representation for Germany/Luxembourg bidding zone
}

def _to_epoch_milliseconds(dt: datetime) -> int:
    """Converts a datetime object to epoch milliseconds."""
    return int(dt.timestamp() * 1000)

@register_api(
    name=SOURCE_AWATTAR,
    regions=list(AWATTAR_MARKET_AREA_MAP.keys()),
    default_priority=50,
)
class AwattarAPI(BaseAPI):
    """
    API for the aWATTar service.
    Fetches day-ahead market prices for Austria and Germany.
    """

    def __init__(self, config: Dict[str, Any], session: aiohttp.ClientSession): # Changed signature
        super().__init__(config, session) # Pass config and session to BaseAPI
        # _api_market_area will be determined in fetch_data based on the 'area' parameter
        self._api_market_area: str | None = None


    async def fetch_data(self, area: str) -> PriceData: # Changed signature
        """
        Fetches aWATTar data for the given area.
        The API fetches data for a range, so we'll request data covering
        today and the following day to ensure we get all relevant prices.
        """
        market_area_upper = area.upper()
        self._api_market_area = AWATTAR_MARKET_AREA_MAP.get(market_area_upper)

        if not self._api_market_area:
            _LOGGER.error(
                "Cannot fetch aWATTar data for %s: market area not configured or supported for aWATTar API.",
                area
            )
            return PriceData(
                hourly_raw=[],
                timezone="UTC", # Default
                currency=CURRENCY_EUR, # Default
                source=SOURCE_AWATTAR,
                meta={"error": f"Market area {area} not configured/supported for aWATTar"}
            )

        # Define the time window for the API request based on current UTC time
        # This ensures we fetch "today" and "tomorrow" from UTC perspective
        now_utc = datetime.now(timezone.utc)
        start_of_today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        
        start_param_dt = start_of_today_utc
        # Fetch data for today and tomorrow to ensure coverage.
        # Awattar API might return data up to the end of the *next* full day if available.
        end_param_dt = start_of_today_utc + timedelta(days=2)


        api_url = AWATTAR_API_URL_BASE.format(market_area=self._api_market_area)
        params = {
            "start": _to_epoch_milliseconds(start_param_dt),
            "end": _to_epoch_milliseconds(end_param_dt),
        }

        _LOGGER.debug(
            "Fetching aWATTar data for area %s (API area %s) from %s with params %s",
            area, self._api_market_area, api_url, params
        )

        raw_response_preview = None
        try:
            # Assuming async_get_json_or_raise is a method in BaseAPI or a utility
            # For now, directly use self.session as per BaseAPI structure
            async with self.session.get(api_url, params=params, timeout=NETWORK_TIMEOUT) as response:
                response.raise_for_status()
                json_response = await response.json()
            
            raw_response_preview = str(json_response)[:200]

            if not json_response or "data" not in json_response or not isinstance(json_response["data"], list):
                _LOGGER.warning(
                    "aWATTar response malformed or missing 'data' list for area %s: %s",
                    area, raw_response_preview
                )
                return PriceData(hourly_raw=[], timezone="UTC", currency=CURRENCY_EUR, source=SOURCE_AWATTAR, meta={"error": "Malformed or empty API response", "raw_response_preview": raw_response_preview})

            hourly_prices: List[Dict[str, Any]] = []
            processed_timestamps = set()

            for entry in json_response["data"]:
                try:
                    start_timestamp_ms = int(entry["start_timestamp"])
                    price_eur_mwh = float(entry["marketprice"])
                    unit = entry.get("unit", "").lower()

                    if unit != "eur/mwh":
                        _LOGGER.warning(
                            "Unexpected unit '%s' in aWATTar data for area %s, expected 'eur/mwh'. Entry: %s",
                            unit, area, entry
                        )
                        # Continue processing if price is parseable, assume it's still MWh based on context

                    start_time_utc = datetime.fromtimestamp(start_timestamp_ms / 1000, timezone.utc)
                    
                    if start_time_utc in processed_timestamps:
                        continue
                    processed_timestamps.add(start_time_utc)

                    price_eur_kwh = round(price_eur_mwh / 1000.0, 5)

                    hourly_prices.append({
                        API_RESPONSE_START_TIME: start_time_utc, # Ensure this is datetime object
                        API_RESPONSE_PRICE: price_eur_kwh,
                    })
                except (ValueError, TypeError, KeyError) as e:
                    _LOGGER.warning(
                        "Could not parse price/timestamp from aWATTar entry for %s: %s (entry: %s)",
                        area, e, entry
                    )
                    continue
            
            hourly_prices.sort(key=lambda x: x[API_RESPONSE_START_TIME])

            _LOGGER.info("Successfully processed %d unique price points from aWATTar for %s", len(hourly_prices), area)
            return PriceData(
                hourly_raw=hourly_prices,
                timezone="UTC", # Data is processed into UTC timestamps
                currency=CURRENCY_EUR, # Awattar prices are in EUR
                source=SOURCE_AWATTAR,
                meta={"api_url": api_url, "raw_unit_from_api": "EUR/MWh", "raw_response_preview": raw_response_preview}
            )

        except aiohttp.ClientResponseError as e: # More specific exception for HTTP errors
            _LOGGER.error("HTTP error fetching aWATTar data for %s: %s - %s", area, e.status, e.message)
            raise # Re-raise for FallbackManager
        except aiohttp.ClientError as e: # General client errors (network, etc.)
            _LOGGER.error("Network error fetching aWATTar data for %s: %s", area, e)
            raise # Re-raise for FallbackManager
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout fetching aWATTar data for %s", area)
            # Return empty PriceData on timeout, or re-raise if FallbackManager should handle
            return PriceData(hourly_raw=[], timezone="UTC", currency=CURRENCY_EUR, source=SOURCE_AWATTAR, meta={"error": "Timeout during API call", "api_url": api_url})
        except Exception as e:
            _LOGGER.error(
                "Unexpected error processing aWATTar data for %s: %s. Response preview: %s",
                area, e, raw_response_preview
            )
            raise # Re-raise for FallbackManager
