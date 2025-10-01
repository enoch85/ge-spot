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
from ..timezone.timezone_utils import get_timezone_object

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
            cet_tz = get_timezone_object("Europe/Berlin") # Use Berlin time for EPEX
            now_cet = now_utc.astimezone(cet_tz)
            raw_tomorrow = None

            # Define expected release hour (e.g., 13:00 CET)
            release_hour_cet = 13
            # Define a buffer hour to consider it a failure (e.g., 16:00 CET)
            failure_check_hour_cet = 16

            should_fetch_tomorrow = now_cet.hour >= release_hour_cet

            if should_fetch_tomorrow:
                async def fetch_tomorrow():
                    return await self._fetch_data(client, area, tomorrow)

                # Define a more robust check for valid EPEX data (not just HTML error/cookie page)
                def is_data_available(data):
                    if not data or not isinstance(data, str):
                        return False
                    # Check if it's likely an HTML page instead of the data table
                    if data.strip().lower().startswith("<!doctype html"):
                         # More specific check for table presence might be needed if error pages vary
                         # For now, assume any DOCTYPE means it's not the expected data table snippet
                         return False
                    # Basic check if it contains expected table markers (adjust if needed)
                    # This is brittle, relying on parser might be better if feasible here
                    return "<table" in data and "epexspot" in data.lower()

                raw_tomorrow = await fetch_with_retry(
                    fetch_tomorrow,
                    is_data_available, # Use the refined check
                    retry_interval=1800,
                    end_time=time(23, 50),
                    local_tz_name=TimezoneName.EUROPE_BERLIN
                )

                # --- Fallback Trigger Logic ---
                if now_cet.hour >= failure_check_hour_cet and not is_data_available(raw_tomorrow):
                    _LOGGER.warning(
                        f"EPEX fetch failed for area {area}: Tomorrow's data expected after {failure_check_hour_cet}:00 CET "
                        f"but was not available or invalid. Triggering fallback."
                    )
                    return None # Signal failure to FallbackManager

            # --- Final Check for Today's Data ---
            # Check if today's data is valid before proceeding
            if not is_data_available(raw_today):
                 _LOGGER.error(f"EPEX fetch failed for area {area}: Today's data is missing or invalid.")
                 return None # Signal failure if today's data is bad

            # --- Parsing and Structuring ---
            # (Moved parsing logic down to ensure checks happen first)
            parser = self.get_parser_for_area(area)
            interval_raw = {}
            metadata = {}

            # Parse today's data (already validated by is_data_available)
            try:
                parsed_today = parser.parse(raw_today)
                if parsed_today and "interval_raw" in parsed_today:
                    interval_raw.update(parsed_today["interval_raw"])
                # Extract metadata primarily from today's data
                metadata = parser.extract_metadata(raw_today)
            except Exception as e:
                _LOGGER.error(f"Failed to parse or extract metadata from today's EPEX data: {e}")
                # Decide if this is fatal - returning None might be safer
                return None

            # Parse tomorrow's data if available and valid
            if is_data_available(raw_tomorrow):
                try:
                    parsed_tomorrow = parser.parse(raw_tomorrow)
                    if parsed_tomorrow and "interval_raw" in parsed_tomorrow:
                        interval_raw.update(parsed_tomorrow["interval_raw"])
                    # Optionally update metadata if today's failed, though less likely
                    if not metadata:
                         metadata = parser.extract_metadata(raw_tomorrow)
                except Exception as e:
                    _LOGGER.warning(f"Failed to parse tomorrow's EPEX data, proceeding without it: {e}")

            # Ensure we have at least some prices before returning success
            if not interval_raw:
                _LOGGER.error(f"EPEX parsing failed for area {area}: No interval prices extracted from valid raw data.")
                return None

            # Construct the final dictionary for the DataProcessor
            # Ensure raw_data key is present for FallbackManager
            final_raw_data = {
                "today": raw_today,
                "tomorrow": raw_tomorrow,
                "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
                "area": area
            }

            return {
                "interval_raw": interval_raw,
                "timezone": metadata.get("timezone", "Europe/Berlin"),
                "currency": metadata.get("currency", "EUR"),
                "source_name": Source.EPEX, # Use constant
                "raw_data": final_raw_data, # Include the raw HTML for parsing/cache
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
        """Parse raw EPEX data for reprocessing from cache.
        
        Args:
            raw_data: Raw data dictionary
            
        Returns:
            Parsed data with interval_raw
        """
        parser = self.get_parser_for_area(raw_data.get("raw_data", {}).get("area") or raw_data.get("area") or "FR")
        interval_raw = {}
        timezone = raw_data.get("timezone", "Europe/Paris")
        currency = raw_data.get("currency", "EUR")
        for key in ("today", "tomorrow"):
            html = raw_data.get("raw_data", {}).get(key)
            if html:
                parsed = parser.parse(html)
                if parsed and "interval_raw" in parsed:
                    interval_raw.update(parsed["interval_raw"])
        return {
            "interval_raw": interval_raw,
            "currency": currency,
            "api_timezone": timezone,
            "source": "epex",
            "area": raw_data.get("raw_data", {}).get("area") or raw_data.get("area") or "FR",
            "fetched_at": raw_data.get("raw_data", {}).get("timestamp"),
        }
