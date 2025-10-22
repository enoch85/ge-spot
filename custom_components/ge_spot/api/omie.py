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
from ..timezone.timezone_utils import get_timezone_object
from .utils import fetch_with_retry
from .base.error_handler import ErrorHandler

_LOGGER = logging.getLogger(__name__)

BASE_URL_TEMPLATE = "https://www.omie.es/sites/default/files/dados/AGNO_{year}/MES_{month}/TXT/INT_PBC_EV_H_1_{day}_{month}_{year}_{day}_{month}_{year}.TXT"


class OmieAPI(BasePriceAPI):
    """OMIE API client - Fetches data directly from OMIE text files."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        session: Optional[aiohttp.ClientSession] = None,
        timezone_service=None,
    ):
        """Initialize the API client.

        Args:
            config: Configuration dictionary
            session: aiohttp client session
            timezone_service: Timezone service instance
        """
        super().__init__(config, session, timezone_service)
        self.area = config.get("area") if config else None
        self.error_handler = ErrorHandler(self.source_type)
        self.parser = OmieParser(timezone_service=self.timezone_service)

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

    async def _fetch_omie_file(
        self, client: ApiClient, target_date: datetime.date
    ) -> Optional[str]:
        """Fetch a single OMIE data file for a specific date."""
        year = str(target_date.year)
        month = str.zfill(str(target_date.month), 2)
        day = str.zfill(str(target_date.day), 2)

        url = self._get_base_url().format(year=year, month=month, day=day)
        _LOGGER.debug(f"[OmieAPI] Attempting to fetch OMIE data from URL: {url}")

        response_text = await client.fetch(
            url,
            timeout=Network.Defaults.HTTP_TIMEOUT,
            encoding="iso-8859-1",  # OMIE uses ISO-8859-1 encoding for Spanish text
            response_format="text",
        )

        if isinstance(response_text, dict) and response_text.get("error"):
            _LOGGER.warning(
                f"[OmieAPI] Client error fetching {url}: {response_text.get('message')}"
            )
            return None

        if (
            not response_text
            or isinstance(response_text, str)
            and (
                "<html" in response_text.lower() or "<!doctype" in response_text.lower()
            )
        ):
            _LOGGER.debug(
                f"[OmieAPI] No valid data or HTML response from OMIE for {day}_{month}_{year}."
            )
            return None

        _LOGGER.info(
            f"[OmieAPI] Successfully fetched OMIE data for {day}_{month}_{year}"
        )
        return response_text

    async def fetch_raw_data(
        self, area: str, session=None, **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Fetch raw price data for the given area using ErrorHandler."""
        if not self.area:
            self.area = area

        client = ApiClient(session=session or self.session)
        try:
            data = await self.error_handler.run_with_retry(
                self._fetch_data,
                client=client,
                area=area,
                reference_time=kwargs.get("reference_time"),
            )
            if (
                not data
                or not isinstance(data, dict)
                or not data.get("raw_data", {}).get("today")
            ):
                _LOGGER.error(
                    f"OMIE API fetch ultimately failed for area {area} after retries or returned invalid data."
                )
                return None
            return data
        finally:
            if session is None and client:
                await client.close()

    async def _fetch_data(
        self, client: ApiClient, area: str, reference_time: Optional[datetime] = None
    ) -> Optional[Dict[str, Any]]:
        """Internal method to fetch data, called by ErrorHandler."""
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
        else:
            # Convert to UTC if it's not already (coordinator may pass local timezone)
            reference_time = reference_time.astimezone(timezone.utc)

        today_date = reference_time.date()
        tomorrow_date = today_date + timedelta(days=1)

        raw_today = await self._fetch_omie_file(client, today_date)

        if not raw_today:
            _LOGGER.warning(
                f"[OmieAPI] Today's ({today_date}) data missing or invalid. Signaling failure."
            )
            return None

        raw_tomorrow = None
        local_tz_name = self.get_timezone_for_area(area)
        local_tz = get_timezone_object(local_tz_name)
        if not local_tz:
            _LOGGER.warning(
                f"[OmieAPI] Could not get timezone object for {local_tz_name}, defaulting to UTC for time check."
            )
            local_tz = timezone.utc

        now_local = reference_time.astimezone(local_tz)
        release_hour_local = 14
        failure_check_hour_local = 16

        should_fetch_tomorrow = now_local.hour >= release_hour_local

        if should_fetch_tomorrow:
            _LOGGER.debug(
                f"[OmieAPI] Attempting to fetch tomorrow's ({tomorrow_date}) data as it's after {release_hour_local}:00 {local_tz_name}."
            )
            raw_tomorrow = await self._fetch_omie_file(client, tomorrow_date)

            if now_local.hour >= failure_check_hour_local and not raw_tomorrow:
                _LOGGER.warning(
                    f"[OmieAPI] Fetch failed for area {area}: Tomorrow's ({tomorrow_date}) data expected after "
                    f"{failure_check_hour_local}:00 {local_tz_name} but was not available or invalid. Triggering fallback."
                )
                return None
        else:
            _LOGGER.debug(
                f"[OmieAPI] Not attempting to fetch tomorrow's ({tomorrow_date}) data yet (before {release_hour_local}:00 {local_tz_name})."
            )

        raw_data_payload = {
            "today": raw_today,
            "tomorrow": raw_tomorrow,
        }

        return {
            "raw_data": raw_data_payload,
            "area": area,
            "timezone": local_tz_name,
            "currency": Currency.EUR,
            "source": self.source_type,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

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
