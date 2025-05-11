import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import aiohttp
from bs4 import BeautifulSoup

from custom_components.ge_spot.api.base_adapter import BaseAPIAdapter, PriceData
from custom_components.ge_spot.api.registry import register_adapter
from custom_components.ge_spot.const import (
    API_RESPONSE_PRICE,
    API_RESPONSE_START_TIME,
    CURRENCY_EUR,
    CURRENCY_GBP,
    NETWORK_TIMEOUT,
    SOURCE_EPEX_SPOT_WEB, # Will be added to const/sources.py
)
# Assuming these utils exist and are importable
from custom_components.ge_spot.utils.network import async_get_json_or_raise # Though this is for JSON, we'll adapt or make a new one for HTML
from custom_components.ge_spot.utils.time import parse_iso_datetime_with_fallback, get_area_timezone

_LOGGER = logging.getLogger(__name__)

EPEX_SPOT_WEB_API_URL = "https://www.epexspot.com/en/market-results"

# Mapping from ge-spot market areas to EPEX Spot Web specific parameters
# Based on ha_epex_spot/custom_components/epex_spot/EPEXSpot/EPEXSpotWeb/__init__.py
EPEX_SPOT_WEB_MARKET_CONFIG = {
    # Areas with 60 min products, auction "MRC" (default)
    "AT":    {"auction": "MRC", "api_market_area": "AT",    "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Vienna"},
    "BE":    {"auction": "MRC", "api_market_area": "BE",    "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Brussels"},
    "DE-LU": {"auction": "MRC", "api_market_area": "DE-LU", "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Berlin"}, # Assuming DE-LU uses Berlin time for EPEX
    "DK1":   {"auction": "MRC", "api_market_area": "DK1",   "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Copenhagen"},
    "DK2":   {"auction": "MRC", "api_market_area": "DK2",   "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Copenhagen"},
    "FI":    {"auction": "MRC", "api_market_area": "FI",    "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Helsinki"},
    "FR":    {"auction": "MRC", "api_market_area": "FR",    "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Paris"},
    "NL":    {"auction": "MRC", "api_market_area": "NL",    "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Amsterdam"},
    "NO1":   {"auction": "MRC", "api_market_area": "NO1",   "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Oslo"},
    "NO2":   {"auction": "MRC", "api_market_area": "NO2",   "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Oslo"},
    "NO3":   {"auction": "MRC", "api_market_area": "NO3",   "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Oslo"},
    "NO4":   {"auction": "MRC", "api_market_area": "NO4",   "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Oslo"},
    "NO5":   {"auction": "MRC", "api_market_area": "NO5",   "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Oslo"},
    "PL":    {"auction": "MRC", "api_market_area": "PL",    "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Warsaw"},
    "SE1":   {"auction": "MRC", "api_market_area": "SE1",   "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Stockholm"},
    "SE2":   {"auction": "MRC", "api_market_area": "SE2",   "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Stockholm"},
    "SE3":   {"auction": "MRC", "api_market_area": "SE3",   "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Stockholm"},
    "SE4":   {"auction": "MRC", "api_market_area": "SE4",   "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Stockholm"},
    # Special market areas from the source code
    "GB":    {"auction": "GB",  "api_market_area": "GB",    "duration": 60, "currency": CURRENCY_GBP, "timezone_hint": "Europe/London"},
    "CH":    {"auction": "CH",  "api_market_area": "CH",    "duration": 60, "currency": CURRENCY_EUR, "timezone_hint": "Europe/Zurich"},
    # "GB-30": {"auction": "30-call-GB", "api_market_area": "GB", "duration": 30, "currency": CURRENCY_GBP, "timezone_hint": "Europe/London"}, # 30 min product, might need different handling or be out of scope for hourly prices
}

