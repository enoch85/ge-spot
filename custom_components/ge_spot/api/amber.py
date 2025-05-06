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
from .base.api_client import ApiClient
from ..const.config import Config

_LOGGER = logging.getLogger(__name__)

class AmberAPI(BasePriceAPI):
    """API client for Amber Energy."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, session: Optional[ClientSession] = None, timezone_service=None):
        """Initialize the Amber API client.

        Args:
            config: Configuration dictionary
            session: Optional aiohttp client session
            timezone_service: Optional timezone service
        """
        super().__init__(config, session, timezone_service)

    def _get_source_type(self) -> str:
        """Get the source type identifier.

        Returns:
            Source type identifier
        """
        return Source.AMBER

    def _get_base_url(self) -> str:
        """Get the base URL for the API.

        Returns:
            Base URL as string
        """
        return getattr(Amber, 'BASE_URL', Network.URLs.AMBER) # Use constant if defined

    @retry_with_backoff(max_attempts=Network.Defaults.RETRY_COUNT,
                       base_delay=Network.Defaults.RETRY_BASE_DELAY)
    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Dict[str, Any]:
        """Fetch raw data from Amber API.

        Args:
            area: The area code (postcode in Australia)
            session: Optional session for API requests
            **kwargs: Additional parameters

        Returns:
            Raw API response data as a dictionary with standardized structure.
        """
        # Use current time as reference
        now_utc = datetime.now(timezone.utc)

        # Calculate date range for the API request (yesterday to tomorrow)
        today = now_utc.date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        start_date = yesterday.isoformat()
        end_date = tomorrow.isoformat()

        # Get API key from configuration
        api_key = self.config.get(Config.API_KEY)
        if not api_key:
            _LOGGER.error("No API key provided for Amber API in configuration")
            raise ValueError("Missing Amber API key in configuration")

        client = ApiClient(session=session or self.session)
        url = f"{self._get_base_url()}/prices?site_id={area}&start_date={start_date}&end_date={end_date}"
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            # Fetch data from Amber API
            data = await client.fetch(
                url,
                headers=headers,
                timeout=Network.Defaults.TIMEOUT,
                response_format='json'
            )

            if not data or not isinstance(data, list):
                _LOGGER.warning(f"Unexpected or empty Amber data format received for area {area}")
                return {}

            # Parse the response
            parser = self.get_parser_for_area(None)
            parsed = parser.parse(data) if data else {}
            hourly_raw = parsed.get("hourly_prices", {})

            # Return standardized data structure with ISO timestamps
            return {
                "hourly_raw": hourly_raw,
                "timezone": self.get_timezone_for_area(None),
                "currency": Currency.AUD,
                "source_name": "amber",
                "raw_data": {
                    "data": data,
                    "timestamp": now_utc.isoformat(),
                    "area": area,
                    "date_range": {
                        "start": start_date,
                        "end": end_date
                    }
                },
            }
        except Exception as e:
            _LOGGER.error(f"Error during Amber API request for area {area}: {e}", exc_info=True)
            return {}
        finally:
            if session is None and client:
                await client.close()

    def get_timezone_for_area(self, area: str) -> str:
        """Get timezone for the area. Amber operates across Australia.

        Args:
            area: Area code (not used in this implementation)

        Returns:
            Timezone string
        """
        return "Australia/Sydney"

    def get_parser_for_area(self, area: str) -> Any:
        """Get parser for the area.

        Args:
            area: Area code (not used in this implementation)

        Returns:
            Parser instance
        """
        return AmberParser()