"""API handler for Stromligning.dk."""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import aiohttp

from .base.api_client import ApiClient
from ..const.sources import Source
from ..const.currencies import Currency
from .parsers.stromligning_parser import StromligningParser
from ..utils.date_range import generate_date_ranges
from .base.base_price_api import BasePriceAPI
from ..const.api import Stromligning
from ..const.network import Network
from ..const.config import Config


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
        # Store config to access supplier later
        self.config = config or {}

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

    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Dict[str, Any]:
        """Fetch raw data from Stromligning.dk API.

        Args:
            area: Area code (e.g., DK1, DK2)
            session: Optional aiohttp session
            **kwargs: Additional keyword arguments (e.g., reference_time)

        Returns:
            Dictionary containing raw data and metadata for the parser.
        """
        reference_time = kwargs.get('reference_time', datetime.now(timezone.utc))
        client = ApiClient(session=session or self.session)
        try:
            # Fetch the raw JSON response from the API
            raw_api_response = await self._fetch_data(client, area, reference_time)

            if not raw_api_response:
                _LOGGER.warning(f"StromligningAPI._fetch_data returned empty for area {area}")
                # Return an empty structure but include essential keys for downstream checks
                return {
                    "raw_data": None,
                    "timezone": self.get_timezone_for_area(area),
                    "currency": Currency.DKK,
                    "area": area,
                    "source": self.source_type,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "source_unit": "kWh",
                }

            # --- No Parsing Here ---
            # The parser will be called later by DataProcessor

            # Return the raw data along with necessary metadata for the parser
            return {
                "raw_data": raw_api_response, # Pass the actual API response
                "timezone": self.get_timezone_for_area(area), # Get timezone based on area
                "currency": Currency.DKK, # Stromligning uses DKK
                "area": area,
                "source": self.source_type,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source_unit": "kWh",  # Specify that Stromligning API returns values in kWh
            }
        finally:
            if session is None and client:
                await client.close()

    async def _fetch_data(self, client: ApiClient, area: str, reference_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Fetch data from Stromligning.dk.

        Args:
            client: API client
            area: Area code (e.g., DK1, DK2)
            reference_time: Optional reference time

        Returns:
            Raw data from API
        """
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Retrieve supplier from configuration using the constant
        supplier = self.config.get(Config.CONF_STROMLIGNING_SUPPLIER)
        if not supplier:
            _LOGGER.error(f"Stromligning supplier ({Config.CONF_STROMLIGNING_SUPPLIER}) is not configured. Please update the integration options.")
            return {}

        # Generate date ranges for today (Stromligning only provides current day data)
        date_ranges = generate_date_ranges(reference_time, Source.STROMLIGNING)
        today_start, today_end = date_ranges[0]

        _LOGGER.debug(f"Fetching Stromligning data for area: {area}, supplier: {supplier}, date range: {today_start} to {today_end}")

        # Fetch from the API - Use priceArea and add supplier
        try:
            url = f"{self._get_base_url()}?priceArea={area}&supplier={supplier}"
            response = await client.fetch(
                url,
                timeout=Network.Defaults.HTTP_TIMEOUT,
            )

            # Check for API-level errors reported in the JSON response
            if isinstance(response, dict) and response.get("error"):
                 _LOGGER.error(f"Stromligning API returned an error for area {area}, supplier {supplier}: {response.get('message', 'Unknown error')}")
                 return {}

            if not response or not isinstance(response, dict):
                _LOGGER.warning(f"Unexpected or empty Stromligning data format received for area {area}, supplier {supplier}")
                return {}

            _LOGGER.debug(f"Successfully fetched Stromligning data for area {area}, supplier {supplier}")
            return response

        except Exception as e:
            _LOGGER.error(f"Error fetching data from Stromligning for area {area}, supplier {supplier}: {e}")
            return {}

    async def parse_raw_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse the raw data fetched from the API.

        Args:
            raw_data: The raw data dictionary from fetch_raw_data.

        Returns:
            Parsed data dictionary.
        """
        if not raw_data or "raw_data" not in raw_data:
            _LOGGER.warning("No raw_data found in input for parsing.")
            return {}

        # Assuming raw_data["raw_data"] holds the actual API response
        api_response = raw_data["raw_data"]
        area = self.config.get(Config.AREA, "DK1") # Get area from config or default

        parser = self.get_parser_for_area(area)
        try:
            parsed = parser.parse(api_response)
            metadata = parser.extract_metadata(api_response) # Extract metadata from the actual response
            # Add metadata that might be in the wrapper dict or from parser
            parsed["timezone"] = raw_data.get("timezone", metadata.get("timezone", "Europe/Copenhagen"))
            parsed["currency"] = raw_data.get("currency", metadata.get("currency", Currency.DKK))
            parsed["source_name"] = raw_data.get("source_name", "stromligning")
            parsed["source_unit"] = raw_data.get("source_unit", "kWh")  # Propagate source unit
            return parsed
        except Exception as e:
            _LOGGER.error(f"Error parsing Stromligning data: {e}", exc_info=True)
            return {}

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
