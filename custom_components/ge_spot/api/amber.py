"""API implementation for Amber Energy."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from aiohttp import ClientSession

from .base.base_price_api import BasePriceAPI
from .base.error_handler import retry_with_backoff
from .parsers.amber_parser import AmberParser
from ..const.sources import Source
from ..const.currencies import Currency
from ..const.network import Network
from ..const.api import Amber
from ..utils.api_client import ApiClient
from ..const.config import Config

_LOGGER = logging.getLogger(__name__)

class AmberAPI(BasePriceAPI):
    """API client for Amber Energy."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, session: Optional[ClientSession] = None, timezone_service=None):
        """Initialize the Amber API client."""
        super().__init__(config, session, timezone_service)

    def _get_source_type(self) -> str:
        """Get the source type identifier."""
        return Source.AMBER

    def _get_base_url(self) -> str:
        """Get the base URL for the API."""
        return getattr(Amber, 'BASE_URL', Network.URLs.AMBER) # Use constant if defined

    @retry_with_backoff(max_attempts=Network.Defaults.RETRY_COUNT,
                       base_delay=Network.Defaults.RETRY_BASE_DELAY)
    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> List[Dict[str, Any]]:
        """Fetch raw data from Amber API.

        Args:
            area: The area code (postcode in Australia)
            session: Optional session for API requests
            **kwargs: Additional parameters (expects 'reference_time')

        Returns:
            Raw API response data as a list of dictionaries.
        """
        reference_time = kwargs.get('reference_time')
        if not reference_time:
            reference_time = datetime.now(timezone.utc)

        # Calculate dates for the query (past 24h and next 24h)
        today = reference_time.date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        start_date = yesterday.isoformat()
        end_date = tomorrow.isoformat()

        # Get API key from config
        api_key = self.config.get(Config.API_KEY) # Use Config constant
        if not api_key:
            _LOGGER.error("No API key provided for Amber API in configuration")
            raise ValueError("Missing Amber API key in configuration")

        # Use ApiClient for fetching
        client = ApiClient(session=session or self.session)
        url = f"{self._get_base_url()}/prices?site_id={area}&start_date={start_date}&end_date={end_date}"
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            # Fetch using ApiClient instance
            data = await client.fetch(
                url,
                headers=headers,
                timeout=Network.Defaults.TIMEOUT,
                response_format='json' # Specify expected format
            )

            if not data or not isinstance(data, list):
                _LOGGER.warning(f"Unexpected or empty Amber data format received for area {area}")
                return []

            # Return the raw list of dictionaries
            return data
        except Exception as e:
            _LOGGER.error(f"Error during Amber API request for area {area}: {e}", exc_info=True)
            raise e
        finally:
            if session is None and client:
                await client.close()

    async def parse_raw_data(self, raw_data: Any) -> Dict[str, Any]:
        """Parse raw Amber data into standardized format.

        Args:
            raw_data: Raw API response data (expected List[Dict[str, Any]])

        Returns:
            Parsed data in standardized format (dict with hourly_prices, currency, etc.)
        """
        if not raw_data or not isinstance(raw_data, list):
             _LOGGER.warning("Cannot parse Amber data: Input is empty or not a list.")
             return {
                 "hourly_prices": {},
                 "currency": Currency.AUD,
                 "api_timezone": self.get_timezone_for_area(None),
                 "source": self._get_source_type()
             }

        parser = self.get_parser_for_area(None) # Get parser instance
        try:
            parsed = parser.parse(raw_data) # Pass the raw list

            result = {
                "hourly_prices": parsed.get("hourly_prices", {}),
                "currency": parsed.get("currency", Currency.AUD),
                "api_timezone": self.get_timezone_for_area(None),
                "source": self._get_source_type(),
            }
            return result
        except Exception as e:
            _LOGGER.error(f"Error parsing Amber data: {e}", exc_info=True)
            return {
                 "hourly_prices": {},
                 "currency": Currency.AUD,
                 "api_timezone": self.get_timezone_for_area(None),
                 "source": self._get_source_type(),
                 "error": str(e)
             }

    def get_timezone_for_area(self, area: str) -> str:
        """Get timezone for the area. Amber operates across Australia."""
        return "Australia/Sydney"

    def get_parser_for_area(self, area: str) -> Any:
        """Get parser for the area."""
        return AmberParser()