"""API handler for EPEX SPOT."""
import logging
import datetime
from datetime import timezone, timedelta, time
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List

from .base.api_client import ApiClient
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from .parsers.epex_parser import EpexParser
from ..utils.date_range import generate_date_ranges
from .base.base_price_api import BasePriceAPI
from .utils import fetch_with_retry
from ..const.time import TimezoneName

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.epexspot.com/en/market-results"

class EpexAPI(BasePriceAPI):
    """API client for EPEX SPOT."""

    def _get_source_type(self) -> str:
        return Source.EPEX

    def _get_base_url(self) -> str:
        return BASE_URL

    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Dict[str, Any]:
        client = ApiClient(session=session or self.session)
        try:
            now_utc = datetime.datetime.now(timezone.utc)
            today = now_utc.strftime("%Y-%m-%d")
            tomorrow = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")
            raw_today = await self._fetch_data(client, area, today)
            if raw_today and isinstance(raw_today, str) and raw_today.strip().lower().startswith("<!doctype html"):
                _LOGGER.error("EPEX returned HTML for today's data (possible cookie wall or error page). Treating as no data.")
                raw_today = None
            now_cet = now_utc.astimezone(timezone(timedelta(hours=1)))
            raw_tomorrow = None
            if now_cet.hour >= 13:
                async def fetch_tomorrow():
                    return await self._fetch_data(client, area, tomorrow)
                def is_data_available(data):
                    parser = self.get_parser_for_area(area)
                    parsed = parser.parse(data) if data else None
                    return parsed and parsed.get("hourly_prices")
                raw_tomorrow = await fetch_with_retry(
                    fetch_tomorrow,
                    is_data_available,
                    retry_interval=1800,
                    end_time=time(23, 50),
                    local_tz_name=TimezoneName.EUROPE_BERLIN
                )
                if raw_tomorrow and isinstance(raw_tomorrow, str) and raw_tomorrow.strip().lower().startswith("<!doctype html"):
                    _LOGGER.error("EPEX returned HTML for tomorrow's data (possible cookie wall or error page). Treating as no data.")
                    raw_tomorrow = None
                if not raw_tomorrow:
                    _LOGGER.warning(f"Failed to fetch EPEX tomorrow's data. Proceeding without it.")
            parser = self.get_parser_for_area(area)
            hourly_raw = {}
            if raw_today:
                parsed_today = parser.parse(raw_today)
                if parsed_today and "hourly_prices" in parsed_today:
                    hourly_raw.update(parsed_today["hourly_prices"])
            if raw_tomorrow:
                parsed_tomorrow = parser.parse(raw_tomorrow)
                if parsed_tomorrow and "hourly_prices" in parsed_tomorrow:
                    hourly_raw.update(parsed_tomorrow["hourly_prices"])
            metadata = {}
            if raw_today:
                try:
                    metadata = parser.extract_metadata(raw_today)
                except Exception as e:
                    _LOGGER.error(f"Failed to extract metadata from today's data: {e}")
            elif raw_tomorrow:
                try:
                    metadata = parser.extract_metadata(raw_tomorrow)
                except Exception as e:
                    _LOGGER.error(f"Failed to extract metadata from tomorrow's data: {e}")
            else:
                _LOGGER.error("No valid EPEX data available for metadata extraction.")
            return {
                "hourly_raw": hourly_raw,
                "timezone": metadata.get("timezone", "Europe/Berlin"),
                "currency": metadata.get("currency", "EUR"),
                "source_name": "epex",
                "raw_data": {
                    "today": raw_today,
                    "tomorrow": raw_tomorrow,
                    "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
                    "area": area
                },
            }
        finally:
            if session is None and client:
                await client.close()

    async def _fetch_data(self, client: ApiClient, area: str, date_str: str) -> Optional[str]:
        """
        Fetch raw HTML data for a given area and date from EPEX SPOT.
        Implements a two-step fetch to handle cookie walls and anti-bot measures:
        1. Fetch the main page to get cookies.
        2. Use those cookies in the actual data request.
        """
        import aiohttp
        params = {
            "market_area": area,
            "auction": "MRC",
            "trading_date": date_str,
            "delivery_date": (datetime.datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d"),
            "modality": "Auction",
            "sub_modality": "DayAhead",
            "data_mode": "table"
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,fr;q=0.8,de;q=0.7",
            "Connection": "keep-alive",
        }
        _LOGGER.debug(f"EPEX two-step fetch: getting cookies from {BASE_URL}")
        try:
            # Step 1: Get cookies from the main page
            async with aiohttp.ClientSession() as session:
                async with session.get(BASE_URL, headers=headers, timeout=15) as resp:
                    if resp.status != 200:
                        _LOGGER.warning(f"EPEX cookie fetch: HTTP {resp.status}")
                    cookies = session.cookie_jar.filter_cookies(BASE_URL)
                    cookie_header = "; ".join([f"{k}={v.value}" for k, v in cookies.items()])
                # Step 2: Use cookies in the actual data request
                headers_with_cookies = dict(headers)
                if cookie_header:
                    headers_with_cookies["Cookie"] = cookie_header
                _LOGGER.debug(f"EPEX data fetch: {BASE_URL} with params {params} and cookies {cookie_header}")
                async with session.get(BASE_URL, params=params, headers=headers_with_cookies, timeout=30) as resp2:
                    text = await resp2.text()
                    if resp2.status != 200:
                        _LOGGER.error(f"EPEX data fetch: HTTP {resp2.status}")
                    return text
        except Exception as e:
            _LOGGER.error(f"EPEX _fetch_data error (two-step): {e}")
            return None

    async def parse_raw_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        parser = self.get_parser_for_area(raw_data.get("raw_data", {}).get("area") or raw_data.get("area") or "FR")
        hourly_prices = {}
        timezone = raw_data.get("timezone", "Europe/Paris")
        currency = raw_data.get("currency", "EUR")
        for key in ("today", "tomorrow"):
            html = raw_data.get("raw_data", {}).get(key)
            if html:
                parsed = parser.parse(html)
                if parsed and "hourly_prices" in parsed:
                    hourly_prices.update(parsed["hourly_prices"])
        return {
            "hourly_prices": hourly_prices,
            "currency": currency,
            "api_timezone": timezone,
            "source": "epex",
            "area": raw_data.get("raw_data", {}).get("area") or raw_data.get("area") or "FR",
            "fetched_at": raw_data.get("raw_data", {}).get("timestamp"),
        }

