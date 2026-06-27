"""API handler for Nordpool."""

import logging
from datetime import datetime, timezone, timedelta, time
from typing import Dict, Any, Optional

from .base.api_client import ApiClient
from ..const.sources import Source
from ..const.currencies import Currency
from ..const.areas import AreaMapping
from ..const.time import TimeFormat
from ..const.network import Network
from .parsers.nordpool_parser import NordpoolParser
from ..utils.date_range import generate_date_ranges
from .base.base_price_api import BasePriceAPI
from .base.error_handler import ErrorHandler
from .utils import fetch_with_retry
from ..const.time import TimezoneName
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
                _LOGGER.error(
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
        # Define a buffer hour to consider it a failure (e.g. 16:00 CET)
        failure_check_hour_cet = 16

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

            # Attempt to fetch tomorrow's data with retry
            tomorrow_data = await fetch_with_retry(
                fetch_tomorrow,
                is_data_available,
                retry_interval=Network.Defaults.STANDARD_UPDATE_INTERVAL_MINUTES
                * Network.Defaults.SECONDS_PER_MINUTE,
                end_time=time(
                    Network.Defaults.RETRY_CUTOFF_TIME_HOUR,
                    Network.Defaults.RETRY_CUTOFF_TIME_MINUTE,
                ),
                local_tz_name=TimezoneName.EUROPE_OSLO,  # Use Oslo time for end_time check
            )

            # --- Fallback Trigger Logic ---
            # If it's past the failure check time and tomorrow's data is still not available,
            # treat this fetch attempt as a failure to trigger fallback.
            # However, if we got HTTP 204, this is "data not ready" not "API failed"
            if now_cet.hour >= failure_check_hour_cet and not is_data_available(
                tomorrow_data
            ):
                # Check if it's a "not ready yet" (204) vs actual failure
                if (
                    tomorrow_data
                    and isinstance(tomorrow_data, dict)
                    and tomorrow_data.get("status") == 204
                ):
                    _LOGGER.info(
                        f"Nordpool tomorrow data not yet published for area {area} (HTTP 204 after {failure_check_hour_cet}:00 CET). "
                        f"Will continue with today's data only."
                    )
                    # Don't trigger fallback - this is expected, just proceed with today's data
                    tomorrow_data = None
                else:
                    _LOGGER.warning(
                        f"Nordpool fetch failed for area {area}: Tomorrow's data expected after {failure_check_hour_cet}:00 CET "
                        f"but was not available or invalid. Triggering fallback."
                    )
                    return None  # Signal failure to FallbackManager

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
            _LOGGER.error(
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
