"""OMIE API client."""
import logging
from datetime import datetime, timezone, timedelta
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

    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Optional[Dict[str, Any]]:
        """Fetch raw price data for the given area by trying date-specific file URLs.

        Args:
            area: Area code (e.g., ES or PT)
            session: Optional session for API requests
            **kwargs: Additional parameters

        Returns:
            Raw data from API or None if no valid data found
        """
        reference_time = kwargs.get('reference_time', datetime.now(timezone.utc))

        client = ApiClient(session=session or self.session)
        try:
            date_ranges = generate_date_ranges(
                reference_time,
                source_type=Source.OMIE,
                include_future=False,
                max_days_back=1
            )

            for start_date, _ in date_ranges:
                target_date = start_date.date()
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
                    continue

                if not response_text or isinstance(response_text, str) and ("<html" in response_text.lower() or "<!doctype" in response_text.lower()):
                    _LOGGER.debug(f"[OmieAPI] No valid data or HTML response from OMIE for {day}_{month}_{year}, trying next date.")
                    continue

                _LOGGER.info(f"[OmieAPI] Successfully fetched OMIE data for {day}_{month}_{year}")
                return {
                    "raw_data": response_text,
                    "area": area,
                    "timezone": self.get_timezone_for_area(area),
                    "url": url,
                    "target_date": target_date.isoformat()
                }

            _LOGGER.warning("[OmieAPI] No valid data found from OMIE after trying relevant dates.")
            return None

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
