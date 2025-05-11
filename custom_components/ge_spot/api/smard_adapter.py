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
    SOURCE_SMARD, # This will be added to sources.py
)
from custom_components.ge_spot.utils.network import async_get_json_or_raise
from custom_components.ge_spot.utils.time import parse_iso_datetime_with_fallback

_LOGGER = logging.getLogger(__name__)

API_URL_BASE = "https://www.smard.de/app/chart_data"

# From ha_epex_spot, mapping ge-spot area codes to SMARD filter IDs
# This needs careful verification and expansion for ge-spot's area codes.
SMARD_MARKET_AREA_MAP = {
    "DE": 4169,        # DE-LU in ha_epex_spot
    "DE_LU": 4169,     # Explicit DE-LU
    "AT": 4170,
    "BE": 4996,
    "DK1": 252,
    "DK2": 253,
    "FR": 254,
    "NL": 256,
    "PL": 257,
    "CH": 259,
    # "NO2": 4997, # Example, add others as needed
}
# SMARD regions are often the same as market area codes, but sometimes more specific.
# For simplicity, we'll use the market_area as the region parameter for the API call.

@register_adapter(
    name=SOURCE_SMARD,
    regions=list(SMARD_MARKET_AREA_MAP.keys()), # Needs to align with ge-spot areas
    default_priority=40,
    currencies=[CURRENCY_EUR]
)
class SmardAdapter(BaseAPIAdapter):
    """
    Adapter for the SMARD.de API.
    Fetches day-ahead market prices for Germany and neighboring countries.
    """

    def __init__(self, hass, api_key_manager, source_name: str, market_area: str, session: aiohttp.ClientSession, **kwargs):
        super().__init__(hass, api_key_manager, source_name, market_area, session, **kwargs)
        self._smard_filter_id = SMARD_MARKET_AREA_MAP.get(self.market_area.upper())
        self._smard_region_param = self.market_area.upper() # API uses region like 'DE', 'AT'

        if not self._smard_filter_id:
            _LOGGER.error("SMARD filter ID not found for market area %s. Adapter may not work.", self.market_area)


    async def _fetch_smard_series_data(self, timestamp_key: str, resolution: str = "hour") -> List[Dict[str, Any]]:
        """Fetches data for a specific series timestamp key."""
        if not self._smard_filter_id:
            return []
            
        series_url = f"{API_URL_BASE}/{self._smard_filter_id}/{self._smard_region_param}/{self._smard_filter_id}_{self._smard_region_param}_{resolution}_{timestamp_key}.json"
        _LOGGER.debug("Fetching SMARD series data from URL: %s", series_url)
        
        try:
            data = await async_get_json_or_raise(self._session, series_url, timeout=NETWORK_TIMEOUT)
            if data and "series" in data and isinstance(data["series"], list):
                return data["series"]
            _LOGGER.warning("SMARD series data missing 'series' list or malformed: %s", data)
            return []
        except aiohttp.ClientError as e:
            _LOGGER.warning("Network error fetching SMARD series data for key %s: %s", timestamp_key, e)
            return [] # Don't let one series failure stop all if others might work
        except Exception as e:
            _LOGGER.warning("Error processing SMARD series data for key %s: %s", timestamp_key, e)
            return []


    async def async_fetch_data(self, target_datetime: datetime) -> PriceData:
        """
        Fetches SMARD data. SMARD provides data in series based on timestamps.
        We need to get the index of available timestamps first, then fetch the relevant series.
        """
        if not self._smard_filter_id:
            _LOGGER.error("Cannot fetch SMARD data for %s: filter ID is missing.", self.market_area)
            return PriceData(hourly_raw=[], timezone="UTC", currency=CURRENCY_EUR, source=self.source_name)

        resolution = "hour" # SMARD also has "quarterhour"
        index_url = f"{API_URL_BASE}/{self._smard_filter_id}/{self._smard_region_param}/index_{resolution}.json"
        _LOGGER.debug("Fetching SMARD index from URL: %s", index_url)

        try:
            index_data = await async_get_json_or_raise(self._session, index_url, timeout=NETWORK_TIMEOUT)
            if not index_data or "timestamps" not in index_data or not isinstance(index_data["timestamps"], list):
                _LOGGER.error("SMARD index data malformed or missing timestamps: %s", index_data)
                return PriceData(hourly_raw=[], timezone="UTC", currency=CURRENCY_EUR, source=self.source_name)

            # Fetch the last 2 or 3 series to cover today and tomorrow, as per ha_epex_spot logic.
            # The number of series to fetch might need adjustment based on how SMARD structures its data updates.
            # target_datetime helps decide which series are relevant, but SMARD's structure is primary.
            # For simplicity, fetch the latest few.
            num_series_to_fetch = 3 
            timestamp_keys_to_fetch = index_data["timestamps"][-num_series_to_fetch:]
            
            all_series_entries: List[Dict[str, Any]] = []
            fetch_tasks = [self._fetch_smard_series_data(key, resolution) for key in timestamp_keys_to_fetch]
            results = await asyncio.gather(*fetch_tasks)
            for series_entries in results:
                all_series_entries.extend(series_entries)

            if not all_series_entries:
                _LOGGER.warning("No series data successfully fetched from SMARD for %s.", self.market_area)
                return PriceData(hourly_raw=[], timezone="UTC", currency=CURRENCY_EUR, source=self.source_name)

            hourly_prices: List[Dict[str, Any]] = []
            processed_timestamps = set()

            for entry in all_series_entries:
                # SMARD entry is a list: [timestamp_ms, price_eur_mwh]
                if not isinstance(entry, list) or len(entry) < 2 or entry[1] is None: # Price can be None
                    _LOGGER.warning("Skipping malformed or null price entry from SMARD: %s", entry)
                    continue

                timestamp_ms = entry[0]
                price_eur_mwh = float(entry[1])
                price_eur_kwh = round(price_eur_mwh / 1000.0, 5)

                start_time_utc = datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc)

                # Avoid duplicates if series overlap
                if start_time_utc in processed_timestamps:
                    continue
                processed_timestamps.add(start_time_utc)

                hourly_prices.append({
                    API_RESPONSE_START_TIME: start_time_utc,
                    API_RESPONSE_PRICE: price_eur_kwh,
                })
            
            # Sort by time as data from multiple series might be out of order
            hourly_prices.sort(key=lambda x: x[API_RESPONSE_START_TIME])
            
            # SMARD data can be sparse or have gaps.
            # ge-spot's DataProcessor is expected to handle interpolation or gap filling if needed.
            # Adapter provides raw points.

            _LOGGER.info("Successfully processed %d unique price points from SMARD for %s", len(hourly_prices), self.market_area)
            return PriceData(
                hourly_raw=hourly_prices,
                timezone="UTC", # SMARD timestamps are UTC
                currency=CURRENCY_EUR,
                source=self.source_name,
                meta={"api_url_base": API_URL_BASE, "raw_unit": "EUR/MWh"}
            )

        except aiohttp.ClientError as e:
            _LOGGER.error("Network error fetching SMARD data for %s: %s", self.market_area, e)
            raise
        except Exception as e:
            _LOGGER.error("Error processing SMARD data for %s: %s", self.market_area, e)
            raise

    @property
    def name(self) -> str:
        return f"SMARD.de ({self.market_area})"
