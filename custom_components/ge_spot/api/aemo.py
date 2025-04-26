"""API handler for AEMO (Australian Energy Market Operator)."""
import logging
from datetime import datetime, timezone
import asyncio
from typing import Dict, Any, Optional, List
import aiohttp

from ..utils.api_client import ApiClient
from ..const.sources import Source
from ..const.api import Aemo
from .parsers.aemo_parser import AemoParser
from ..utils.date_range import generate_date_ranges
from .base.base_price_api import BasePriceAPI
from ..const.currencies import Currency
from ..const.network import Network

_LOGGER = logging.getLogger(__name__)

# Documentation about AEMO's API structure
"""
AEMO (Australian Energy Market Operator) API Details:
-------------------------------------------------------
Unlike European markets, AEMO provides real-time spot prices at 5-minute intervals
rather than daily ahead auctions. The integration works with a consolidated endpoint:

1. ELEC_NEM_SUMMARY - A comprehensive endpoint that contains:
   - Current spot prices for all regions
   - Detailed price information including regulation and contingency prices
   - Market notices

The API provides data for five regions across Australia:
- NSW1 - New South Wales
- QLD1 - Queensland
- SA1  - South Australia
- TAS1 - Tasmania
- VIC1 - Victoria

For more information, see: https://visualisations.aemo.com.au/
"""

class AemoAPI(BasePriceAPI):
    """API client for AEMO (Australian Energy Market Operator)."""

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
        return Source.AEMO

    def _get_base_url(self) -> str:
        """Get the base URL for the API.

        Returns:
            Base URL as string
        """
        # Use constant defined in const/api.py if available, otherwise fallback
        return getattr(Aemo, 'SUMMARY_URL', "https://visualisations.aemo.com.au/aemo/apps/api/report/ELEC_NEM_SUMMARY")

    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Optional[Dict[str, Any]]:
        """Fetch raw price data for the given area.

        Args:
            area: Area code (e.g., NSW1, QLD1, etc.)
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
            # Validate area
            if area not in Aemo.REGIONS:
                _LOGGER.error(f"Invalid AEMO region: {area}. Must be one of {Aemo.REGIONS}")
                # Raise ValueError for consistency in error handling
                raise ValueError(f"Invalid AEMO region: {area}")

            # Generate date ranges to try - AEMO uses 5-minute intervals, but API might accept broader queries
            # The API seems to use a single endpoint returning current state, date range might not be strictly needed
            # but we keep the structure for potential future API changes or fallback strategies.
            date_ranges = generate_date_ranges(reference_time, self._get_source_type())

            # Try each date range (often just one for AEMO)
            for start_date, end_date in date_ranges:
                # AEMO summary API doesn't seem to use date params, but we log the intended range
                _LOGGER.debug(f"Fetching AEMO summary data for area {area} (intended range: {start_date} to {end_date})")

                try:
                    response = await client.fetch(
                        self._get_base_url(),
                        timeout=Network.Defaults.TIMEOUT,
                        response_format='json'
                    )

                    # Check if we got a valid response containing the expected summary array
                    if response and isinstance(response, dict) and Aemo.SUMMARY_ARRAY in response:
                        _LOGGER.info(f"Successfully fetched AEMO summary data for area {area}")
                        # Add area to response for parser context
                        response["areaQueried"] = area
                        return response # Return the raw dictionary
                    else:
                        _LOGGER.warning(f"Invalid or empty response from AEMO for area {area}. Response: {response}")
                        # Continue to next range if applicable, though likely only one range for AEMO
                        continue

                except Exception as fetch_exc:
                    _LOGGER.error(f"Error during AEMO API fetch for area {area}: {fetch_exc}", exc_info=True)
                    # Continue to next range if applicable
                    continue

            # If loop finishes without returning, log warning and return None
            _LOGGER.warning(f"No valid data found from AEMO for area {area} after trying date ranges.")
            return None # Indicate failure

        except ValueError as ve:
             # Catch specific validation errors (like invalid area) and re-raise
             raise ve
        except Exception as e:
            _LOGGER.error(f"Unexpected error fetching AEMO data for area {area}: {e}", exc_info=True)
            return None # Indicate failure
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
        default_timezone = "Australia/Sydney" # AEMO operates across multiple, but Sydney is common
        default_currency = Currency.AUD

        if not raw_data or not isinstance(raw_data, dict):
            _LOGGER.warning("Cannot parse AEMO data: Input is empty or not a dictionary.")
            # Determine a default area if possible, otherwise use a known valid one
            area = raw_data.get("areaQueried", "NSW1") if isinstance(raw_data, dict) else "NSW1"
            return {
                "hourly_prices": {},
                "currency": default_currency,
                "api_timezone": self.get_timezone_for_area(area), # Use method for consistency
                "source": self._get_source_type(),
                "area": area
            }

        # Determine area from the raw data if available
        area = raw_data.get("areaQueried", "NSW1") # Fallback needed if key missing

        parser = self.get_parser_for_area(area)
        try:
            # Parse the main data structure
            # The parser needs to handle the specific structure of the AEMO summary response
            # and extract prices relevant to the 'area'
            parsed = parser.parse(raw_data, area=area) # Pass area to parser
            # Extract metadata separately if needed (parser might handle this)
            metadata = parser.extract_metadata(raw_data, area=area) # Pass area to parser

            # Build standardized result
            result = {
                "hourly_prices": parsed.get("hourly_prices", {}),
                "currency": metadata.get("currency", default_currency),
                # Use specific timezone from method, fallback to metadata then default
                "api_timezone": self.get_timezone_for_area(area) or metadata.get("timezone", default_timezone),
                "area": metadata.get("area", area), # Use metadata area first
                "source": self._get_source_type(),
                # Optionally include raw_data or metadata for debugging
                # "raw_data": raw_data,
                # "metadata": metadata,
            }

            if not result["hourly_prices"]:
                _LOGGER.warning(f"AEMO parsing resulted in empty hourly_prices for area {area}")

            return result

        except Exception as e:
            _LOGGER.error(f"Error parsing AEMO data for area {area}: {e}", exc_info=True)
            return {
                "hourly_prices": {},
                "currency": default_currency,
                "api_timezone": self.get_timezone_for_area(area), # Use method
                "source": self._get_source_type(),
                "area": area,
                "error": str(e)
            }

    def get_timezone_for_area(self, area: str) -> str:
        """Get timezone for the specific AEMO area.

        Args:
            area: Area code (NSW1, QLD1, SA1, TAS1, VIC1)

        Returns:
            Timezone string based on the state.
        """
        # Map AEMO regions to Australian timezones
        timezone_map = {
            "NSW1": "Australia/Sydney", # New South Wales
            "QLD1": "Australia/Brisbane", # Queensland
            "SA1": "Australia/Adelaide", # South Australia
            "TAS1": "Australia/Hobart", # Tasmania
            "VIC1": "Australia/Melbourne" # Victoria
        }
        # Default to Sydney if area is unknown or not provided
        return timezone_map.get(area, "Australia/Sydney")

    def get_parser_for_area(self, area: str) -> Any:
        """Get parser for the area.

        Args:
            area: Area code

        Returns:
            Parser instance
        """
        # AEMO uses the same parser structure, but parsing logic might differ based on area
        return AemoParser()
