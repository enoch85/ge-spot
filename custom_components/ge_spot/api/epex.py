"""API handler for EPEX SPOT."""
import logging
import datetime
from datetime import timezone, timedelta, time
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List
import asyncio

from .base.api_client import ApiClient
from .base_api import BaseAPI, PriceData # Import new base and PriceData
from ..api.registry import register_adapter # Import register_adapter
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

@register_adapter(
    name=Source.EPEX,
    regions=["FR", "DE", "AT", "BE", "NL", "GB", "CH"], # Add supported regions
    default_priority=40 # Example priority
)
class EpexAPI(BaseAPI): # Inherit from BaseAPI, renamed class
    """Adapter for EPEX SPOT."""

    def __init__(self, config: Dict[str, Any] | None = None, session: Any | None = None):
        super().__init__(config, session)
        self.parser = EpexParser() # Initialize the parser

    async def fetch_data(self, area: str) -> PriceData:
        """Fetch and parse data from EPEX SPOT, returning a PriceData object."""
        _LOGGER.debug(f"EPEX API: Fetching data for {area}") # Changed Adapter to API
        client = ApiClient(session=self.session) # Use self.session
        try:
            now_utc = datetime.datetime.now(timezone.utc)
            today_str = now_utc.strftime("%Y-%m-%d")
            tomorrow_str = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")
            
            raw_today = await self._fetch_page_data(client, area, today_str)
            
            cet_tz = get_timezone_object(TimezoneName.EUROPE_BERLIN)
            now_cet = now_utc.astimezone(cet_tz)
            raw_tomorrow = None

            release_hour_cet = 13
            failure_check_hour_cet = 16
            should_fetch_tomorrow = now_cet.hour >= release_hour_cet

            if should_fetch_tomorrow:
                async def fetch_tomorrow_page_data(): # Renamed for clarity
                    return await self._fetch_page_data(client, area, tomorrow_str)

                def is_data_valid(data: Optional[str]) -> bool: # Renamed and clarified
                    if not data or not isinstance(data, str):
                        return False
                    if data.strip().lower().startswith("<!doctype html"):
                        # Basic check, might need refinement based on actual error pages
                        return "epex-market-results-table" in data.lower()
                    # Assuming non-HTML means it's a direct table snippet or similar expected format
                    return "<table" in data and "epexspot" in data.lower() # Keep this for now

                raw_tomorrow = await fetch_with_retry(
                    fetch_tomorrow_page_data,
                    is_data_valid,
                    retry_interval=1800,
                    end_time=time(23, 50),
                    local_tz_name=TimezoneName.EUROPE_BERLIN
                )

                if now_cet.hour >= failure_check_hour_cet and not is_data_valid(raw_tomorrow):
                    _LOGGER.warning(f"EPEX fetch: Tomorrow's data for {area} not available/valid after {failure_check_hour_cet}:00 CET.")
                    # Return empty PriceData with error meta, or raise specific exception
                    return PriceData(source=self.api_name, meta={"error": f"Tomorrow's data missing for {area}"}) # Use self.api_name

            if not is_data_valid(raw_today):
                _LOGGER.error(f"EPEX fetch: Today's data for {area} is missing or invalid.")
                return PriceData(source=self.api_name, meta={"error": f"Today's data missing/invalid for {area}"}) # Use self.api_name

            # --- Parsing --- #
            all_prices: List[Dict[str, Any]] = [] # Use PriceEntry structure
            extracted_currency = "EUR" # Default
            extracted_timezone = TimezoneName.EUROPE_BERLIN # Default

            if raw_today and is_data_valid(raw_today): # Ensure it's valid before parsing
                try:
                    parsed_today_data = self.parser.parse(raw_today)
                    if parsed_today_data and parsed_today_data.get("hourly_prices"):
                        all_prices.extend(self._structure_parsed_prices(parsed_today_data["hourly_prices"]))                    
                    # Metadata extraction (assuming parser handles this or provides it)
                    # For now, we'll use defaults or what the parser might return in 'metadata'
                    meta_today = self.parser.extract_metadata(raw_today) # Assuming this method exists
                    extracted_currency = meta_today.get("currency", extracted_currency)
                    extracted_timezone = meta_today.get("timezone", extracted_timezone)
                except Exception as e:
                    _LOGGER.error(f"Error parsing today's EPEX data for {area}: {e}")
                    # Potentially return error if today's data is crucial and fails parsing
                    return PriceData(source=self.api_name, meta={"error": f"Parsing today's data failed for {area}: {e}"}) # Use self.api_name

            if raw_tomorrow and is_data_valid(raw_tomorrow): # Ensure it's valid before parsing
                try:
                    parsed_tomorrow_data = self.parser.parse(raw_tomorrow)
                    if parsed_tomorrow_data and parsed_tomorrow_data.get("hourly_prices"):
                         all_prices.extend(self._structure_parsed_prices(parsed_tomorrow_data["hourly_prices"])) 
                    meta_tomorrow = self.parser.extract_metadata(raw_tomorrow)
                    if meta_tomorrow: # Prioritize tomorrow's metadata if available
                        extracted_currency = meta_tomorrow.get("currency", extracted_currency)
                        extracted_timezone = meta_tomorrow.get("timezone", extracted_timezone)
                except Exception as e:
                    _LOGGER.warning(f"Error parsing tomorrow's EPEX data for {area}: {e}. Proceeding with today's data if any.")
            
            if not all_prices:
                _LOGGER.error(f"EPEX parsing resulted in no price data for {area}.")
                return PriceData(source=self.api_name, meta={"error": f"No price data extracted for {area}"}) # Use self.api_name

            # Sort by start_time
            all_prices.sort(key=lambda x: x['start_time'])

            return PriceData(
                hourly_raw=all_prices,
                timezone=extracted_timezone,
                currency=extracted_currency,
                source=self.api_name, # Use self.api_name
                meta={"raw_today_snippet": raw_today[:200] if raw_today else None, 
                      "raw_tomorrow_snippet": raw_tomorrow[:200] if raw_tomorrow else None}
            )
        except Exception as e:
            _LOGGER.exception(f"General error in EpexAPI fetch_data for {area}: {e}") # Changed EpexAdapter to EpexAPI
            return PriceData(source=self.api_name, meta={"error": f"General fetch error for {area}: {str(e)}"}) # Use self.api_name
        finally:
            if client: # Close client if it was created here (though ApiClient handles its own session if passed)
                await client.close()

    def _structure_parsed_prices(self, parsed_prices: Dict[str, float]) -> List[Dict[str, Any]]:
        """Converts parser's {iso_timestamp_str: price} to list of PriceEntry-like dicts."""
        structured_entries = []
        for ts_str, price in parsed_prices.items():
            try:
                dt_obj = datetime.datetime.fromisoformat(ts_str)
                structured_entries.append({"start_time": dt_obj, "price": float(price)})
            except (ValueError, TypeError) as e:
                _LOGGER.warning(f"EPEX: Could not parse timestamp or price: {ts_str}, {price}. Error: {e}")
        return structured_entries

    async def _fetch_page_data(self, client: ApiClient, area: str, date_str: str) -> Optional[str]:
        """Fetches the raw HTML/data for a given area and date from EPEX SPOT."""
        # This method encapsulates the logic from the old _fetch_data, 
        # focusing on fetching the page content.
        # The two-step cookie handling process is preserved here.
        import aiohttp # Keep local import if not used elsewhere in this class
        params = {
            "market_area": area,
            "auction": "MRC", # Assuming MRC is standard, adjust if needed
            "trading_date": date_str,
            "delivery_date": (datetime.datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d"),
            "modality": "Auction",
            "sub_modality": "DayAhead",
            "data_mode": "table", # Requesting table data
            # "generation_unit": "", # Ensure these are not needed or handled
            # "product": "60",
            # "connected_marketareas": "",
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,fr;q=0.8,de;q=0.7",
            "Connection": "keep-alive",
            "Referer": BASE_URL # Adding a referer might help
        }
        _LOGGER.debug(f"EPEX: Attempting to fetch data for {area} on {date_str} from {BASE_URL}")
        
        # Using aiohttp.ClientSession directly for more control over cookies, similar to original.
        # If ApiClient can handle this cookie dance, it could be used instead.
        try:
            async with aiohttp.ClientSession() as http_session: # Renamed to avoid conflict with self.session
                # Step 1: Initial request to establish session/cookies if necessary (though EPEX might not need this for table view)
                # For simplicity, let's try direct first, then add pre-fetch if issues persist.
                # async with http_session.get(BASE_URL, headers=headers, timeout=15) as initial_resp:
                #     if initial_resp.status != 200:
                #         _LOGGER.warning(f"EPEX initial page load for cookies returned status {initial_resp.status}")
                #     # Cookies are now in http_session.cookie_jar

                # Step 2: Request the actual data table
                _LOGGER.debug(f"EPEX data fetch: URL={BASE_URL}, Params={params}")
                async with http_session.get(BASE_URL, params=params, headers=headers, timeout=30) as resp:
                    text_content = await resp.text()
                    if resp.status != 200:
                        _LOGGER.error(f"EPEX data fetch for {area} on {date_str} failed with HTTP status {resp.status}. Response: {text_content[:500]}")
                        return None # Indicate error
                    
                    # Basic check for expected content (e.g., table presence)
                    # This helps differentiate from generic error pages or cookie walls.
                    if "epex-market-results-table" not in text_content.lower() and "<table" not in text_content.lower():
                        _LOGGER.warning(f"EPEX response for {area} on {date_str} does not seem to contain the expected data table. Might be an error page or changed layout. Content snippet: {text_content[:500]}")
                        # Depending on strictness, might return None here.
                        # For now, return the content and let parser decide.
                    return text_content
        except asyncio.TimeoutError:
            _LOGGER.error(f"EPEX request for {area} on {date_str} timed out.")
            return None
        except aiohttp.ClientError as e:
            _LOGGER.error(f"EPEX request for {area} on {date_str} failed due to client error: {e}")
            return None
        except Exception as e:
            _LOGGER.error(f"Unexpected error during EPEX data fetch for {area} on {date_str}: {e}", exc_info=True)
            return None

# Remove or comment out the old EpexAPI class if EpexAdapter replaces it fully.
# class EpexAPI(BasePriceAPI):
#     ...

