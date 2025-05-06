"""API handler for ComEd Hourly Pricing."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
import asyncio
import json
import re

from .base.api_client import ApiClient
from ..timezone import TimezoneService
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.api import ComEd
from .parsers.comed_parser import ComedParser
from ..utils.date_range import generate_date_ranges
from .base.base_price_api import BasePriceAPI

_LOGGER = logging.getLogger(__name__)

class ComedAPI(BasePriceAPI):
    """API client for ComEd Hourly Pricing."""

    def _get_source_type(self) -> str:
        """Get the source type identifier.

        Returns:
            Source type identifier
        """
        return Source.COMED

    def _get_base_url(self) -> str:
        """Get the base URL for the API.

        Returns:
            Base URL as string
        """
        return ComEd.BASE_URL

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
            # Use current UTC time as reference
            now_utc = datetime.now(timezone.utc)

            # Fetch data from ComEd API
            raw_data = await self._fetch_data(client, area, now_utc)
            if not raw_data:
                return {}

            # Parse the data
            parser = self.get_parser_for_area(area)
            parsed = parser.parse(raw_data)
            hourly_raw = parsed.get("hourly_prices", {})
            metadata = parser.extract_metadata(raw_data)

            # Return standardized data structure with ISO timestamps
            return {
                "hourly_raw": hourly_raw,
                "timezone": metadata.get("timezone", "America/Chicago"),
                "currency": metadata.get("currency", "cents"),
                "source_name": "comed",
                "raw_data": {
                    "data": raw_data,
                    "timestamp": now_utc.isoformat(),
                    "area": area
                },
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
        return "America/Chicago"

    def get_parser_for_area(self, area: str) -> Any:
        """Get parser for the area.

        Args:
            area: Area code

        Returns:
            Parser instance
        """
        return ComedParser()

    async def _fetch_data(self, client, area, reference_time):
        """Fetch data from ComEd Hourly Pricing API.

        Args:
            client: API client
            area: Area code
            reference_time: Reference time for the request

        Returns:
            Raw response data
        """
        try:
            # Map area to endpoint if it's a valid ComEd area
            if area in ComEd.AREAS:
                endpoint = area
            else:
                # Default to 5minutefeed if area is not recognized
                _LOGGER.warning(f"Unrecognized ComEd area: {area}, defaulting to 5minutefeed")
                endpoint = ComEd.FIVE_MINUTE_FEED

            # Generate date ranges to try - ComEd uses 5-minute intervals
            date_ranges = generate_date_ranges(reference_time, Source.COMED)

            # Try each date range until we get a valid response
            for start_date, end_date in date_ranges:
                url = f"{ComEd.BASE_URL}?type={endpoint}"

                # ComEd API doesn't use date parameters in the URL, but we log the date range for debugging
                _LOGGER.debug(f"Fetching ComEd data from URL: {url} for date range: {start_date.isoformat()} to {end_date.isoformat()}")

                response = None
                try:
                    async with asyncio.timeout(60):
                        response = await client.fetch(url)
                except TimeoutError:
                    _LOGGER.error("Timeout fetching ComEd data")
                    continue  # Try next date range
                except Exception as e:
                    _LOGGER.error(f"Error fetching ComEd data: {e}")
                    continue  # Try next date range

                if not response:
                    _LOGGER.warning(f"Empty response from ComEd API for date range: {start_date.isoformat()} to {end_date.isoformat()}")
                    continue  # Try next date range

                # If we got a valid response, process it
                if response:
                    break

            # If we've tried all date ranges and still have no data, return None
            if not response:
                _LOGGER.warning("No valid data found from ComEd after trying multiple date ranges")
                return None

            # Check if response is valid
            if isinstance(response, dict) and "error" in response:
                _LOGGER.error(f"Error response from ComEd API: {response.get('message', 'Unknown error')}")
                return None

            # Check if response is valid JSON
            try:
                # If response is already a string, try to parse it as JSON
                if isinstance(response, str):
                    # First try standard JSON parsing
                    json.loads(response)
                # If response is already parsed JSON (dict or list), no need to parse
            except json.JSONDecodeError:
                # If that fails, try to fix the malformed JSON
                try:
                    # Add missing commas between properties
                    fixed_json = re.sub(r'""', '","', response)
                    # Fix array brackets if needed
                    if not fixed_json.startswith('['):
                        fixed_json = '[' + fixed_json
                    if not fixed_json.endswith(']'):
                        fixed_json = fixed_json + ']'
                    json.loads(fixed_json)
                    _LOGGER.debug("Successfully fixed malformed JSON from ComEd API")
                    # Replace the response with the fixed JSON
                    response = fixed_json
                except (json.JSONDecodeError, ValueError) as e:
                    _LOGGER.error(f"Invalid JSON response from ComEd API: {e}")
                    return None

            return {
                "raw_data": response,
                "endpoint": endpoint,
                "url": url
            }
        except Exception as e:
            _LOGGER.error(f"Failed to fetch data from ComEd API: {e}", exc_info=True)
            return None
