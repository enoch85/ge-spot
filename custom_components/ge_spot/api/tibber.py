import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, cast

import aiohttp

from custom_components.ge_spot.api.base_adapter import BaseAPIAdapter, PriceData
from custom_components.ge_spot.api.registry import register_adapter
from custom_components.ge_spot.const import (
    API_RESPONSE_PRICE,
    API_RESPONSE_START_TIME,
    NETWORK_TIMEOUT,
    SOURCE_TIBBER, # This will be added to sources.py
)
from custom_components.ge_spot.const.currencies import CURRENCY_EUR, CURRENCY_NOK, CURRENCY_SEK # Added currency imports
from custom_components.ge_spot.utils.network import async_post_graphql_or_raise # Assuming a new utility for GraphQL
from custom_components.ge_spot.utils.time import parse_iso_datetime_with_fallback

_LOGGER = logging.getLogger(__name__)

TIBBER_API_URL = "https://api.tibber.com/v1-beta/gql"

# Tibber API uses a GraphQL query. The market area is implicitly determined by the API token (linked to a home).
# The currency is also returned by the API.
# We define supported regions based on where Tibber operates and GE-Spot has areas.
# Timezone is determined by the `startsAt` field which includes offset.

# This query is from ha_epex_spot Tibber component
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
# Timezone hints are for reference; API provides offset.
TIBBER_SUPPORTED_REGIONS_CONFIG = {
    "DE-LU": {"default_currency": CURRENCY_EUR, "timezone_hint": "Europe/Berlin"}, # Germany
    "NL":    {"default_currency": CURRENCY_EUR, "timezone_hint": "Europe/Amsterdam"},# Netherlands
    "NO1":   {"default_currency": CURRENCY_NOK, "timezone_hint": "Europe/Oslo"},    # Norway (example area)
    "NO2":   {"default_currency": CURRENCY_NOK, "timezone_hint": "Europe/Oslo"},
    "NO3":   {"default_currency": CURRENCY_NOK, "timezone_hint": "Europe/Oslo"},
    "NO4":   {"default_currency": CURRENCY_NOK, "timezone_hint": "Europe/Oslo"},
    "NO5":   {"default_currency": CURRENCY_NOK, "timezone_hint": "Europe/Oslo"},
    "SE1":   {"default_currency": CURRENCY_SEK, "timezone_hint": "Europe/Stockholm"}, # Sweden (example area)
    "SE2":   {"default_currency": CURRENCY_SEK, "timezone_hint": "Europe/Stockholm"},
    "SE3":   {"default_currency": CURRENCY_SEK, "timezone_hint": "Europe/Stockholm"},
    "SE4":   {"default_currency": CURRENCY_SEK, "timezone_hint": "Europe/Stockholm"},
    # Potentially others like AT, FR if Tibber expands and uses those currencies.
}

