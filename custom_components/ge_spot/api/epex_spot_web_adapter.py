\
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, cast
from zoneinfo import ZoneInfo # Use zoneinfo for modern timezone handling

import aiohttp
from bs4 import BeautifulSoup

from custom_components.ge_spot.api.base_adapter import BaseAPIAdapter, PriceData
from custom_components.ge_spot.api.registry import register_adapter
from custom_components.ge_spot.const import (
    API_RESPONSE_HOUR,
    API_RESPONSE_PRICE,
    API_RESPONSE_START_TIME,
    CURRENCY_EUR,
    CURRENCY_GBP,
    NETWORK_TIMEOUT,
    SOURCE_EPEX_SPOT_WEB, # This will be added to sources.py
)
# Assuming similar utility structure as Awattar
# from custom_components.ge_spot.utils.network import async_post_json_or_raise 
from custom_components.ge_spot.utils.time import (
    get_date_range_for_target_day,
    parse_iso_datetime_with_fallback,
)

_LOGGER = logging.getLogger(__name__)

API_URL = "https://www.epexspot.com/en/market-results"

# Market area mapping from ha_epex_spot, might need adjustment for ge-spot's area codes
# For now, we'll use it to determine internal parameters for the request.
# ge-spot's self.market_area will be the primary key.
EPEX_MARKET_AREA_PARAMS = {
    "GB": {"auction": "GB", "internal_market_area": "GB", "duration": 60, "currency": CURRENCY_GBP, "timezone": "Europe/London"},
    "GB-30": {"auction": "30-call-GB", "internal_market_area": "GB", "duration": 30, "currency": CURRENCY_GBP, "timezone": "Europe/London"}, # 30 min not directly supported by ge-spot hourly, will need aggregation if used
    "CH": {"auction": "CH", "internal_market_area": "CH", "duration": 60, "currency": CURRENCY_EUR, "timezone": "Europe/Zurich"},
    # Default for others is MRC auction, 60 min, EUR, Europe/Paris (or similar CET)
}
DEFAULT_EPEX_PARAMS = {"auction": "MRC", "duration": 60, "currency": CURRENCY_EUR, "timezone": "Europe/Paris"}


