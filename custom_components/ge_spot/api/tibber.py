import asyncio
import logging
from datetime import datetime, timezone # Removed timedelta as it's not directly used here
from typing import Any, Dict, List

import aiohttp

from .base_api import BaseAPI, PriceData # Changed from BaseAPIAdapter
from .registry import register_api # Changed from register_adapter
from ..const import (
    API_RESPONSE_PRICE,
    API_RESPONSE_START_TIME,
    NETWORK_TIMEOUT,
)
from ..const.sources import SOURCE_TIBBER # Ensure this is defined in const.sources
from ..utils.time import parse_iso_datetime_with_fallback

_LOGGER = logging.getLogger(__name__)

TIBBER_GQL_API_URL = "https://api.tibber.com/v1-beta/gql"

# This query is from ha_epex_spot Tibber component and existing ge-spot adapter
TIBBER_GRAPHQL_QUERY = """
{
  viewer {
    homes {
      currentSubscription{
        priceInfo{
          today {
            total
            energy
            tax
            startsAt
            currency
          }
          tomorrow {
            total
            energy
            tax
            startsAt
            currency
          }
        }
      }
    }
  }
}
"""

# GE-Spot regions that Tibber might support. Token will determine actual availability.
# Used for registration purposes.
TIBBER_REGIONS_FOR_REGISTRATION = [
    "DE-LU", "NL", "NO1", "NO2", "NO3", "NO4", "NO5", "SE1", "SE2", "SE3", "SE4", "AT", "BE", "FR"
] # Expanded list based on common European areas

