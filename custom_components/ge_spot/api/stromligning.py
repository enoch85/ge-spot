"""API handler for Stromligning.dk."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
import aiohttp

from ..utils.api_client import ApiClient
from ..const.sources import Source
from ..const.currencies import Currency
from .parsers.stromligning_parser import StromligningParser
from ..utils.date_range import generate_date_ranges
from .base.base_price_api import BasePriceAPI
from ..const.api import Stromligning
from ..const.network import Network


_LOGGER = logging.getLogger(__name__)

class StromligningAPI(BasePriceAPI):
    """API client for Stromligning.dk."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, session: Optional[aiohttp.ClientSession] = None, timezone_service=None):
        """Initialize the API client.

        Args:
            config: Configuration dictionary
            session: aiohttp client session
            timezone_service: Timezone service instance
        """
        super().__init__(config, session, timezone_service)

    def _get_source_type(self) -> str:
        """Get the source type identifier.

        Returns:
            Source type identifier
        """
        return Source.STROMLIGNING

    def _get_base_url(self) -> str:
        """Get the base URL for the API.

        Returns:
            Base URL as string
        """
        return getattr(Stromligning, 'BASE_URL', "https://stromligning.dk/api/prices")

    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Optional[Dict[str, Any]]:
        """Fetch raw price data for the given area from Stromligning.dk API.

        Args:
            area: Area code (e.g., DK1, DK2)
            session: Optional session for API requests
            **kwargs: Additional parameters (expects 'reference_time')

        Returns:
            Raw API response data as a dictionary, or None if fetch fails.
        """
        reference_time = kwargs.get('reference_time')
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        client = ApiClient(session=session or self.session)
        try:
            # Generate date ranges to try
            # Stromligning often needs a range covering today and tomorrow
            date_ranges = generate_date_ranges(reference_time, self._get_source_type())

            # Use the provided area or default (Stromligning requires an area)
            area_code = area or "DK1" # Default to DK1 if area is not specified

            # Try each date range until we get a valid response
            for start_date, end_date in date_ranges:
                # Stromligning API expects a range, typically covering multiple days
                # Use start date as "from" and end date + 1 day as "to" for robustness
                from_date_str = start_date.strftime("%Y-%m-%dT00:00:00")
                # Ensure end_date covers the full day
                to_date_obj = end_date.replace(hour=23, minute=59, second=59)
                # Extend range slightly to ensure tomorrow's data is captured if available
                if to_date_obj.date() == start_date.date():
                    to_date_obj += timedelta(days=1)
                to_date_str = to_date_obj.strftime("%Y-%m-%dT%H:%M:%S")

                params = {
                    "from": from_date_str,
                    "to": to_date_str,
                    "priceArea": area_code,
                    "lean": "false"  # Request detailed response with components
                }

                _LOGGER.debug(f"Fetching Stromligning with params: {params}")

                response = await client.fetch(
                    self._get_base_url(),
                    params=params,
                    timeout=Network.Defaults.TIMEOUT
                )

                # Check if we got a valid response with prices
                if response and isinstance(response, dict) and "prices" in response and response["prices"]:
                    _LOGGER.info(f"Successfully fetched Stromligning data for {area_code} from {from_date_str} to {to_date_str}")
                    # Add area to response for parser context
                    response["priceAreaUsed"] = area_code
                    return response # Return the raw dictionary
                else:
                    _LOGGER.debug(f"No valid data from Stromligning for {area_code} ({from_date_str} to {to_date_str}), trying next range. Response: {response}")

            # If we've tried all date ranges and still have no data, log a warning
            _LOGGER.warning(f"No valid data found from Stromligning for area {area_code} after trying multiple date ranges.")
            return None # Indicate failure to fetch

        except Exception as e:
            _LOGGER.error(f"Error fetching Stromligning data for area {area_code}: {e}", exc_info=True)
            # Re-raise or return None based on desired error handling (returning None here)
            return None
        finally:
            if session is None and client:
                await client.close()

    async def parse_raw_data(self, raw_data: Any) -> Dict[str, Any]:
        """Parse raw data into standardized format.

        Args:
            raw_data: Raw data from API (expected dict)

        Returns:
            Parsed data in standardized format.
        """
        default_area = "DK1"
        default_timezone = "Europe/Copenhagen"
        default_currency = Currency.DKK

        if not raw_data or not isinstance(raw_data, dict):
            _LOGGER.warning("Cannot parse Stromligning data: Input is empty or not a dictionary.")
            return {
                "hourly_prices": {},
                "currency": default_currency,
                "api_timezone": default_timezone,
                "source": self._get_source_type(),
                "area": default_area
            }

        # Determine area from raw data if possible, otherwise use default
        area = raw_data.get("priceAreaUsed", default_area)

        parser = self.get_parser_for_area(area)
        try:
            # Parse the main data structure
            parsed = parser.parse(raw_data)
            # Extract metadata separately
            metadata = parser.extract_metadata(raw_data)

            # Build standardized result - ONLY include core fields
            result = {
                "hourly_prices": parsed.get("hourly_prices", {}),
                "currency": metadata.get("currency", default_currency),
                "api_timezone": metadata.get("timezone", default_timezone),
                "area": metadata.get("area", area), # Use metadata area first
                "source": self._get_source_type(),
                # Optionally include raw_data or metadata for debugging
                # "raw_data": raw_data,
                # "metadata": metadata,
            }

            if not result["hourly_prices"]:
                _LOGGER.warning(f"Stromligning parsing resulted in empty hourly_prices for area {area}")

            return result

        except Exception as e:
            _LOGGER.error(f"Error parsing Stromligning data for area {area}: {e}", exc_info=True)
            return {
                "hourly_prices": {},
                "currency": default_currency,
                "api_timezone": default_timezone,
                "source": self._get_source_type(),
                "area": area,
                "error": str(e)
            }

    def get_timezone_for_area(self, area: str) -> str:
        """Get timezone for the area.

        Args:
            area: Area code (DK1, DK2)

        Returns:
            Timezone string
        """
        # Denmark uses a single timezone
        return "Europe/Copenhagen"

    def get_parser_for_area(self, area: str) -> Any:
        """Get parser for the area.

        Args:
            area: Area code

        Returns:
            Parser instance
        """
        # Stromligning uses the same parser regardless of area
        return StromligningParser()
