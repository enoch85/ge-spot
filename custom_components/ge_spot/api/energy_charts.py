"""API handler for Energy-Charts."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from .base.api_client import ApiClient
from ..const.sources import Source
from ..const.currencies import Currency
from ..const.network import Network
from .parsers.energy_charts_parser import EnergyChartsParser
from .base.base_price_api import BasePriceAPI
from .base.error_handler import ErrorHandler

_LOGGER = logging.getLogger(__name__)

class EnergyChartsAPI(BasePriceAPI):
    """Energy-Charts API implementation.
    
    Energy-Charts provides electricity price data from Fraunhofer ISE.
    Data source: Bundesnetzagentur | SMARD.de
    License: CC BY 4.0
    Resolution: 15-minute intervals (96 data points per day)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, session=None, timezone_service=None):
        """Initialize the API.

        Args:
            config: Configuration dictionary
            session: Optional session for API requests
            timezone_service: Optional timezone service
        """
        super().__init__(config, session, timezone_service=timezone_service)
        self.error_handler = ErrorHandler(self.source_type)
        self.parser = EnergyChartsParser()

    def _get_source_type(self) -> str:
        """Get the source type identifier.

        Returns:
            Source type identifier
        """
        return Source.ENERGY_CHARTS

    def _get_base_url(self) -> str:
        """Get the base URL for the API.

        Returns:
            Base URL as string
        """
        return "https://api.energy-charts.info"

    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Dict[str, Any]:
        """Fetch raw price data for the given area.

        Args:
            area: Area code (will be mapped to bidding zone)
            session: Optional session for API requests
            **kwargs: Additional parameters including reference_time

        Returns:
            Raw data from API wrapped in standardized structure
        """
        client = ApiClient(session=session or self.session)
        try:
            return await self.error_handler.run_with_retry(
                self._fetch_data,
                client=client,
                area=area,
                reference_time=kwargs.get('reference_time')
            )
        finally:
            if session is None:
                await client.close()

    async def _fetch_data(
        self, 
        client: ApiClient, 
        area: str, 
        reference_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Fetch data from Energy-Charts API.

        Args:
            client: API client
            area: Area code
            reference_time: Optional reference time for data fetch

        Returns:
            Dictionary containing raw data and metadata for the parser
        """
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Map area to bidding zone (bzn)
        # Energy-Charts uses bidding zone codes like DE-LU, FR, NL, etc.
        # For now, we'll use direct mapping - this will be enhanced with proper area mapping
        bzn = self._map_area_to_bzn(area)
        
        _LOGGER.debug(f"Fetching Energy-Charts data for area: {area}, bzn: {bzn}")

        # Request 2 days of data (today + tomorrow) to reduce API load
        # Energy-Charts is slower with larger date ranges
        # Start from today to ensure we capture current prices
        start_date = reference_time.strftime("%Y-%m-%d")
        end_date = (reference_time + timedelta(days=1)).strftime("%Y-%m-%d")

        params = {
            "bzn": bzn,
            "start": start_date,
            "end": end_date
        }

        try:
            response = await client.fetch(
                f"{self.base_url}/price",
                params=params
            )

            if not response or not isinstance(response, dict):
                _LOGGER.error(f"Energy-Charts API returned invalid response for {area}")
                return None

            # Check for required fields
            if "unix_seconds" not in response or "price" not in response:
                _LOGGER.error(f"Energy-Charts response missing required fields for {area}")
                return None

            # Check if we got data
            if not response.get("unix_seconds") or not response.get("price"):
                _LOGGER.warning(f"Energy-Charts returned empty data for {area}")
                return None

            _LOGGER.debug(
                f"Energy-Charts returned {len(response.get('unix_seconds', []))} data points for {area}"
            )

            # Return standardized structure for parser
            return {
                "raw_data": response,
                "timezone": "Europe/Berlin",  # Energy-Charts API uses CET/CEST
                "currency": Currency.EUR,  # Energy-Charts always returns EUR
                "area": area,
                "bzn": bzn,
                "source": self.source_type,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "license_info": response.get("license_info", "")
            }

        except Exception as e:
            _LOGGER.error(f"Error fetching Energy-Charts data for {area}: {e}")
            return None

    def _map_area_to_bzn(self, area: str) -> str:
        """Map area code to Energy-Charts bidding zone.

        Args:
            area: Area code (e.g., "DE-LU", "FR", "SE1")

        Returns:
            Bidding zone code for Energy-Charts API
        """
        # Energy-Charts bidding zone mapping (38 zones across Europe)
        # Source: https://energy-charts.info/charts/price_spot_market/
        
        bzn_mapping = {
            # Nordic regions
            "SE1": "SE1", "SE2": "SE2", "SE3": "SE3", "SE4": "SE4",
            "NO1": "NO1", "NO2": "NO2", "NO3": "NO3", "NO4": "NO4", "NO5": "NO5",
            "NO2NSL": "NO2NSL",
            "DK1": "DK1", "DK2": "DK2",
            "FI": "FI",
            # Baltic states
            "EE": "EE", "LT": "LT", "LV": "LV",
            # Western Europe
            "DE": "DE-LU", "DE-LU": "DE-LU", "LU": "DE-LU",
            "FR": "FR", "NL": "NL", "BE": "BE", "AT": "AT", "CH": "CH",
            # Central & Eastern Europe
            "PL": "PL", "CZ": "CZ", "SK": "SK", "HU": "HU",
            "RO": "RO", "BG": "BG", "SI": "SI", "HR": "HR", "RS": "RS", "ME": "ME", "GR": "GR",
            # Italy zones
            "IT-North": "IT-North",
            "IT-South": "IT-South",
            "IT-Centre-North": "IT-Centre-North",
            "IT-Centre-South": "IT-Centre-South",
            "IT-Sardinia": "IT-Sardinia",
            "IT-Sicily": "IT-Sicily",
            # Iberia
            "ES": "ES", "PT": "PT",
        }
        
        return bzn_mapping.get(area, area)
