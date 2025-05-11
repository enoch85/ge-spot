"""OMIE API client."""
import logging
from datetime import datetime, timezone, timedelta, time
import aiohttp
from typing import Dict, Any, Optional, List

from .base_api import BaseAPI, PriceData # Import new base and PriceData
from ..api.registry import register_adapter # Import register_adapter
from .parsers.omie_parser import OmieParser
from ..const.sources import Source
from .base.api_client import ApiClient
from ..const.network import Network
from ..const.currencies import Currency
from ..const.time import TimezoneName
from ..timezone.timezone_utils import get_timezone_object
from .utils import fetch_with_retry
from .base.error_handler import ErrorHandler

_LOGGER = logging.getLogger(__name__)

BASE_URL_TEMPLATE = "https://www.omie.es/sites/default/files/dados/AGNO_{year}/MES_{month}/TXT/INT_PBC_EV_H_1_{day}_{month}_{year}_{day}_{month}_{year}.TXT"

@register_adapter(
    name=Source.OMIE,
    regions=["ES", "PT"], # Supported regions for OMIE
    default_priority=20 # Example priority
)
class OmieAPI(BaseAPI): # Inherit from BaseAPI, renamed class
    """Adapter for OMIE API."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, session: Optional[aiohttp.ClientSession] = None, timezone_service=None):
        super().__init__(config, session)
        self.parser = OmieParser(timezone_service=timezone_service)

    def _get_url_for_date(self, target_date: datetime.date) -> str:
        year = str(target_date.year)
        month = str.zfill(str(target_date.month), 2)
        day = str.zfill(str(target_date.day), 2)
        return BASE_URL_TEMPLATE.format(year=year, month=month, day=day)

    async def _fetch_single_omie_file(self, client: ApiClient, target_date: datetime.date) -> Optional[str]:
        """Fetches a single OMIE data file for a specific date."""
        url = self._get_url_for_date(target_date)
        _LOGGER.debug(f"OmieAPI: Attempting to fetch data from URL: {url}") # Renamed class in log

        response_text = await client.fetch(
            url,
            timeout=Network.Defaults.TIMEOUT,
            encoding='iso-8859-1', # OMIE files use this encoding
            response_format='text'
        )

        if isinstance(response_text, dict) and response_text.get("error"):
            _LOGGER.warning(f"OmieAPI: Client error fetching {url}: {response_text.get('message')}") # Renamed class in log
            return None

        if not response_text or (isinstance(response_text, str) and ("<html" in response_text.lower() or "<!doctype" in response_text.lower())):
            _LOGGER.debug(f"OmieAPI: No valid data or HTML response from OMIE for {target_date.strftime('%Y-%m-%d')}.") # Renamed class in log
            return None

        _LOGGER.info(f"OmieAPI: Successfully fetched data for {target_date.strftime('%Y-%m-%d')}") # Renamed class in log
        return response_text

    def get_timezone_for_area(self, area: str) -> str:
        """Determines the timezone based on the OMIE area."""
        return TimezoneName.EUROPE_LISBON if area and area.upper() == "PT" else TimezoneName.EUROPE_MADRID

    async def fetch_data(self, area: str) -> PriceData:
        """Fetch and parse data from OMIE, returning a PriceData object."""
        _LOGGER.debug(f"OmieAPI: Fetching data for area {area}") # Renamed class in log
        client = ApiClient(session=self.session)
        try:
            reference_time = datetime.now(timezone.utc)
            today_date = reference_time.date()
            tomorrow_date = today_date + timedelta(days=1)

            raw_today = await self._fetch_single_omie_file(client, today_date)

            if not raw_today:
                _LOGGER.warning(f"OMIE: Today's ({today_date}) data missing or invalid for area {area}.")
                return PriceData(source=self.api_name, meta={"error": f"Today's data missing/invalid for {area}"}) # Use self.api_name

            raw_tomorrow = None
            area_timezone_str = self.get_timezone_for_area(area)
            area_tz = get_timezone_object(area_timezone_str)
            if not area_tz: # Should not happen if TimezoneName constants are valid
                _LOGGER.error(f"OMIE: Could not get timezone object for {area_timezone_str}, defaulting to UTC.")
                area_tz = timezone.utc 
            
            now_local = reference_time.astimezone(area_tz)
            release_hour_local = 14 # OMIE data typically available after 14:00 local time
            failure_check_hour_local = 16 # If still not available by 16:00, consider it an issue

            should_fetch_tomorrow = now_local.hour >= release_hour_local

            if should_fetch_tomorrow:
                _LOGGER.debug(f"OMIE: Attempting to fetch tomorrow's ({tomorrow_date}) data for {area}.")
                raw_tomorrow = await self._fetch_single_omie_file(client, tomorrow_date)
                if now_local.hour >= failure_check_hour_local and not raw_tomorrow:
                    _LOGGER.warning(f"OMIE: Tomorrow's data for {area} ({tomorrow_date}) not available/valid after {failure_check_hour_local}:00 {area_timezone_str}.")
                    # Proceed with today's data, but log the absence of tomorrow's

            # --- Parsing --- # 
            # The parser expects a dict similar to the old fetch_raw_data output.
            parser_input = {
                "raw_data": {"today": raw_today, "tomorrow": raw_tomorrow},
                "area": area,
                "timezone": area_timezone_str, # Pass the determined area timezone
                "currency": Currency.EUR, # OMIE is always EUR
                "source": self.api_name, # Use self.api_name
                "fetched_at": reference_time.isoformat()
            }

            parsed_result = self.parser.parse(parser_input)
            hourly_prices_from_parser = parsed_result.get("hourly_raw", {}) # dict: {iso_timestamp_str: price}
            final_hourly_prices: List[Dict[str, Any]] = []

            for ts_str, price_value in hourly_prices_from_parser.items():
                try:
                    dt_obj = datetime.fromisoformat(ts_str)
                    final_hourly_prices.append({"start_time": dt_obj, "price": float(price_value)})
                except (ValueError, TypeError) as e:
                    _LOGGER.warning(f"OMIE: Could not parse/convert entry: {ts_str}, {price_value}. Error: {e}")
            
            final_hourly_prices.sort(key=lambda x: x["start_time"]) # Ensure sorted order

            if not final_hourly_prices and raw_tomorrow: # If tomorrow's data was fetched but parsing yielded nothing
                 _LOGGER.warning(f"OMIE: Parsing resulted in no prices for {area}, though raw data (inc. tomorrow) seemed available.")

            return PriceData(
                hourly_raw=final_hourly_prices,
                timezone=parsed_result.get("timezone", area_timezone_str),
                currency=parsed_result.get("currency", Currency.EUR),
                source=self.api_name, # Use self.api_name
                meta={
                    "omie_area": area,
                    "parser_meta": parsed_result.get("meta", {}),
                    "raw_today_fetched": bool(raw_today),
                    "raw_tomorrow_fetched": bool(raw_tomorrow)
                }
            )

        except Exception as e:
            _LOGGER.exception(f"General error in OmieAPI fetch_data for {area}: {e}") # Renamed class in log
            return PriceData(source=self.api_name, meta={"error": f"General fetch error for {area}: {str(e)}"}) # Use self.api_name
        finally:
            # ApiClient manages its session if it created it.
            pass
