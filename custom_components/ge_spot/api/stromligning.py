"""API handler for Stromligning.dk."""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import aiohttp

from .base.api_client import ApiClient
from ..const.sources import Source
from ..const.currencies import Currency
from .parsers.stromligning_parser import StromligningParser
from ..utils.date_range import generate_date_ranges
from .base_api import BaseAPI, PriceData # Import new base and PriceData
from ..api.registry import register_adapter # Import register_adapter
from ..const.time import TimezoneName # Added import
from ..const.config import Config # Added import
from ..const.network import Network # Added import

_LOGGER = logging.getLogger(__name__)

@register_adapter(
    name=Source.STROMLIGNING,
    regions=["DK1", "DK2"], # Supported Danish regions
    default_priority=50 # Example priority
)
class StromligningAPI(BaseAPI): # Inherit from BaseAPI, renamed class
    """Adapter for Stromligning.dk API."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, session: Optional[aiohttp.ClientSession] = None, timezone_service=None):
        super().__init__(config, session)
        self.parser = StromligningParser()
        # self.timezone_service = timezone_service # Keep if used by parser or this adapter

    def _get_base_url(self) -> str:
        # Ensure Stromligning class or constant is available, or hardcode
        # For now, using the hardcoded default from the old class
        return "https://stromligning.dk/api/prices" 

    def get_timezone_for_area(self, area: str) -> str:
        """Stromligning is always Copenhagen time."""
        return TimezoneName.EUROPE_COPENHAGEN

    async def fetch_data(self, area: str) -> PriceData:
        """Fetch and parse data from Stromligning.dk, returning a PriceData object."""
        _LOGGER.debug(f"StromligningAPI: Fetching data for area {area}") # Renamed class in log
        client = ApiClient(session=self.session)
        try:
            supplier = self.config.get(Config.CONF_STROMLIGNING_SUPPLIER)
            if not supplier:
                _LOGGER.error(f"Stromligning supplier ({Config.CONF_STROMLIGNING_SUPPLIER}) is not configured.")
                return PriceData(source=self.api_name, meta={"error": "Supplier not configured"}) # Use self.api_name

            url = f"{self._get_base_url()}?priceArea={area}&supplier={supplier}"
            _LOGGER.debug(f"StromligningAPI: Fetching from {url}") # Renamed class in log
            
            raw_api_response = await client.fetch(
                url,
                timeout=Network.Defaults.TIMEOUT,
                response_format='json'
            )

            if isinstance(raw_api_response, dict) and raw_api_response.get("error"):
                error_msg = raw_api_response.get('message', 'Unknown API error')
                _LOGGER.error(f"Stromligning API error for {area}, supplier {supplier}: {error_msg}")
                return PriceData(source=self.api_name, meta={"error": f"API error: {error_msg}"}) # Use self.api_name

            if not raw_api_response or not isinstance(raw_api_response, dict):
                _LOGGER.warning(f"Stromligning: Unexpected or empty data for {area}, supplier {supplier}.")
                return PriceData(source=self.api_name, meta={"error": "Empty or invalid data received"}) # Use self.api_name

            # --- Parsing --- # 
            # The parser expects the raw API JSON response directly.
            parsed_result = self.parser.parse(raw_api_response)
            
            hourly_prices_from_parser = parsed_result.get("hourly_raw", {}) # dict: {iso_timestamp_str: price}
            final_hourly_prices: List[Dict[str, Any]] = []

            for ts_str, price_value in hourly_prices_from_parser.items():
                try:
                    # Prices from Stromligning are per kWh, ensure parser handles this or adjust here.
                    # Timestamps should be UTC or have timezone info from parser.
                    dt_obj = datetime.fromisoformat(ts_str)
                    final_hourly_prices.append({"start_time": dt_obj, "price": float(price_value)})
                except (ValueError, TypeError) as e:
                    _LOGGER.warning(f"Stromligning: Could not parse/convert entry: {ts_str}, {price_value}. Error: {e}")
            
            final_hourly_prices.sort(key=lambda x: x["start_time"]) # Ensure sorted order

            if not final_hourly_prices and raw_api_response: # If raw data was there but parsing yielded nothing
                 _LOGGER.warning(f"Stromligning: Parsing resulted in no prices for {area}, supplier {supplier}.")
                 # Potentially return error if parsing is expected to always yield data

            # Stromligning API returns prices in DKK and timezone is Copenhagen
            api_timezone = self.get_timezone_for_area(area)
            api_currency = Currency.DKK

            return PriceData(
                hourly_raw=final_hourly_prices,
                timezone=parsed_result.get("timezone", api_timezone), # Use parser's timezone if available
                currency=parsed_result.get("currency", api_currency), # Use parser's currency if available
                source=self.api_name, # Use self.api_name
                meta={
                    "stromligning_area": area,
                    "supplier": supplier,
                    "parser_meta": parsed_result.get("meta", {}),
                    "raw_response_valid": True # Assumed if we reached here after initial checks
                }
            )

        except Exception as e:
            _LOGGER.exception(f"General error in StromligningAPI fetch_data for {area}: {e}") # Renamed class in log
            return PriceData(source=self.api_name, meta={"error": f"General fetch error for {area}: {str(e)}"}) # Use self.api_name
        finally:
            # ApiClient manages its session.
            pass

# Comment out or remove the old StromligningAPI class
# class StromligningAPI(BasePriceAPI):
#     ...
