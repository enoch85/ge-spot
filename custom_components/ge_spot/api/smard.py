import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

import aiohttp

from custom_components.ge_spot.api.base_adapter import BaseAPIAdapter, PriceData
from custom_components.ge_spot.api.registry import register_adapter
from custom_components.ge_spot.const import (
    API_RESPONSE_PRICE,
    API_RESPONSE_START_TIME,
    CURRENCY_EUR,
    NETWORK_TIMEOUT,
    SOURCE_SMARD,
)
# Assuming these utils exist and are importable
from custom_components.ge_spot.utils.network import async_get_json_or_raise
from custom_components.ge_spot.utils.time import parse_iso_datetime_with_fallback

_LOGGER = logging.getLogger(__name__)

SMARD_API_URL_BASE = "https://www.smard.de/app/chart_data"

# Based on ha_epex_spot/EPEXSpot/SMARD/__init__.py MARKET_AREA_MAP
# and ge-spot's area naming conventions.
SMARD_MARKET_CONFIG = {
    "DE-LU": {"filter_id": 4169, "region_code": "DE-LU", "timezone_hint": "Europe/Berlin"},
    "AT":    {"filter_id": 4170, "region_code": "AT", "timezone_hint": "Europe/Vienna"},
    "BE":    {"filter_id": 4996, "region_code": "BE", "timezone_hint": "Europe/Brussels"},
    "DK1":   {"filter_id": 252,  "region_code": "DK1", "timezone_hint": "Europe/Copenhagen"},
    "DK2":   {"filter_id": 253,  "region_code": "DK2", "timezone_hint": "Europe/Copenhagen"},
    "FR":    {"filter_id": 254,  "region_code": "FR", "timezone_hint": "Europe/Paris"},
    "NL":    {"filter_id": 256,  "region_code": "NL", "timezone_hint": "Europe/Amsterdam"},
    "NO2":   {"filter_id": 4997, "region_code": "NO2", "timezone_hint": "Europe/Oslo"},
    "PL":    {"filter_id": 257,  "region_code": "PL", "timezone_hint": "Europe/Warsaw"},
    "CH":    {"filter_id": 259,  "region_code": "CH", "timezone_hint": "Europe/Zurich"},
    "SI":    {"filter_id": 260,  "region_code": "SI", "timezone_hint": "Europe/Ljubljana"},
    "CZ":    {"filter_id": 261,  "region_code": "CZ", "timezone_hint": "Europe/Prague"},
    "HU":    {"filter_id": 262,  "region_code": "HU", "timezone_hint": "Europe/Budapest"},
    "IT-NO": {"filter_id": 255,  "region_code": "IT", "timezone_hint": "Europe/Rome"},
}

SMARD_RESOLUTION = "hour"