def _to_epex_date_string(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

def _parse_epex_price(price_str: str) -> float:
    return float(price_str.replace(",", ""))

async def _async_post_form_and_get_json_or_raise(
    session: aiohttp.ClientSession,
    url: str,
    params: Dict[str, Any],
    data: Dict[str, Any],
    timeout: int = NETWORK_TIMEOUT,
) -> Any:
    """Perform an async POST request with form data, expect JSON commands back."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0", # Updated User-Agent
        "X-Requested-With": "XMLHttpRequest", # Often used for AJAX requests
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    try:
        async with session.post(url, params=params, data=data, headers=headers, timeout=timeout, verify_ssl=True) as response:
            response.raise_for_status()
            return await response.json()
    except asyncio.TimeoutError:
        _LOGGER.warning("Timeout error posting form data to %s with params %s", url, params)
        raise
    except aiohttp.ClientResponseError as e:
        _LOGGER.warning("HTTP error %s posting form data to %s with params %s: %s", e.status, url, params, e.message)
        raise
    except aiohttp.ClientError as e:
        _LOGGER.warning("Client error posting form data to %s with params %s: %s", url, params, e)
        raise
    except Exception as e:
        _LOGGER.warning("Unexpected error posting form data to %s with params %s: %s", url, params, e)
        raise

@register_adapter(
    name=SOURCE_EPEX_SPOT_WEB,
    regions=list(EPEX_SPOT_WEB_MARKET_CONFIG.keys()),
    default_priority=60, # Arbitrary, can be adjusted
)
class EpexSpotWebAdapter(BaseAPIAdapter):
    """
    Adapter for the EPEX Spot website scraper.
    Fetches day-ahead market prices by simulating form submissions.
    """

    def __init__(self, hass, api_key_manager, source_name: str, market_area: str, session: aiohttp.ClientSession, **kwargs):
        super().__init__(hass, api_key_manager, source_name, market_area, session, **kwargs)
        self._market_config = EPEX_SPOT_WEB_MARKET_CONFIG.get(self.market_area.upper())

    async def _fetch_day_data(self, delivery_date_local: datetime) -> List[Dict[str, Any]]:
        """Fetches and parses data for a single delivery day."""
        if not self._market_config:
            # This should ideally be caught in __init__ or async_fetch_data before calling this.
            _LOGGER.error("EPEX Spot Web: Market area %s not configured.", self.market_area)
            return []

        trading_date_local = delivery_date_local - timedelta(days=1)
        
        # These parameters are based on the ha_epex_spot component's structure
        params_query = {
            "market_area": self._market_config["api_market_area"],
            "trading_date": _to_epex_date_string(trading_date_local),
            "delivery_date": _to_epex_date_string(delivery_date_local),
            "auction": self._market_config["auction"],
            "modality": "Auction",
            "sub_modality": "DayAhead",
            "product": self._market_config["duration"],
            "data_mode": "table",
            "ajax_form": "1",
            "_wrapper_format": "drupal_ajax", # Added based on inspection of typical Drupal AJAX requests
        }
        
        form_data_payload = {
            "form_id": "market_data_filters_form",
            "_triggering_element_name": "submit_js", # Or could be specific like 'filters[market_area]'
            "_drupal_ajax": "1",
            # Potentially include current values of all filters if required by the backend
            f"filters[market_area]": self._market_config["api_market_area"],
            f"filters[modality]": "Auction",
            f"filters[sub_modality]": "DayAhead",
            f"filters[product]": str(self._market_config["duration"]),
            f"filters[delivery_date]": _to_epex_date_string(delivery_date_local),
        }

        _LOGGER.debug(
            "Fetching EPEX Spot Web for area %s, delivery %s. Params: %s, Payload: %s", 
            self.market_area, delivery_date_local.date(), params_query, form_data_payload
        )

        try:
            json_commands = await _async_post_form_and_get_json_or_raise(
                self._session, EPEX_SPOT_WEB_API_URL, params=params_query, data=form_data_payload
            )
        except Exception as e:
            _LOGGER.warning("Failed to fetch EPEX Spot Web data for %s, delivery %s: %s", self.market_area, delivery_date_local.date(), e)
            return []

        html_content = None
        if isinstance(json_commands, list):
            for command in json_commands:
                if command.get("command") == "invoke" and command.get("selector") == ".js-md-widget" and "args" in command:
                    html_content = command["args"][0]
                    break
                elif command.get("command") == "insert" and command.get("selector") == ".js-md-widget-table-wrapper": # Alternative selector
                    html_content = command["data"]
                    break
        
        if not html_content:
            _LOGGER.debug("No table data found in EPEX Spot Web response for %s, delivery %s. Response: %s", self.market_area, delivery_date_local.date(), str(json_commands)[:500])
            return []

        soup = BeautifulSoup(html_content, features="html.parser")
        table = soup.find("table", class_="table-01") # table-length-1 seems too specific

        if not table:
            _LOGGER.warning("Could not find price table in EPEX Spot Web HTML for %s, delivery %s", self.market_area, delivery_date_local.date())
            return []
        
        body = table.tbody
        if not body:
            _LOGGER.warning("Could not find table body in EPEX Spot Web HTML for %s, delivery %s", self.market_area, delivery_date_local.date())
            return []

        rows = body.find_all("tr")
        if not rows:
            _LOGGER.debug("No rows found in price table for %s, delivery %s", self.market_area, delivery_date_local.date())
            return []

        hourly_prices: List[Dict[str, Any]] = []
        # The delivery_date_local is in the market's local timezone (e.g., Europe/Paris for FR)
        # We need to construct UTC timestamps for the PriceData object.
        market_timezone = get_area_timezone(self._market_config["timezone_hint"]) # Use the hint for the market's local time
        
        current_hour_start_local = delivery_date_local.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=market_timezone)

        for row_idx, row in enumerate(rows):
            cols = row.find_all("td")
            if not cols or len(cols) < 4: # Expecting at least Hour, Buy Vol, Sell Vol, Price
                # The first row might be a header or format identifier in some views, skip if not enough columns
                # Or, the EPEX table structure might have changed. The original code implies a specific structure.
                # Let's assume the relevant price is in the 4th column (index 3) if the first col is hour range.
                # If first col is data, price is cols[x]
                # The original code structure: buy_volume_col, sell_volume_col, volume_col, price_col
                # This implies the hour is implicit by row order.
                _LOGGER.debug("Skipping row %d with insufficient columns: %s", row_idx, [c.text for c in cols])
                continue
            
            # Assuming the structure from ha_epex_spot: Hour (implicit), Buy Vol, Sell Vol, Volume, Price
            # If the first column is an hour string like "00-01", we might need to parse it.
            # However, the original code iterates and increments start_time, implying row order defines the hour.

            try:
                # price_text = cols[3].string # Assuming price is the 4th column
                # Let's stick to the original logic's sibling finding if possible, assuming first td is buy_volume
                buy_volume_col = cols[0]
                sell_volume_col = buy_volume_col.find_next_sibling("td")
                volume_col = sell_volume_col.find_next_sibling("td")
                price_col = volume_col.find_next_sibling("td")

                if not price_col or price_col.string is None:
                    _LOGGER.warning("Price column missing or empty in row %d for %s, delivery %s", row_idx, self.market_area, delivery_date_local.date())
                    # Increment time even if data is missing for this hour to maintain sequence for next rows
                    current_hour_start_local += timedelta(minutes=self._market_config["duration"])
                    continue
                
                price_str = price_col.string.strip()
                price_val_mwh = _parse_epex_price(price_str)
                price_val_kwh = round(price_val_mwh / 1000.0, 5)

                start_time_utc = current_hour_start_local.astimezone(timezone.utc)

                hourly_prices.append({
                    API_RESPONSE_START_TIME: start_time_utc,
                    API_RESPONSE_PRICE: price_val_kwh,
                })
            except (ValueError, TypeError, IndexError, AttributeError) as e:
                _LOGGER.warning(
                    "Could not parse row %d for EPEX Spot Web, area %s, delivery %s: %s. Row content: %s",
                    row_idx, self.market_area, delivery_date_local.date(), e, [c.text.strip() for c in cols]
                )
            finally:
                # Always advance to the next hour slot
                current_hour_start_local += timedelta(minutes=self._market_config["duration"])
                # Stop if we've processed 24 hours for a 60-min duration product
                if self._market_config["duration"] == 60 and row_idx >= 23:
                    break 
                # Add similar logic for 30-min products if they become relevant (48 rows)
        
        return hourly_prices

    async def async_fetch_data(self, target_datetime: datetime) -> PriceData:
        """
        Fetches EPEX Spot Web data. It fetches for the target_datetime (today)
        and the next day, as prices are published day-ahead.
        """
        if not self._market_config:
            _LOGGER.error(
                "Cannot fetch EPEX Spot Web data for %s: market area configuration is missing.", self.market_area
            )
            return PriceData(hourly_raw=[], timezone="UTC", currency=CURRENCY_EUR, source=self.source_name, meta={"error": f"Market area {self.market_area} not configured for EPEX Spot Web"})

        # Determine the delivery dates to fetch based on the market's local timezone
        # target_datetime is UTC. We need to find "today" and "tomorrow" in the market's local time.
        market_timezone = get_area_timezone(self._market_config["timezone_hint"])
        
        # Convert target_datetime (which is effectively 'now' in UTC) to market's local time to determine 'today' for that market
        today_local_market_time = target_datetime.astimezone(market_timezone).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_local_market_time = today_local_market_time + timedelta(days=1)

        dates_to_fetch = [today_local_market_time, tomorrow_local_market_time]
        
        all_hourly_prices: List[Dict[str, Any]] = []
        raw_responses_preview = [] # For metadata

        for delivery_date_local in dates_to_fetch:
            daily_prices = await self._fetch_day_data(delivery_date_local)
            all_hourly_prices.extend(daily_prices)
            # We don't have a simple raw response preview here as it's parsed HTML from JSON commands
            raw_responses_preview.append(f"Fetched for {delivery_date_local.date()}: {len(daily_prices)} prices")

        if not all_hourly_prices:
            _LOGGER.warning("No price data successfully fetched from EPEX Spot Web for %s for dates around %s", self.market_area, target_datetime.date())
            return PriceData(hourly_raw=[], timezone="UTC", currency=self._market_config["currency"], source=self.source_name, meta={"error": "No data fetched", "fetch_attempts": raw_responses_preview})
        
        # Sort and de-duplicate (though _fetch_day_data should provide unique, sorted for its day)
        all_hourly_prices.sort(key=lambda x: x[API_RESPONSE_START_TIME])
        unique_hourly_prices = []
        seen_timestamps = set()
        for price_entry in all_hourly_prices:
            if price_entry[API_RESPONSE_START_TIME] not in seen_timestamps:
                unique_hourly_prices.append(price_entry)
                seen_timestamps.add(price_entry[API_RESPONSE_START_TIME])

        _LOGGER.info("Successfully processed %d unique price points from EPEX Spot Web for %s", len(unique_hourly_prices), self.market_area)
        return PriceData(
            hourly_raw=unique_hourly_prices,
            timezone="UTC", # All data is converted to UTC start times
            currency=self._market_config["currency"],
            source=self.source_name,
            meta={"api_url": EPEX_SPOT_WEB_API_URL, "raw_unit": f"{self._market_config['currency']}/MWh", "fetch_details": raw_responses_preview}
        )

    @property
    def name(self) -> str:
        return f"EPEX Spot Web ({self.market_area})"

