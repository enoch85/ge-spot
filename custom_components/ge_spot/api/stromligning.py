"""API handler for Stromligning.dk."""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
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

    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Dict[str, Any]:
        reference_time = kwargs.get('reference_time')
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
        client = ApiClient(session=session or self.session)
        try:
            raw_data = await self._fetch_data(client, area, reference_time)
            if not raw_data:
                return {}
            parser = self.get_parser_for_area(area)
            parsed = parser.parse(raw_data)
            hourly_raw = parsed.get("hourly_prices", {})
            metadata = parser.extract_metadata(raw_data)
            return {
                "hourly_raw": hourly_raw,
                "timezone": metadata.get("timezone", "Europe/Copenhagen"),
                "currency": metadata.get("currency", Currency.DKK),
                "source_name": "stromligning",
                "raw_data": raw_data,
            }
        finally:
            if session is None and client:
                await client.close()

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
