"""API handler for Energi Data Service."""

import logging
import datetime
from datetime import timezone, timedelta
import json
from typing import Dict, Any

from .base.api_client import ApiClient
from ..const.sources import Source
from .parsers.energi_data_parser import EnergiDataParser
from .base.base_price_api import BasePriceAPI
from .utils import fetch_optional_data
from ..const.currencies import Currency
from ..const.energy import EnergyUnit
from ..const.time import TimezoneName
from ..timezone.timezone_utils import get_timezone_object

_LOGGER = logging.getLogger(__name__)

# Since September 30, 2025: DayAheadPrices provides native 15-minute intervals
# Before: Elspotprices provided hourly data
BASE_URL = "https://api.energidataservice.dk/dataset/DayAheadPrices"


class EnergiDataAPI(BasePriceAPI):
    """API client for Energi Data Service."""

    SOURCE_TYPE = Source.ENERGI_DATA_SERVICE

    def _get_base_url(self) -> str:
        """Get the base URL for the API.

        Returns:
            Base URL as string
        """
        return BASE_URL

    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Dict[str, Any]:
        """Fetch raw data from Energi Data Service API.

        Args:
            area: Area code
            session: Optional aiohttp session
            **kwargs: Additional keyword arguments (e.g. reference_time)

        Returns:
            Dictionary containing raw data and metadata for the parser.
        """
        client = ApiClient(session=session or self.session)
        try:
            # Use UTC for all reference times
            reference_time = kwargs.get("reference_time")
            if reference_time is None:
                reference_time = datetime.datetime.now(timezone.utc)
            else:
                # Convert to UTC if it's not already (coordinator may pass local timezone)
                reference_time = reference_time.astimezone(timezone.utc)

            # Always compute today and tomorrow based on reference time
            # Requests use timezone=dk, so their date boundaries must also be Danish.
            reference_time = reference_time.astimezone(
                get_timezone_object(TimezoneName.EUROPE_COPENHAGEN)
            )
            today = reference_time.strftime("%Y-%m-%d")
            tomorrow = (reference_time + timedelta(days=1)).strftime("%Y-%m-%d")

            # Fetch today's data
            raw_today = await self._fetch_data(client, area, today)

            # Missing forecasts must not delay today's usable prices.
            now_utc = datetime.datetime.now(timezone.utc)
            # Use the imported function directly
            cet_tz = get_timezone_object(
                "Europe/Copenhagen"
            )  # Use Copenhagen time for EnergiDataService
            now_cet = now_utc.astimezone(cet_tz)
            raw_tomorrow = None

            # Define expected release hour (e.g. 13:00 CET)
            release_hour_cet = 13

            should_fetch_tomorrow = now_cet.hour >= release_hour_cet

            if should_fetch_tomorrow:

                async def fetch_tomorrow_task():  # Renamed to avoid conflict
                    return await self._fetch_data(client, area, tomorrow)

                # Basic check for tomorrow's data presence
                def is_tomorrow_data_present(data):
                    return data and isinstance(data, dict) and data.get("records")

                raw_tomorrow = await fetch_optional_data(
                    fetch_tomorrow_task, is_tomorrow_data_present
                )

            # --- Final Check for Today's Data ---
            # Check if today's data is valid before proceeding
            if (
                not raw_today
                or not isinstance(raw_today, dict)
                or not raw_today.get("records")
            ):
                _LOGGER.debug(
                    f"EnergiDataService fetch failed for area {area}: Today's data is missing or invalid."
                )
                return None  # Signal failure if today's data is bad

            # --- No Parsing Here ---
            # The parser will be called later by DataProcessor

            # Return the raw data along with necessary metadata for the parser
            # Ensure raw_data key is present for FallbackManager
            final_raw_data = {
                "today": raw_today,
                "tomorrow": raw_tomorrow,
            }

            return {
                "raw_data": final_raw_data,
                "timezone": "Europe/Copenhagen",  # EnergiDataService API timezone context
                "currency": Currency.DKK,  # Use constant
                "area": area,
                "source": self.source_type,
                "fetched_at": datetime.datetime.now(timezone.utc).isoformat(),
                "source_unit": EnergyUnit.MWH,
            }
        finally:
            if session is None and client:
                await client.close()

    def get_timezone_for_area(self, area: str) -> str:
        """Get timezone for the area.

        Args:
            area: Area code

        Returns:
            Timezone string
        """
        return "Europe/Copenhagen"

    def get_parser_for_area(self, area: str) -> Any:
        """Get parser for the area.

        Args:
            area: Area code

        Returns:
            Parser instance
        """
        return EnergiDataParser()

    async def _fetch_data(self, client, area, date_str):
        """Fetch data from Energi Data Service.

        Args:
            client: API client
            area: Area code
            date_str: Date string in YYYY-MM-DD format

        Returns:
            Raw response
        """
        # Parse the provided date string
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )

        # Historical prices cannot fill a missing forecast for the selected date.
        date_ranges = [(date_obj, date_obj + timedelta(days=1))]

        # Use area from config or passed parameter
        area_code = area if area else "DK1"  # Default to Western Denmark

        # Try each date range until we get a valid response
        for start_date, end_date in date_ranges:
            # Format dates for Energi Data Service API
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")

            params = {
                "start": f"{start_str}T00:00",
                "end": f"{end_str}T00:00",
                "filter": json.dumps({"PriceArea": area_code}),
                "sort": "TimeDK",
                "timezone": "dk",
            }

            _LOGGER.debug(f"Fetching Energi Data Service with params: {params}")

            response = await client.fetch(BASE_URL, params=params)

            # Check if we got a valid response with records
            if (
                response
                and isinstance(response, dict)
                and "records" in response
                and response["records"]
            ):
                _LOGGER.debug(
                    f"Successfully fetched Energi Data Service data for {start_str} to {end_str}"
                )
                return response
            else:
                _LOGGER.debug(
                    f"No valid data from Energi Data Service for {start_str} to {end_str}"
                )

        _LOGGER.debug("No prices published for %s on %s", area_code, date_str)
        return None