@register_adapter(
    name=SOURCE_SMARD,
    regions=list(SMARD_MARKET_CONFIG.keys()),
    default_priority=40
)
class SmardAdapter(BaseAPIAdapter):
    """
    Adapter for the SMARD.de API.
    Fetches day-ahead market prices for Germany and neighboring countries.
    """

    def __init__(self, hass, api_key_manager, source_name: str, market_area: str, session: aiohttp.ClientSession, **kwargs):
        super().__init__(hass, api_key_manager, source_name, market_area, session, **kwargs)
        # filter_id and region_param are determined in async_fetch_data

    async def _fetch_smard_series_data(self, timestamp_key: str, resolution: str, smard_filter_id: int, smard_region_param: str) -> List[Dict[str, Any]]:
        """Fetches data for a specific series timestamp key."""
        series_url = f"{SMARD_API_URL_BASE}/{smard_filter_id}/{smard_region_param}/{smard_filter_id}_{smard_region_param}_{resolution}_{timestamp_key}.json"
        _LOGGER.debug("Fetching SMARD series data from URL: %s", series_url)
        
        try:
            data = await async_get_json_or_raise(self._session, series_url, timeout=NETWORK_TIMEOUT)
            if data and "series" in data and isinstance(data["series"], list):
                return data["series"]
            _LOGGER.warning("SMARD series data missing 'series' list or malformed for key %s, area %s: %s", timestamp_key, self.market_area, str(data)[:200])
            return []
        except aiohttp.ClientError as e:
            _LOGGER.warning("Network error fetching SMARD series data for key %s, area %s: %s", timestamp_key, self.market_area, e)
            return [] 
        except Exception as e:
            _LOGGER.warning("Error processing SMARD series data for key %s, area %s: %s", timestamp_key, self.market_area, e)
            return []

    async def async_fetch_data(self, target_datetime: datetime) -> PriceData:
        """
        Fetches SMARD data. SMARD provides data in series based on timestamps.
        We need to get the index of available timestamps first, then fetch the relevant series.
        """
        market_config = SMARD_MARKET_CONFIG.get(self.market_area.upper())
        if not market_config:
            _LOGGER.error("Cannot fetch SMARD data for %s: market area configuration is missing.", self.market_area)
            return PriceData(hourly_raw=[], timezone="UTC", currency=CURRENCY_EUR, source=self.source_name, meta={"error": f"Market area {self.market_area} not configured for SMARD"})

        smard_filter_id = market_config["filter_id"]
        smard_region_param = market_config["region_code"] # This is the part like 'DE-LU', 'AT', 'IT'
        resolution = SMARD_RESOLUTION

        index_url = f"{SMARD_API_URL_BASE}/{smard_filter_id}/{smard_region_param}/index_{resolution}.json"
        _LOGGER.debug("Fetching SMARD index for area %s from URL: %s", self.market_area, index_url)

        raw_index_data_preview = None
        try:
            index_data = await async_get_json_or_raise(self._session, index_url, timeout=NETWORK_TIMEOUT)
            raw_index_data_preview = str(index_data)[:200]

            if not index_data or "timestamps" not in index_data or not isinstance(index_data["timestamps"], list) or not index_data["timestamps"]:
                _LOGGER.error("SMARD index data malformed, missing timestamps, or empty for %s: %s", self.market_area, raw_index_data_preview)
                return PriceData(hourly_raw=[], timezone=market_config.get("timezone_hint", "UTC"), currency=CURRENCY_EUR, source=self.source_name, meta={"api_url_base": SMARD_API_URL_BASE, "error": "Malformed or empty index data", "raw_response_preview": raw_index_data_preview})

            # Fetch the last 3 series to cover today and tomorrow, as per ha_epex_spot logic and SMARD behavior.
            num_series_to_fetch = 3 
            if len(index_data["timestamps"]) < num_series_to_fetch:
                timestamp_keys_to_fetch = index_data["timestamps"]
                _LOGGER.debug("Found only %d series for %s, fetching all.", len(index_data["timestamps"]), self.market_area)
            else:
                timestamp_keys_to_fetch = index_data["timestamps"][-num_series_to_fetch:]
            
            all_series_entries: List[Dict[str, Any]] = []
            fetch_tasks = [self._fetch_smard_series_data(key, resolution, smard_filter_id, smard_region_param) for key in timestamp_keys_to_fetch]
            results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

            for i, result_item in enumerate(results):
                if isinstance(result_item, Exception):
                    _LOGGER.warning(f"Error fetching SMARD series for key {timestamp_keys_to_fetch[i]}, area {self.market_area}: {result_item}")
                elif result_item: 
                    all_series_entries.extend(result_item)

            if not all_series_entries:
                _LOGGER.warning("No series data successfully fetched from SMARD for %s after trying %d keys.", self.market_area, len(timestamp_keys_to_fetch))
                return PriceData(hourly_raw=[], timezone=market_config.get("timezone_hint", "UTC"), currency=CURRENCY_EUR, source=self.source_name, meta={"api_url_base": SMARD_API_URL_BASE, "error": "No series data fetched", "raw_index_preview": raw_index_data_preview})

            hourly_prices: List[Dict[str, Any]] = []
            processed_timestamps = set()

            for entry in all_series_entries:
                if not isinstance(entry, list) or len(entry) < 2 or entry[0] is None or entry[1] is None: # Price and timestamp must exist
                    _LOGGER.warning("Skipping malformed or null price/timestamp entry from SMARD for %s: %s", self.market_area, entry)
                    continue

                try:
                    timestamp_ms = int(entry[0])
                    price_eur_mwh = float(entry[1])
                except (ValueError, TypeError) as e:
                    _LOGGER.warning("Could not parse timestamp/price from SMARD entry for %s: %s (entry: %s)", self.market_area, e, entry)
                    continue
                
                price_eur_kwh = round(price_eur_mwh / 1000.0, 5)
                start_time_utc = datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc)

                if start_time_utc in processed_timestamps:
                    continue
                processed_timestamps.add(start_time_utc)

                hourly_prices.append({
                    API_RESPONSE_START_TIME: start_time_utc,
                    API_RESPONSE_PRICE: price_eur_kwh,
                })
            
            hourly_prices.sort(key=lambda x: x[API_RESPONSE_START_TIME])
            
            _LOGGER.info("Successfully processed %d unique price points from SMARD for %s", len(hourly_prices), self.market_area)
            return PriceData(
                hourly_raw=hourly_prices,
                timezone=market_config.get("timezone_hint", "UTC"), # Use timezone hint from config
                currency=CURRENCY_EUR,
                source=self.source_name,
                meta={"api_url_base": SMARD_API_URL_BASE, "raw_unit": "EUR/MWh", "raw_index_preview": raw_index_data_preview}
            )

        except aiohttp.ClientError as e:
            _LOGGER.error("Network error fetching SMARD index for %s: %s", self.market_area, e)
            # Raise network errors for FallbackManager to handle
            raise
        except Exception as e:
            _LOGGER.error("Unexpected error processing SMARD data for %s: %s. Index preview: %s", self.market_area, e, raw_index_data_preview)
            # Raise other critical errors for FallbackManager
            raise

    @property
    def name(self) -> str:
        return f"SMARD.de ({self.market_area})"
