"""API handler for Nordpool."""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from .base.api_client import ApiClient
from ..const.sources import Source
from ..const.currencies import Currency
from ..const.areas import AreaMapping
from ..const.time import TimeFormat, TimezoneName
from ..const.network import Network
from .parsers.nordpool_parser import NordpoolParser
from ..utils.date_range import generate_date_ranges
from .base.base_price_api import BasePriceAPI
from .base.error_handler import ErrorHandler
from .utils import fetch_optional_data
from ..timezone.timezone_utils import get_timezone_object

_LOGGER = logging.getLogger(__name__)


class NordpoolAPI(BasePriceAPI):
    """Nordpool API implementation."""

    SOURCE_TYPE = Source.NORDPOOL

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        session=None,
        timezone_service=None,
    ):
        """Initialize the API.

        Args:
            config: Configuration dictionary
            session: Optional session for API requests
            timezone_service: Optional timezone service
        """
        super().__init__(config, session, timezone_service=timezone_service)
        self.error_handler = ErrorHandler(self.source_type)
        self.parser = NordpoolParser(timezone_service=timezone_service)

    def _get_base_url(self) -> str:
        """Get the base URL for the API.

        Returns:
            Base URL as string
        """
        return Network.URLs.NORDPOOL

    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Dict[str, Any]:
        """Fetch raw price data for the given area.

        Args:
            area: Area code
            session: Optional session for API requests
            **kwargs: Additional parameters

        Returns:
            Raw data from API
        """
        client = ApiClient(session=session or self.session)
        try:
            # Run the fetch with retry logic
            data = await self.error_handler.run_with_retry(
                self._fetch_data,
                client=client,
                area=area,
                reference_time=kwargs.get("reference_time"),
            )
            # Check if 'today' data exists within 'raw_data'
            if (
                not data
                or not isinstance(data, dict)
                or not data.get("raw_data", {}).get("today")
            ):
                _LOGGER.debug(
                    f"Nordpool API returned empty or invalid data for area {area}: {data}"
                )
            return data
        finally:
            if session is None:
                await client.close()

    async def _fetch_data(
        self, client: ApiClient, area: str, reference_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Fetch data from Nordpool.

        Args:
            client: API client
            area: Area code
            reference_time: Optional reference time

        Returns:
            Dictionary containing raw data and metadata for the parser.
        """
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
        else:
            # Convert to UTC if it's not already (coordinator may pass local timezone)
            reference_time = reference_time.astimezone(timezone.utc)

        # Map from area code to delivery area
        # The date query selects a CET/CEST delivery day, not a UTC day.
        reference_time = reference_time.astimezone(
            get_timezone_object(TimezoneName.EUROPE_OSLO)
        )
        delivery_area = AreaMapping.NORDPOOL_DELIVERY.get(area, area)

        _LOGGER.debug(
            f"Fetching Nordpool data for area: {area}, delivery area: {delivery_area}"
        )

        # Generate date ranges to try
        # For Nordpool, we need to handle today and tomorrow separately
        date_ranges = generate_date_ranges(reference_time, Source.NORDPOOL)

        # Check if we need extended date ranges due to timezone offset
        extended_ranges = self.needs_extended_date_range("Europe/Oslo", reference_time)

        # Fetch yesterday's data if needed
        yesterday_data = None
        if extended_ranges["need_yesterday"]:
            yesterday = (reference_time - timedelta(days=1)).strftime(
                TimeFormat.DATE_ONLY
            )
            params_yesterday = {
                "currency": Currency.EUR,
                "date": yesterday,
                "market": "DayAhead",
                "deliveryArea": delivery_area,
            }
            yesterday_data = await client.fetch(self.base_url, params=params_yesterday)
            _LOGGER.debug(
                f"Fetched yesterday's data ({yesterday}) for timezone offset handling"
            )

        # Fetch today's data (first range is today to tomorrow)
        today_start, today_end = date_ranges[0]
        today = today_start.strftime(TimeFormat.DATE_ONLY)

        params_today = {
            "currency": Currency.EUR,
            "date": today,
            "market": "DayAhead",
            "deliveryArea": delivery_area,
        }

        today_data = await client.fetch(self.base_url, params=params_today)

        # Try to fetch tomorrow's data if it's after 13:00 CET (when typically available)
        tomorrow_data = None
        now_utc = datetime.now(timezone.utc)
        # Use the imported function directly
        cet_tz = get_timezone_object("Europe/Oslo")  # Use Oslo time for Nordpool
        now_cet = now_utc.astimezone(cet_tz)

        # Define expected release hour (e.g. 13:00 CET)
        release_hour_cet = 13

        should_fetch_tomorrow = now_cet.hour >= release_hour_cet

        if should_fetch_tomorrow:
            # Always compute tomorrow as reference_time + 1 day
            tomorrow = (reference_time + timedelta(days=1)).strftime(
                TimeFormat.DATE_ONLY
            )
            params_tomorrow = {
                "currency": Currency.EUR,
                "date": tomorrow,
                "market": "DayAhead",
                "deliveryArea": delivery_area,
            }

            async def fetch_tomorrow():
                return await client.fetch(self.base_url, params=params_tomorrow)

            def is_data_available(data):
                # Check if data is a dict and has the expected structure
                return data and isinstance(data, dict) and data.get("multiAreaEntries")

            tomorrow_data = await fetch_optional_data(fetch_tomorrow, is_data_available)

        # Construct the dictionary to be returned to FallbackManager/DataProcessor
        # This dictionary should contain everything the parser needs.
        # Include yesterday/tomorrow data if fetched for timezone offset handling
        raw_data_payload = {
            "yesterday": yesterday_data,
            "today": today_data,
            "tomorrow": tomorrow_data,
        }
        # Basic check: If today_data is also missing/invalid, signal failure
        if (
            not today_data
            or not isinstance(today_data, dict)
            or not today_data.get("multiAreaEntries")
        ):
            _LOGGER.debug(
                f"Nordpool fetch failed for area {area}: Today's data is missing or invalid."
            )
            return None  # Signal failure

        return {
            "raw_data": raw_data_payload,
            "timezone": "Europe/Oslo",  # Nordpool API timezone
            "currency": "EUR",  # Nordpool API currency
            "area": area,  # Pass the area to the parser via this dict
            "delivery_area": delivery_area,  # Pass the delivery area for parser to use
            "source": self.source_type,  # Let the parser know the source
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            # Add any other metadata the parser might need from the API adapter context
        }
