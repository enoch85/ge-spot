import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import aiohttp

from .base_api import BaseAPI, PriceData
from .registry import register_api
from ..const.api import API_RESPONSE_PRICE, API_RESPONSE_START_TIME
from ..const.currencies import CURRENCY_EUR
from ..const.network import NETWORK_TIMEOUT
from ..const.sources import SOURCE_SMARD # Ensure this is defined in const/sources.py

_LOGGER = logging.getLogger(__name__)

# Configuration for SMARD API access
# series_id refers to the SMARD data series for day-ahead auction results (hourly).
# region_slug is used in the API URL structure.
_SMARD_AREA_CONFIG = {
    "DE": {"series_id": "416911", "region_slug": "DE", "currency": CURRENCY_EUR},
    "AT": {"series_id": "416912", "region_slug": "AT", "currency": CURRENCY_EUR},
}

# SMARD API URL template for fetching hourly day-ahead auction prices.
# Timestamp is milliseconds since epoch for 00:00 UTC of the target day.
_SMARD_API_URL_TEMPLATE = "https://www.smard.de/app/chart_data/{series_id}/{region_slug}/{series_id}_{region_slug}_hour_{timestamp_ms}.json"
# Note: SMARD uses different paths for quarterhour, hour, etc.
# For series 416911/416912 (Day-Ahead Auktion Stundenkontrakte), the data is hourly.
# The URL segment might be specific, e.g. _hour_ or _quarterhour_ depending on the exact data module.
# The example from Bundesnetzagentur for hourly data often looks like:
# https://www.smard.de/app/chart_data/1223/DE/1223_DE_hour_1609459200000.json (1223 is old key for Day-Ahead Spot DE)
# The series IDs 416911 (DE) and 416912 (AT) are more current for "Day-Ahead Auktion Stundenkontrakte".
# Assuming the _hour_ slug is correct for these series. If issues arise, this URL might need adjustment.


def _to_smard_epoch_milliseconds(dt: datetime) -> int:
    """Converts a datetime object to epoch milliseconds for the start of the day (00:00 UTC)."""
    start_of_day_utc = dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    return int(start_of_day_utc.timestamp() * 1000)

