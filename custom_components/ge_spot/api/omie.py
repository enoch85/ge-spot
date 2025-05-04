"""OMIE API client."""
import logging
from datetime import datetime, timezone, timedelta, time
import aiohttp
from typing import Dict, Any, Optional

from .base.base_price_api import BasePriceAPI
from .parsers.omie_parser import OmieParser
from ..const.sources import Source
from .base.api_client import ApiClient
from ..const.network import Network
from ..const.currencies import Currency
from ..const.time import TimezoneName
from ..utils.date_range import generate_date_ranges
from ..const.config import Config
from ..timezone.timezone_utils import get_timezone_object
from .utils import fetch_with_retry

_LOGGER = logging.getLogger(__name__)

BASE_URL_TEMPLATE = "https://www.omie.es/sites/default/files/dados/AGNO_{year}/MES_{month}/TXT/INT_PBC_EV_H_1_{day}_{month}_{year}_{day}_{month}_{year}.TXT"

class OmieAPI(BasePriceAPI):
    """OMIE API client - Fetches data directly from OMIE text files."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, session: Optional[aiohttp.ClientSession] = None, timezone_service=None):
        """Initialize the API client.

        Args:
            config: Configuration dictionary
            session: aiohttp client session
            timezone_service: Timezone service instance
        """
        super().__init__(config, session, timezone_service)
        self.area = config.get(Config.AREA) if config else None

    def _get_source_type(self) -> str:
        """Get the source type for this API.

        Returns:
            Source type string
        """
        return Source.OMIE

    def _get_base_url(self) -> str:
        """Get the base URL template for API requests.

        Returns:
            Base URL template string
        """
        return BASE_URL_TEMPLATE

    async def _fetch_omie_file(self, client: ApiClient, target_date: datetime.date) -> Optional[str]:
        """Fetch a single OMIE data file for a specific date."""
        year = str(target_date.year)
        month = str.zfill(str(target_date.month), 2)
        day = str.zfill(str(target_date.day), 2)

        url = self._get_base_url().format(
            year=year, month=month, day=day
        )
        _LOGGER.debug(f"[OmieAPI] Attempting to fetch OMIE data from URL: {url}")

        response_text = await client.fetch(
            url,
            timeout=Network.Defaults.TIMEOUT,
            encoding='iso-8859-1',
            response_format='text'
        )

        if isinstance(response_text, dict) and response_text.get("error"):
            _LOGGER.warning(f"[OmieAPI] Client error fetching {url}: {response_text.get('message')}")
            return None

        if not response_text or isinstance(response_text, str) and ("<html" in response_text.lower() or "<!doctype" in response_text.lower()):
            _LOGGER.debug(f"[OmieAPI] No valid data or HTML response from OMIE for {day}_{month}_{year}.")
            return None

        _LOGGER.info(f"[OmieAPI] Successfully fetched OMIE data for {day}_{month}_{year}")
        return response_text

    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Optional[Dict[str, Any]]:
        """Fetch raw price data for the given area, checking for tomorrow if fallback is enabled."""
        if not self.area:
            self.area = area

        reference_time_utc = kwargs.get('reference_time', datetime.now(timezone.utc))
        today_date = reference_time_utc.date()
        tomorrow_date = today_date + timedelta(days=1)

        client = ApiClient(session=session or self.session)
        try:
            raw_today = await self._fetch_omie_file(client, today_date)

            if not raw_today:
                yesterday_date = today_date - timedelta(days=1)
                _LOGGER.warning(f"[OmieAPI] Today's ({today_date}) data missing, trying yesterday ({yesterday_date}).")
                raw_yesterday = await self._fetch_omie_file(client, yesterday_date)
                if raw_yesterday:
                    return {
                        "raw_data": {"today": None, "yesterday": raw_yesterday, "tomorrow": None},
                        "area": area,
                        "timezone": self.get_timezone_for_area(area),
                        "target_date": yesterday_date.isoformat(),
                        "data_source": self.source_type,
                        "attempted_sources": [self.source_type]
                    }
                else:
                    _LOGGER.error(f"[OmieAPI] Failed to fetch data for today ({today_date}) and yesterday ({yesterday_date}).")
                    return None

            raw_tomorrow = None
            fallback_sources = self.config.get(Config.FALLBACK_SOURCES, {})
            is_fallback_enabled = self.area in fallback_sources and fallback_sources[self.area]

            if is_fallback_enabled:
                local_tz_name = self.get_timezone_for_area(self.area)
                local_tz = get_timezone_object(local_tz_name)
                if not local_tz:
                    _LOGGER.warning(f"[OmieAPI] Could not get timezone object for {local_tz_name}, defaulting to UTC for time check.")
                    local_tz = timezone.utc

                now_local = reference_time_utc.astimezone(local_tz)
                release_hour_local = 14

                should_fetch_tomorrow = now_local.hour >= release_hour_local

                if should_fetch_tomorrow:
                    _LOGGER.debug(f"[OmieAPI] Fallback enabled for {self.area} and it's after {release_hour_local}:00 {local_tz_name}. Attempting to fetch tomorrow's ({tomorrow_date}) data.")
                    raw_tomorrow = await self._fetch_omie_file(client, tomorrow_date)

                    if not raw_tomorrow:
                        _LOGGER.warning(
                            f"[OmieAPI] Fetch failed for area {self.area}: Tomorrow's ({tomorrow_date}) data expected after "
                            f"{release_hour_local}:00 {local_tz_name} but was not available or invalid. Triggering fallback."
                        )
                        return None
                else:
                    _LOGGER.debug(f"[OmieAPI] Fallback enabled for {self.area}, but it's before {release_hour_local}:00 {local_tz_name}. Not checking for tomorrow's data yet.")
            else:
                _LOGGER.debug(f"[OmieAPI] Fallback not enabled for area {self.area}. Not checking for tomorrow's data.")

            raw_data_payload = {
                "today": raw_today,
                "tomorrow": raw_tomorrow,
                "yesterday": None
            }

            return {
                "raw_data": raw_data_payload,
                "area": area,
                "timezone": self.get_timezone_for_area(area),
                "target_date": today_date.isoformat(),
                "data_source": self.source_type,
                "attempted_sources": [self.source_type]
            }

        except Exception as e:
            _LOGGER.error(f"[OmieAPI] Unexpected error fetching OMIE data: {e}", exc_info=True)
            return None
        finally:
            if session is None and client:
                await client.close()

    def get_timezone_for_area(self, area: str) -> str:
        """Get the timezone name string for a specific area.

        Args:
            area: Area code

        Returns:
            Timezone string
        """
        if area and area.upper() == "PT":
            return TimezoneName.EUROPE_LISBON
        else:
            return TimezoneName.EUROPE_MADRID

    def get_parser_for_area(self, area: str) -> Any:
        """Get the appropriate parser instance.

        Args:
            area: Area code

        Returns:
            Parser instance
        """
        return OmieParser(timezone_service=self.timezone_service)