@register_adapter(
    name=SOURCE_TIBBER,
    regions=list(TIBBER_SUPPORTED_REGIONS_CONFIG.keys()),
    default_priority=80 # High, as it's often a direct user subscription
)
class TibberAdapter(BaseAPIAdapter):
    """
    Adapter for the Tibber API.
    Fetches electricity prices using GraphQL. Requires an API token.
    Tibber provides consumer prices (total, energy, tax). We will use 'energy' price.
    """

    def __init__(self, hass, api_key_manager, source_name: str, market_area: str, session: aiohttp.ClientSession, **kwargs):
        super().__init__(hass, api_key_manager, source_name, market_area, session, **kwargs)
        self._api_token = self.api_key_manager.get_api_key(self.source_name, self.market_area) # Uses source_name for key
        if not self._api_token:
            _LOGGER.error("API token for Tibber not found. Market area: %s", self.market_area)


    async def async_fetch_data(self, target_datetime: datetime) -> PriceData:
        """
        Fetches Tibber data using GraphQL.
        The API returns today's and tomorrow's prices if available.
        """
        api_token = self.api_key
        if not api_token:
            _LOGGER.error("Tibber API token is missing. Cannot fetch data.")
            # Use market_area specific default currency if available, else EUR
            default_currency = TIBBER_SUPPORTED_REGIONS_CONFIG.get(self.market_area.upper(), {}).get("default_currency", CURRENCY_EUR)
            return PriceData(hourly_raw=[], timezone="UTC", currency=default_currency, source=self.source_name, meta={"error": "API token missing"})

        payload = {"query": TIBBER_GRAPHQL_QUERY}
        auth_header = f"Bearer {api_token}"

        _LOGGER.debug("Fetching Tibber data for user associated with token (market area %s for context)", self.market_area)

        raw_response_preview = None
        api_currency = None
        try:
            json_response = await async_post_graphql_or_raise(
                self._session, TIBBER_API_URL, payload, auth_header, timeout=NETWORK_TIMEOUT
            )
            raw_response_preview = str(json_response)[:300]

            # Navigate through the GraphQL response structure
            if not json_response or "data" not in json_response or not json_response["data"]:
                _LOGGER.warning("Tibber response malformed or missing 'data': %s", raw_response_preview)
                raise ValueError("Malformed Tibber response: no data field")

            viewer = json_response["data"].get("viewer")
            if not viewer or not viewer.get("homes"):
                _LOGGER.warning("Tibber: No homes found in response for this token. Ensure token has access to a home with a subscription. Response: %s", raw_response_preview)
                # This might mean the token is valid but has no associated home/subscription for price data.
                # Return empty but not as a hard error that would trigger fallback to other sources if this is the *only* source.
                default_currency = TIBBER_SUPPORTED_REGIONS_CONFIG.get(self.market_area.upper(), {}).get("default_currency", CURRENCY_EUR)
                return PriceData(hourly_raw=[], timezone="UTC", currency=default_currency, source=self.source_name, meta={"error": "No homes with price subscription found for token", "raw_response_preview": raw_response_preview})
            
            # Assuming the first home is the relevant one, as per most Tibber integrations
            home = viewer["homes"][0]
            price_info = home.get("currentSubscription", {}).get("priceInfo")
            if not price_info:
                _LOGGER.warning("Tibber: No currentSubscription.priceInfo found for home. Response: %s", raw_response_preview)
                default_currency = TIBBER_SUPPORTED_REGIONS_CONFIG.get(self.market_area.upper(), {}).get("default_currency", CURRENCY_EUR)
                return PriceData(hourly_raw=[], timezone="UTC", currency=default_currency, source=self.source_name, meta={"error": "No priceInfo found for home subscription", "raw_response_preview": raw_response_preview})

            api_entries = []
            if "today" in price_info and price_info["today"]:
                api_entries.extend(price_info["today"])
            if "tomorrow" in price_info and price_info["tomorrow"]:
                api_entries.extend(price_info["tomorrow"])

            if not api_entries:
                _LOGGER.info("No price entries (today/tomorrow) found in Tibber response for %s.", self.market_area)
                default_currency = TIBBER_SUPPORTED_REGIONS_CONFIG.get(self.market_area.upper(), {}).get("default_currency", CURRENCY_EUR)
                return PriceData(hourly_raw=[], timezone="UTC", currency=default_currency, source=self.source_name, meta={"error": "No price entries in API response", "raw_response_preview": raw_response_preview})

            hourly_prices: List[Dict[str, Any]] = []
            processed_timestamps = set()
            
            # Determine currency from the first valid entry
            for entry in api_entries:
                if entry and "currency" in entry:
                    api_currency = entry["currency"].upper()
                    break
            if not api_currency: # Fallback if no currency found in entries
                api_currency = TIBBER_SUPPORTED_REGIONS_CONFIG.get(self.market_area.upper(), {}).get("default_currency", CURRENCY_EUR)
                _LOGGER.warning("Could not determine currency from Tibber API response, defaulting to %s for area %s", api_currency, self.market_area)

            for entry in api_entries:
                try:
                    if not entry or "startsAt" not in entry or "total" not in entry or entry["total"] is None:
                        _LOGGER.debug("Skipping Tibber entry with missing critical data: %s", entry)
                        continue

                    start_time_str = entry["startsAt"]
                    price_value_str = entry["total"]
                    
                    start_time_dt = parse_iso_datetime_with_fallback(start_time_str)
                    if not start_time_dt:
                        _LOGGER.warning("Could not parse start time from Tibber entry: %s", entry)
                        continue
                    
                    start_time_utc = start_time_dt.astimezone(timezone.utc)

                    if start_time_utc in processed_timestamps:
                        _LOGGER.debug("Skipping duplicate timestamp from Tibber: %s", start_time_utc)
                        continue
                    processed_timestamps.add(start_time_utc)

                    # Price is total, includes tax, in the currency reported by API
                    price_value = round(float(price_value_str), 5) 

                    hourly_prices.append({
                        API_RESPONSE_START_TIME: start_time_utc,
                        API_RESPONSE_PRICE: price_value,
                    })
                except (ValueError, TypeError, KeyError) as e:
                    _LOGGER.warning("Could not parse price/timestamp from Tibber entry for %s: %s (entry: %s)", self.market_area, e, entry)
                    continue
            
            hourly_prices.sort(key=lambda x: x[API_RESPONSE_START_TIME])

            _LOGGER.info("Successfully processed %d unique price points from Tibber for %s", len(hourly_prices), self.market_area)
            return PriceData(
                hourly_raw=hourly_prices,
                timezone="UTC", # Data is converted to UTC start times
                currency=api_currency, # Currency from API response
                source=self.source_name,
                meta={"api_url": TIBBER_API_URL, "raw_unit": f"{api_currency}/kWh", "raw_response_preview": raw_response_preview}
            )

        except aiohttp.ClientError as e:
            _LOGGER.error("Network error fetching Tibber data for %s: %s", self.market_area, e)
            raise
        except ValueError as e: # Catch specific errors like malformed JSON or structure issues
            _LOGGER.error("Data error processing Tibber response for %s: %s. Preview: %s", self.market_area, e, raw_response_preview)
            # For data errors that are not network related, we might not want to fall back if Tibber is the primary choice.
            # However, returning an empty PriceData with error meta is safer.
            default_currency = TIBBER_SUPPORTED_REGIONS_CONFIG.get(self.market_area.upper(), {}).get("default_currency", CURRENCY_EUR)
            return PriceData(hourly_raw=[], timezone="UTC", currency=default_currency, source=self.source_name, meta={"error": str(e), "raw_response_preview": raw_response_preview})
        except Exception as e:
            _LOGGER.error("Unexpected error processing Tibber data for %s: %s. Preview: %s", self.market_area, e, raw_response_preview)
            raise

    @property
    def name(self) -> str:
        return f"Tibber ({self.market_area})"