@register_adapter(
    name=SOURCE_EPEX_SPOT_WEB,
    # Regions need to be mapped from ha_epex_spot's list to ge-spot's area codes
    regions=["AT", "BE", "CH", "DE", "DK1", "DK2", "FI", "FR", "GB", "NL", "NO1", "NO2", "NO3", "NO4", "PL", "SE1", "SE2", "SE3", "SE4"], # Example, needs verification
    default_priority=20,
    currencies=[CURRENCY_EUR, CURRENCY_GBP]
)
class EpexSpotWebAdapter(BaseAPIAdapter):
    """
    Adapter for the EPEX Spot website (scraping).
    Fetches day-ahead electricity prices.
    """

    def __init__(self, hass, api_key_manager, source_name: str, market_area: str, session: aiohttp.ClientSession, **kwargs):
        super().__init__(hass, api_key_manager, source_name, market_area, session, **kwargs)
        
        specific_params = EPEX_MARKET_AREA_PARAMS.get(self.market_area.upper())
        if specific_params:
            self._api_auction = specific_params["auction"]
            self._api_internal_market_area = specific_params["internal_market_area"]
            self._api_duration_product = specific_params["duration"] # Product parameter for API
            self._source_currency = specific_params["currency"]
            self._source_timezone_str = specific_params["timezone"]
        else:
            # Default for most EU countries not explicitly listed (e.g. FR, DE-LU, AT etc.)
            self._api_auction = DEFAULT_EPEX_PARAMS["auction"]
            self._api_internal_market_area = self.market_area # Use ge-spot market area directly
            self._api_duration_product = DEFAULT_EPEX_PARAMS["duration"]
            self._source_currency = DEFAULT_EPEX_PARAMS["currency"]
            self._source_timezone_str = DEFAULT_EPEX_PARAMS["timezone"] # Typically CET for these markets

        self._source_timezone = ZoneInfo(self._source_timezone_str)


    def _format_date_for_api(self, dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d")

    async def _fetch_day_data(self, delivery_date: datetime) -> List[Dict[str, Any]]:
        """Fetches and parses data for a single delivery date."""
        trading_date = delivery_date - timedelta(days=1)
        
        # Headers and params from ha_epex_spot
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
            "X-Requested-With": "XMLHttpRequest", # Often needed for AJAX requests
            "Referer": API_URL,
        }
        params = {
            "market_area": self._api_internal_market_area,
            "trading_date": self._format_date_for_api(trading_date),
            "delivery_date": self._format_date_for_api(delivery_date),
            "auction": self._api_auction,
            "modality": "Auction",
            "sub_modality": "DayAhead",
            "product": self._api_duration_product, # 60 or 30
            "data_mode": "table",
            "ajax_form": "1",
        }
        # POST data payload
        payload = {
            "form_id": "market_data_filters_form",
            "_triggering_element_name": "submit_js",
            # "_drupal_ajax": "1", # May or may not be needed
            # "ajax_page_state[theme]": "epex", # May or may not be needed
        }

        _LOGGER.debug("Fetching EPEX Spot Web data for %s, delivery_date %s. URL: %s, Params: %s, Payload: %s",
                      self.market_area, delivery_date, API_URL, params, payload)

        try:
            async with self._session.post(API_URL, headers=headers, params=params, data=payload, timeout=NETWORK_TIMEOUT) as resp:
                resp.raise_for_status()
                response_json = await resp.json() # Expecting JSON that contains HTML
        except Exception as e:
            _LOGGER.error("Error fetching EPEX Spot Web data for %s on %s: %s", self.market_area, delivery_date, e)
            return []

        # Extract HTML table from JSON response (as per ha_epex_spot)
        html_content = ""
        for entry in response_json:
            if entry.get("command") == "invoke" and entry.get("selector") == ".js-md-widget":
                if "args" in entry and entry["args"]:
                    html_content = entry["args"][0]
                    break
        
        if not html_content:
            _LOGGER.warning("No HTML table content found in EPEX Spot Web response for %s on %s.", self.market_area, delivery_date)
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        table = soup.find("table", class_="table-01") # table-length-1 might be too specific
        if not table or not table.tbody:
            _LOGGER.warning("Price table not found in EPEX Spot Web HTML for %s on %s.", self.market_area, delivery_date)
            return []

        hourly_prices: List[Dict[str, Any]] = []
        rows = table.tbody.find_all("tr")

        # Determine the starting hour for the given delivery_date in the source's timezone
        # The table rows are 00-01, 01-02, etc. for the delivery_date in local market time.
        current_hour_start_local = delivery_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=self._source_timezone)

        for row_idx, row in enumerate(rows):
            cols = row.find_all("td")
            if len(cols) < 4: # Expecting at least hour, buy_vol, sell_vol, price
                _LOGGER.warning("Skipping malformed row in EPEX Spot Web table: %s", row)
                continue
            
            # Hour is implied by row index, starting from 00:00 of delivery_date in local market time
            # Some tables might have an explicit hour column, e.g. cols[0].string like "00:00 - 01:00"
            # For now, assume implicit hour based on row index and delivery_date
            
            start_time_local = current_hour_start_local + timedelta(hours=row_idx)
            # Convert local start time to UTC for internal consistency before ge-spot's TimezoneService
            start_time_utc = start_time_local.astimezone(timezone.utc)

            try:
                # Price is typically in the last relevant column
                # ha_epex_spot: price_col = volume_col.find_next_sibling("td")
                # Assuming price is in cols[3] after hour, buy_vol, sell_vol
                price_str = cols[3].string
                if price_str is None:
                    _LOGGER.warning("Price string is None for row %s", row)
                    continue
                
                # Prices are per MWh, convert to per kWh
                price_mwh = float(price_str.replace(",", "")) # Handle thousand separators if any
                price_kwh = round(price_mwh / 1000.0, 5)

                hourly_prices.append({
                    API_RESPONSE_START_TIME: start_time_utc, # Store as UTC
                    API_RESPONSE_PRICE: price_kwh,
                })
            except (ValueError, IndexError) as e:
                _LOGGER.warning("Error parsing row in EPEX Spot Web table for %s: %s. Row: %s", self.market_area, e, row)
                continue
            
            if self._api_duration_product == 30 and len(hourly_prices) >= 48: # Stop if 30-min data and we have 48 entries
                 break
            if self._api_duration_product == 60 and len(hourly_prices) >= 24: # Stop if 60-min data and we have 24 entries
                 break


        # If duration is 30 minutes, we need to aggregate to hourly for ge-spot
        # This is a simplification for now; true 30-min handling is complex for ge-spot's current model.
        # For now, if it's 30 min data, this adapter will be problematic unless ge-spot supports sub-hourly.
        # Let's assume for now product is 60. If 30, this adapter would need significant changes or be limited.
        if self._api_duration_product == 30:
            _LOGGER.warning("EPEX Spot Web adapter fetched 30-min data for %s. Aggregation to hourly is not yet implemented robustly. Data might be incomplete or misaligned.", self.market_area)
            # Basic aggregation: average two 30-min slots. This is a placeholder.
            aggregated_prices = []
            for i in range(0, len(hourly_prices), 2):
                if i + 1 < len(hourly_prices):
                    avg_price = round((hourly_prices[i][API_RESPONSE_PRICE] + hourly_prices[i+1][API_RESPONSE_PRICE]) / 2, 5)
                    aggregated_prices.append({
                        API_RESPONSE_START_TIME: hourly_prices[i][API_RESPONSE_START_TIME],
                        API_RESPONSE_PRICE: avg_price
                    })
            hourly_prices = aggregated_prices


        return hourly_prices

    async def async_fetch_data(self, target_datetime: datetime) -> PriceData:
        """
        Fetches electricity prices for the target_datetime and the next day.
        EPEX Spot website provides data per day.
        """
        # Determine dates to fetch in the source's local timezone context
        # target_datetime is UTC. Convert to source's local to determine "today" and "tomorrow" for fetching.
        target_datetime_local = target_datetime.astimezone(self._source_timezone)
        
        fetch_date_today_local = target_datetime_local.replace(hour=0, minute=0, second=0, microsecond=0)
        fetch_date_tomorrow_local = fetch_date_today_local + timedelta(days=1)

        all_hourly_prices: List[Dict[str, Any]] = []
        
        # Fetch for "today" (based on target_datetime)
        _LOGGER.info("Fetching EPEX Spot Web for %s for local date: %s", self.market_area, fetch_date_today_local.date())
        today_prices = await self._fetch_day_data(fetch_date_today_local)
        all_hourly_prices.extend(today_prices)

        # Fetch for "tomorrow"
        _LOGGER.info("Fetching EPEX Spot Web for %s for local date: %s", self.market_area, fetch_date_tomorrow_local.date())
        tomorrow_prices = await self._fetch_day_data(fetch_date_tomorrow_local)
        all_hourly_prices.extend(tomorrow_prices)
        
        if not all_hourly_prices:
            _LOGGER.warning("No data fetched from EPEX Spot Web for %s.", self.market_area)
        else:
            _LOGGER.info("Successfully fetched %d price points from EPEX Spot Web for %s", len(all_hourly_prices), self.market_area)
            
        return PriceData(
            hourly_raw=all_hourly_prices,
            timezone=self._source_timezone_str, # Inform ge-spot of the original timezone of the data context
            currency=self._source_currency,
            source=self.source_name,
            meta={"api_url": API_URL, "raw_unit": f"{self._source_currency}/MWh"}
        )

    @property
    def name(self) -> str:
        return f"EPEX Spot Web ({self.market_area})"