@register_api(
    name=SOURCE_SMARD,
    regions=list(_SMARD_AREA_CONFIG.keys()), # ["DE", "AT"]
    default_priority=60, # Example priority
)
class SmardAPI(BaseAPI):
    """
    API for the SMARD.de service (German Bundesnetzagentur).
    Fetches hourly day-ahead electricity market prices for Germany and Austria.
    """

    def __init__(self, config: Dict[str, Any], session: aiohttp.ClientSession):
        super().__init__(config, session)
        # No specific config needed from 'config' dict for Smard beyond BaseAPI

    async def _fetch_smard_data_for_day(self, area_code: str, target_day_utc: datetime) -> List[Dict[str, Any]]:
        """
        Fetches SMARD data for a specific day and market area.
        SMARD API provides data in daily files, timestamped for the start of that day.
        """
        current_area_config = _SMARD_AREA_CONFIG[area_code]
        series_id = current_area_config["series_id"]
        region_slug = current_area_config["region_slug"]
        
        timestamp_ms = _to_smard_epoch_milliseconds(target_day_utc)
        
        api_url = _SMARD_API_URL_TEMPLATE.format(
            series_id=series_id,
            region_slug=region_slug,
            timestamp_ms=timestamp_ms
        )

        _LOGGER.debug(
            "Fetching SMARD data for area %s (series %s, region %s) for day %s from %s",
            area_code, series_id, region_slug, target_day_utc.strftime('%Y-%m-%d'), api_url
        )
        
        raw_response_preview = None
        try:
            async with self.session.get(api_url, timeout=NETWORK_TIMEOUT) as response:
                response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
                json_response = await response.json()
                raw_response_preview = str(json_response)[:250] # Increased preview length

            # Validate structure of the response
            if not json_response or "series" not in json_response or not isinstance(json_response.get("series"), list):
                _LOGGER.warning(
                    "SMARD response malformed or missing 'series' list for area %s, day %s. Preview: %s",
                    area_code, target_day_utc.strftime('%Y-%m-%d'), raw_response_preview
                )
                return []

            day_prices: List[Dict[str, Any]] = []
            for point in json_response["series"]:
                # Each 'point' is expected to be a list: [timestamp_ms, price_eur_mwh]
                if point is None or len(point) < 2 or point[0] is None or point[1] is None:
                    _LOGGER.debug("Skipping malformed data point in SMARD response: %s", str(point))
                    continue 

                try:
                    entry_timestamp_ms = int(point[0])
                    price_eur_mwh = float(point[1]) # SMARD prices are in EUR/MWh

                    # Convert price from EUR/MWh to EUR/kWh
                    price_eur_kwh = round(price_eur_mwh / 1000.0, 5)
                    
                    start_time_utc = datetime.fromtimestamp(entry_timestamp_ms / 1000, timezone.utc)

                    # SMARD data should align with hourly intervals for these series
                    # Double-check if the timestamp is for the target day, though API call is specific
                    if start_time_utc.date() != target_day_utc.date():
                        _LOGGER.debug("SMARD data point %s is outside target day %s, skipping.", start_time_utc, target_day_utc.date())
                        continue

                    day_prices.append({
                        API_RESPONSE_START_TIME: start_time_utc,
                        API_RESPONSE_PRICE: price_eur_kwh,
                    })
                except (ValueError, TypeError) as e:
                    _LOGGER.warning(
                        "Could not parse price/timestamp from SMARD entry for %s, day %s: %s (entry: %s)",
                        area_code, target_day_utc.strftime('%Y-%m-%d'), e, str(point)[:50]
                    )
                    continue
            
            _LOGGER.debug("Fetched %d price points from SMARD for area %s, day %s", len(day_prices), area_code, target_day_utc.strftime('%Y-%m-%d'))
            return day_prices

        except aiohttp.ClientResponseError as e:
            if e.status == 404: # Data not yet available (common for future dates)
                _LOGGER.info(
                    "SMARD data not yet available (404) for area %s, day %s. URL: %s",
                    area_code, target_day_utc.strftime('%Y-%m-%d'), api_url
                )
            else: # Other HTTP errors
                _LOGGER.warning(
                    "HTTP error fetching SMARD data for area %s, day %s: %s - %s. URL: %s",
                    area_code, target_day_utc.strftime('%Y-%m-%d'), e.status, e.message, api_url
                )
            return [] # Return empty list on HTTP error for this day's fetch
        except aiohttp.ClientError as e: # Includes network errors, timeouts handled by ClientTimeout
            _LOGGER.warning("Client error (e.g., network, timeout) fetching SMARD data for area %s, day %s: %s. URL: %s", area_code, target_day_utc.strftime('%Y-%m-%d'), e, api_url)
            return []
        except asyncio.TimeoutError: # Explicitly catch asyncio.TimeoutError if not covered by ClientError
            _LOGGER.warning("Timeout fetching SMARD data for area %s, day %s. URL: %s", area_code, target_day_utc.strftime('%Y-%m-%d'), api_url)
            return []
        except Exception as e: # Catch any other unexpected errors during processing
            _LOGGER.error(
                "Unexpected error processing SMARD data for area %s, day %s: %s. URL: %s, Response Preview: %s",
                area_code, target_day_utc.strftime('%Y-%m-%d'), e, api_url, raw_response_preview,
                exc_info=True # Include stack trace for unexpected errors
            )
            return []


    async def fetch_data(self, area: str) -> PriceData:
        """
        Fetches SMARD market price data for the given area, covering today and tomorrow.
        SMARD data is typically available per day.
        """
        area_upper = area.upper()
        if area_upper not in _SMARD_AREA_CONFIG:
            _LOGGER.error(
                "Cannot fetch SMARD data for %s: area not configured or supported for SMARD API.", area
            )
            return PriceData(
                hourly_raw=[],
                timezone="UTC",
                currency=CURRENCY_EUR, # Default currency
                source=SOURCE_SMARD,
                meta={"error": f"Area {area} not configured/supported for SMARD API."}
            )

        current_area_config = _SMARD_AREA_CONFIG[area_upper]
        
        now_utc = datetime.now(timezone.utc)
        # SMARD data is usually published for the current day and the next day.
        # Fetch for "today" and "tomorrow" based on UTC.
        today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_utc = today_utc + timedelta(days=1)

        all_hourly_prices: List[Dict[str, Any]] = []
        
        # Fetch data for today
        prices_today = await self._fetch_smard_data_for_day(area_code=area_upper, target_day_utc=today_utc)
        all_hourly_prices.extend(prices_today)
        
        # Fetch data for tomorrow
        prices_tomorrow = await self._fetch_smard_data_for_day(area_code=area_upper, target_day_utc=tomorrow_utc)
        all_hourly_prices.extend(prices_tomorrow)

        # Sort and de-duplicate (though fetching distinct days should prevent duplicates)
        if all_hourly_prices:
            all_hourly_prices.sort(key=lambda x: x[API_RESPONSE_START_TIME])
            # Basic de-duplication, just in case of any overlap or retry logic (not present here but good practice)
            unique_prices = []
            seen_timestamps = set()
            for price_entry in all_hourly_prices:
                ts = price_entry[API_RESPONSE_START_TIME]
                if ts not in seen_timestamps:
                    unique_prices.append(price_entry)
                    seen_timestamps.add(ts)
            all_hourly_prices = unique_prices

        if not all_hourly_prices:
            _LOGGER.info("No SMARD data successfully fetched for area %s for %s and %s.", 
                         area_upper, today_utc.strftime('%Y-%m-%d'), tomorrow_utc.strftime('%Y-%m-%d'))
            # Return PriceData with info, not an error, if fetches completed but yielded no data (e.g., all 404s)
            return PriceData(
                hourly_raw=[],
                timezone="UTC", # Data is processed into UTC
                currency=current_area_config["currency"],
                source=SOURCE_SMARD,
                meta={"info": f"No data available or fetched for {area_upper} for relevant period."}
            )

        _LOGGER.info("Successfully processed %d unique hourly price points from SMARD for %s.", len(all_hourly_prices), area_upper)
        return PriceData(
            hourly_raw=all_hourly_prices,
            timezone="UTC", # All timestamps are UTC
            currency=current_area_config["currency"],
            source=SOURCE_SMARD,
            meta={
                "series_id": current_area_config["series_id"], 
                "region_slug": current_area_config["region_slug"],
                "days_fetched": [today_utc.strftime('%Y-%m-%d'), tomorrow_utc.strftime('%Y-%m-%d')]
            }
        )
