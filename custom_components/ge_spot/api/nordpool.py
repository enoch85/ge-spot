"""API handler for Nordpool."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base_api import BaseAPI, PriceData # Updated import
from .registry import register_adapter
from ..const.api import NORDPOOL_AREAS_EURO, NORDPOOL_AREAS_NOK, NORDPOOL_CURRENCY_MAP
from ..const.sources import Source
from ..const.areas import AreaMapping
from ..const.time import TimeFormat
from ..const.network import Network
from ..const.config import Config
from .parsers.nordpool_parser import NordpoolPriceParser
from ..utils.date_range import generate_date_ranges
from .base.error_handler import ErrorHandler
from .utils import fetch_with_retry
from ..const.time import TimezoneName
from ..timezone.timezone_utils import get_timezone_object

_LOGGER = logging.getLogger(__name__)

@register_adapter(
    name=Source.NORDPOOL,
    regions=list(AreaMapping.NORDPOOL_DELIVERY.keys()), # Use keys from AreaMapping
    default_priority=50,
)
class NordpoolAPI(BaseAPI):  # Renamed class and updated base class
    """API client for Nordpool."""

    BASE_URL = "https://www.nordpoolgroup.com/api/marketdata/page/{endpoint}"

    def __init__(self, config: Optional[Dict[str, Any]] = None, session=None, timezone_service=None):
        super().__init__(config, session)
        # self.error_handler = ErrorHandler(Source.NORDPOOL) # Error handling can be part of BaseAPIAdapter or this class
        self.parser = NordpoolPriceParser()
        self.timezone_service = timezone_service # Keep if used, or remove if BaseAPIAdapter handles it

    def _get_base_url(self) -> str:
        return Network.URLs.NORDPOOL

    async def fetch_data(self, area: str) -> PriceData:
        """Fetch data from Nordpool API and convert to standard PriceData format."""
        _LOGGER.debug(f"NordpoolAPI: Fetching data for area {area}") # Renamed class in log
        now_utc = datetime.now(timezone.utc)
        currency = self._get_currency_for_area(area)
        endpoint, params = self._get_endpoint_and_params(area, currency)

        if not endpoint:
            _LOGGER.error(f"NordpoolAPI: No endpoint configured for area {area}") # Renamed class in log
            return PriceData(source=self.api_name, meta={"error": f"No endpoint for {area}"})

        try:
            api_data = await self._fetch_json(endpoint, params=params)
            if not api_data or "data" not in api_data or not api_data["data"]:
                _LOGGER.warning(f"NordpoolAPI: No data received from API for {area}. Response: {str(api_data)[:200]}") # Renamed class in log
                return PriceData(source=self.api_name, meta={"error": f"No data from API for {area}"})

            raw_prices = api_data["data"].get("Rows", [])
            if not raw_prices:
                _LOGGER.warning(f"NordpoolAPI: 'Rows' missing or empty in data for {area}. Data: {str(api_data['data'])[:200]}") # Renamed class in log
                return PriceData(source=self.api_name, meta={"error": f"'Rows' missing/empty for {area}"})

            # Determine the timezone for the area (Nordpool data is typically CET/CEST)
            # This might need to be more sophisticated if Nordpool serves data for multiple timezones directly
            # For now, assume Europe/Oslo as a common Nordpool timezone.
            # TODO: Confirm if Nordpool API provides timezone or if it's always CET/CEST.
            # For areas like LT, LV, EE, it's their respective local timezones.
            # The API response itself doesn't seem to specify timezone for timestamps.
            # We will assume the timestamps are in the local time of the bidding zone.
            # This needs careful handling if the API provides UTC or a fixed timezone.
            # For now, we'll use a helper to get a best-guess timezone.
            price_timezone_str = self._get_timezone_for_area(area)


            hourly_prices = self._parse_nordpool_data(raw_prices, price_timezone_str, area)

            if not hourly_prices:
                _LOGGER.warning(f"NordpoolAPI: Parsing resulted in no prices for {area}") # Renamed class in log
                return PriceData(source=self.api_name, meta={"error": f"Parsing failed for {area}"})

            return PriceData(
                hourly_raw=hourly_prices,
                timezone=price_timezone_str, # Store the determined timezone
                currency=currency,
                source=self.api_name,  # Use api_name from BaseAPI
                meta={
                    "api_response_snippet": str(api_data)[:200],
                    "fetch_timestamp_utc": now_utc.isoformat(),
                    "original_area_code": area # Store the original area code used for the fetch
                },
            )
        except Exception as e:
            _LOGGER.exception(f"NordpoolAPI: Error fetching or parsing data for {area}: {e}") # Renamed class in log
            return PriceData(
                source=self.api_name,  # Use api_name from BaseAPI
                meta={"error": f"Exception for {area}: {str(e)}"}
            )

    def _get_timezone_for_area(self, area: str) -> str:
        # Simplified timezone mapping. This should ideally come from a more robust source
        # or be part of the area configuration.
        # Nordpool areas are typically in CET/CEST or EET/EEST.
        # Example: Oslo is Europe/Oslo, Helsinki is Europe/Helsinki.
        # This is a placeholder and might need refinement.
        if area in ["FI", "EE", "LT", "LV"]:
            return f"Europe/{area.capitalize()}" # FI -> Europe/Fi (Incorrect, needs mapping)
                                                # Correct mapping:
                                                # FI -> Europe/Helsinki
                                                # EE -> Europe/Tallinn
                                                # LT -> Europe/Vilnius
                                                # LV -> Europe/Riga"
        # Most other Nordpool areas are CET/CEST.
        # Defaulting to Europe/Oslo as a common one.
        # A more precise mapping based on Nordpool's bidding zones is needed for accuracy.
        # For now, this is a simplification.
        area_tz_map = {
            "FI": "Europe/Helsinki",
            "EE": "Europe/Tallinn",
            "LT": "Europe/Vilnius",
            "LV": "Europe/Riga",
            "SE1": "Europe/Stockholm", "SE2": "Europe/Stockholm", "SE3": "Europe/Stockholm", "SE4": "Europe/Stockholm",
            "NO1": "Europe/Oslo", "NO2": "Europe/Oslo", "NO3": "Europe/Oslo", "NO4": "Europe/Oslo", "NO5": "Europe/Oslo",
            "DK1": "Europe/Copenhagen", "DK2": "Europe/Copenhagen",
            # Add other specific mappings if known
        }
        # Fallback for areas not explicitly mapped (e.g., AT, BE, DE-LU, FR, NL from day-ahead web)
        # These are typically CET.
        return area_tz_map.get(area, "Europe/Oslo") # Default to Oslo if not found