@register_api(
    name=SOURCE_TIBBER,
    regions=TIBBER_REGIONS_FOR_REGISTRATION,
    default_priority=20 # High priority as it's often user-specific and direct
)
class TibberAPI(BaseAPI): # Changed from TibberAdapter and BaseAPIAdapter
    """
    API for Tibber.
    Fetches personalized energy prices using GraphQL.
    Requires an API token provided in the integration's configuration.
    Tibber provides consumer prices (total); this is used for the price.
    """

    def __init__(self, config: Dict[str, Any], session: aiohttp.ClientSession):
        super().__init__(config, session)
        # API token should be passed in the main component configuration
        # and then into this API's config dict by the integration setup.
        self._api_token = self._config.get("api_token") 
        if not self._api_token:
            _LOGGER.error(
                "Tibber API token not provided in configuration for source %s.", 
                SOURCE_TIBBER
            )
            # Further actions (like preventing fetch) will be handled by checks in fetch_data

    async def fetch_data(self, area: str) -> PriceData: # area is for context/logging
        """
        Fetches Tibber data using GraphQL.
        The API returns today's and tomorrow's prices if available, specific to the token's home.
        The 'area' parameter is mainly for logging and consistency with BaseAPI.
        """
        if not self._api_token:
            _LOGGER.warning("Cannot fetch Tibber data: API token is missing. Area: %s", area)
            return PriceData(hourly_raw=[], timezone="UTC", currency="", source=SOURCE_TIBBER, meta={"error": "API token missing", "area": area})

        payload = {"query": TIBBER_GRAPHQL_QUERY}
        headers = {"Authorization": f"Bearer {self._api_token}"}

        _LOGGER.debug("Fetching Tibber data (area: %s)", area)

        raw_response_preview = None
        api_currency = "" # Placeholder, determined from the first valid API response entry

        try:
            async with self._session.post(
                TIBBER_GQL_API_URL,
                json=payload, # GraphQL uses JSON payload
                headers=headers,
                timeout=NETWORK_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    _LOGGER.error(
                        "Error fetching Tibber data: %s - %s. Area: %s",
                        resp.status, error_text[:200], area
                    )
                    resp.raise_for_status() # Let aiohttp handle non-200 as an exception
                
                json_response = await resp.json()
                raw_response_preview = str(json_response)[:300]

            if "errors" in json_response and json_response["errors"]:
                _LOGGER.error("Tibber API returned GraphQL errors: %s. Area: %s", json_response["errors"], area)
                return PriceData(hourly_raw=[], timezone="UTC", currency=api_currency, source=SOURCE_TIBBER, meta={"error": "GraphQL API error", "details": json_response["errors"], "raw_response_preview": raw_response_preview, "area": area})

            # Navigate through the GraphQL response structure
            homes = json_response.get("data", {}).get("viewer", {}).get("homes")
            if not homes or not isinstance(homes, list) or not homes[0]:
                _LOGGER.warning("No homes found in Tibber response for area %s. Ensure token has access. Response: %s", area, raw_response_preview)
                return PriceData(hourly_raw=[], timezone="UTC", currency=api_currency, source=SOURCE_TIBBER, meta={"error": "No homes data in response", "raw_response_preview": raw_response_preview, "area": area})

            price_info = homes[0].get("currentSubscription", {}).get("priceInfo")
            if not price_info:
                _LOGGER.warning("No priceInfo found in Tibber response for area %s. Response: %s", area, raw_response_preview)
                return PriceData(hourly_raw=[], timezone="UTC", currency=api_currency, source=SOURCE_TIBBER, meta={"error": "No priceInfo in response", "raw_response_preview": raw_response_preview, "area": area})

            api_entries = []
            if price_info.get("today") and isinstance(price_info["today"], list):
                api_entries.extend(price_info["today"])
            if price_info.get("tomorrow") and isinstance(price_info["tomorrow"], list):
                api_entries.extend(price_info["tomorrow"])

            if not api_entries:
                _LOGGER.info("No price entries (today/tomorrow) found in Tibber response for area %s.", area)
                return PriceData(hourly_raw=[], timezone="UTC", currency=api_currency, source=SOURCE_TIBBER, meta={"info": "No price entries in API response", "raw_response_preview": raw_response_preview, "area": area})

            hourly_prices: List[Dict[str, Any]] = []
            processed_timestamps = set()
            
            # Determine currency from the first valid entry that has it
            for entry in api_entries:
                if entry and isinstance(entry, dict) and entry.get("currency"):
                    api_currency = entry["currency"].upper()
                    break
            if not api_currency: # Fallback if no currency found in any entry
                _LOGGER.warning("Could not determine currency from Tibber API response entries. Area: %s", area)
                # No default currency here, PriceData will reflect empty string or rely on caller to handle.

            for entry in api_entries:
                try:
                    if not isinstance(entry, dict) or entry.get("startsAt") is None or entry.get("total") is None:
                        _LOGGER.debug("Skipping Tibber entry with missing critical data: %s", entry)
                        continue

                    start_at_str = entry["startsAt"]
                    total_price_str = entry["total"]
                    entry_currency_str = entry.get("currency")

                    # Validate currency consistency if already determined
                    if api_currency and entry_currency_str and api_currency != entry_currency_str.upper():
                        _LOGGER.warning("Inconsistent currency in Tibber entry. Expected %s, got %s. Entry: %s", api_currency, entry_currency_str.upper(), entry)
                        # Potentially skip or handle as an error, for now, we log and proceed with the first currency found.
                    
                    start_time_dt = parse_iso_datetime_with_fallback(start_at_str)
                    if not start_time_dt:
                        _LOGGER.warning("Could not parse start time from Tibber entry: %s", entry)
                        continue
                    
                    start_time_utc = start_time_dt.astimezone(timezone.utc)

                    if start_time_utc in processed_timestamps:
                        _LOGGER.debug("Skipping duplicate timestamp from Tibber: %s", start_time_utc)
                        continue
                    processed_timestamps.add(start_time_utc)

                    # Price is 'total', includes taxes, in the currency reported by API (per kWh)
                    price_value = round(float(total_price_str), 5) 

                    hourly_prices.append({
                        API_RESPONSE_START_TIME: start_time_utc,
                        API_RESPONSE_PRICE: price_value,
                    })
                except (ValueError, TypeError, KeyError) as e:
                    _LOGGER.warning("Could not parse price/timestamp from Tibber entry (area %s): %s (entry: %s)", area, e, entry)
                    continue
            
            hourly_prices.sort(key=lambda x: x[API_RESPONSE_START_TIME])

            _LOGGER.info("Successfully processed %d unique hourly price points from Tibber (area: %s)", len(hourly_prices), area)
            return PriceData(
                hourly_raw=hourly_prices,
                timezone="UTC", # All start times are converted to UTC
                currency=api_currency, # Currency from API response
                source=SOURCE_TIBBER,
                meta={
                    "api_url": TIBBER_GQL_API_URL, 
                    "raw_unit_from_api": f"{api_currency}/kWh" if api_currency else "kWh", 
                    "raw_response_preview": raw_response_preview,
                    "area": area # Changed from area_hint
                    }
            )

        except aiohttp.ClientError as e:
            _LOGGER.error("Network error fetching Tibber data (area: %s): %s", area, e)
            raise # Re-raise for FallbackManager
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout fetching Tibber data (area: %s)", area)
            return PriceData(hourly_raw=[], timezone="UTC", currency=api_currency, source=SOURCE_TIBBER, meta={"error": "Timeout during API call", "api_url": TIBBER_GQL_API_URL, "area": area})
        except Exception as e:
            _LOGGER.error("Unexpected error processing Tibber data (area: %s): %s. Preview: %s", area, e, raw_response_preview)
            raise # Re-raise for FallbackManager

    # No specific 'name' property as per BaseAPI structure.
