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
    # Tibber returns prices in local currency (EUR, SEK, NOK)
    # CURRENCY_EUR, CURRENCY_NOK, CURRENCY_SEK will be needed
    NETWORK_TIMEOUT,
    SOURCE_TIBBER, # This will be added to sources.py
)
from custom_components.ge_spot.utils.network import async_post_json_or_raise # Assuming this utility
from custom_components.ge_spot.utils.time import parse_iso_datetime_with_fallback

_LOGGER = logging.getLogger(__name__)

API_URL = "https://api.tibber.com/v1-beta/gql"
TIBBER_QUERY = """
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
# Tibber market areas from ha_epex_spot
TIBBER_MARKET_AREAS = ["DE", "NL", "NO", "SE"] # Needs mapping to ge-spot area codes

@register_adapter(
    name=SOURCE_TIBBER,
    regions=TIBBER_MARKET_AREAS, # Map to ge-spot area codes
    default_priority=50,
    # Currencies depend on the market area, adapter will determine from response
    currencies=["EUR", "NOK", "SEK"], # List all possible
    requires_api_key=True
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
        Fetches electricity prices for today and tomorrow.
        """
        if not self._api_token:
            _LOGGER.warning("Cannot fetch Tibber data for %s: API token is missing.", self.market_area)
            # Return empty with a placeholder currency, actual currency unknown without API call
            return PriceData(hourly_raw=[], timezone="Europe/Oslo", currency="EUR", source=self.source_name) 

        headers = {"Authorization": f"Bearer {self._api_token}"}
        payload = {"query": TIBBER_QUERY}
        _LOGGER.debug("Fetching Tibber data for %s. URL: %s", self.market_area, API_URL)

        try:
            response_data = await async_post_json_or_raise(self._session, API_URL, headers=headers, json_payload=payload, timeout=NETWORK_TIMEOUT)

            if (not response_data or "data" not in response_data or
                not response_data["data"].get("viewer") or not response_data["data"]["viewer"].get("homes")):
                _LOGGER.error("Tibber API returned no data or unexpected format: %s", response_data)
                return PriceData(hourly_raw=[], timezone="Europe/Oslo", currency="EUR", source=self.source_name)

            homes = response_data["data"]["viewer"]["homes"]
            if not homes or not homes[0].get("currentSubscription") or not homes[0]["currentSubscription"].get("priceInfo"):
                _LOGGER.error("Tibber API: No priceInfo found in response: %s", response_data)
                return PriceData(hourly_raw=[], timezone="Europe/Oslo", currency="EUR", source=self.source_name)

            price_info = homes[0]["currentSubscription"]["priceInfo"]
            api_prices_today = price_info.get("today", [])
            api_prices_tomorrow = price_info.get("tomorrow", [])
            
            all_api_prices = api_prices_today + api_prices_tomorrow
            hourly_prices: List[Dict[str, Any]] = []
            source_currency = "EUR" # Default, will be updated from first valid entry
            source_timezone_str = "Europe/Oslo" # Default, Tibber times are usually local to home

            if not all_api_prices:
                 _LOGGER.warning("Tibber API returned no price entries for today or tomorrow for %s.", self.market_area)


            for entry_idx, entry in enumerate(all_api_prices):
                if not all(k in entry for k in ["startsAt", "energy", "currency"]):
                    _LOGGER.warning("Skipping malformed entry from Tibber: %s", entry)
                    continue
                
                start_time_str = entry["startsAt"] # ISO 8601 format, e.g., "2023-10-27T00:00:00.000+02:00"
                price_value = float(entry["energy"]) # Use 'energy' component as per plan
                
                current_currency = entry["currency"].upper()
                if entry_idx == 0: # Set currency from the first entry
                    source_currency = current_currency

                start_time = parse_iso_datetime_with_fallback(start_time_str)
                if start_time is None:
                    _LOGGER.warning("Could not parse startsAt from Tibber entry: %s", entry)
                    continue
                
                # Determine source timezone from the first valid entry's offset if possible
                if entry_idx == 0 and start_time.tzinfo:
                    # This gets the specific tz, e.g. CET, CEST. For consistency, use a fixed zone name.
                    # Example: For a +02:00 offset in summer, it could be Europe/Berlin or Europe/Oslo.
                    # Tibber operates in specific countries, so we can infer.
                    # For simplicity, we'll use a common one for now, but this could be market_area dependent.
                    # The parse_iso_datetime_with_fallback should ideally give tz-aware datetime.
                    # We need to report the original timezone context to ge-spot.
                    # Let's assume the parsed `start_time` is already timezone-aware.
                    # The `source_timezone_str` will be the IANA name.
                    # This part is tricky without knowing the exact home location's timezone IANA name.
                    # For now, we'll assume the parsed `start_time` is correct and convert to UTC.
                    pass


                # Ensure start_time is UTC for internal consistency
                # parse_iso_datetime_with_fallback should return tz-aware if offset is present.
                start_time_utc = start_time.astimezone(timezone.utc)
                
                # Store the original timezone string from the first entry that has it.
                # This is a bit of a guess; ideally, Tibber API would state the home's IANA timezone.
                if entry_idx == 0 and start_time.tzinfo:
                    # Try to infer a general IANA timezone based on country.
                    # This is a simplification.
                    if self.market_area.upper() == "DE": source_timezone_str = "Europe/Berlin"
                    elif self.market_area.upper() == "NL": source_timezone_str = "Europe/Amsterdam"
                    elif self.market_area.upper() == "SE": source_timezone_str = "Europe/Stockholm"
                    elif self.market_area.upper() == "NO": source_timezone_str = "Europe/Oslo"


                hourly_prices.append({
                    API_RESPONSE_START_TIME: start_time_utc, # Store as UTC
                    API_RESPONSE_PRICE: round(price_value, 5),
                })
            
            _LOGGER.info("Successfully fetched %d price points from Tibber for %s", len(hourly_prices), self.market_area)
            return PriceData(
                hourly_raw=hourly_prices,
                timezone=source_timezone_str, # Original timezone context
                currency=source_currency,
                source=self.source_name,
                meta={"api_url": API_URL, "raw_unit": f"{source_currency}/kWh", "price_type": "energy_component"}
            )

        except aiohttp.ClientError as e:
            _LOGGER.error("Network error fetching Tibber data for %s: %s", self.market_area, e)
            raise
        except Exception as e:
            _LOGGER.error("Error processing Tibber data for %s: %s", self.market_area, e)
            raise

    @property
    def name(self) -> str:
        return f"Tibber ({self.market_area})"
