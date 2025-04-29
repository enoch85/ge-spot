"""API handler for ENTSO-E Transparency Platform."""
import logging
import asyncio
from datetime import datetime, timezone, timedelta, time
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional

from .base.api_client import ApiClient
from ..utils.debug_utils import sanitize_sensitive_data
from ..utils.date_range import generate_date_ranges # Re-add this import
from ..timezone import TimezoneService
from ..const.api import EntsoE, SourceTimezone # Update import
from ..const.sources import Source # Add Source import
from ..const.areas import AreaMapping
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.network import Network, ContentType
from ..const.time import TimeFormat
from ..const.energy import EnergyUnit
from ..const.currencies import Currency
from .parsers.entsoe_parser import EntsoeParser
from .base.base_price_api import BasePriceAPI
from .base.error_handler import ErrorHandler
from .base.data_structure import create_standardized_price_data
from .utils import fetch_with_retry
from ..const.time import TimezoneName

_LOGGER = logging.getLogger(__name__)

class EntsoeAPI(BasePriceAPI):
    """API implementation for ENTSO-E Transparency Platform."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, session=None, timezone_service=None):
        """Initialize the API.
        
        Args:
            config: Configuration dictionary
            session: Optional session for API requests
            timezone_service: Optional timezone service
        """
        super().__init__(config, session, timezone_service=timezone_service)
        self.error_handler = ErrorHandler(self.source_type)
        self.parser = EntsoeParser()
    
    def _get_source_type(self) -> str:
        """Get the source type identifier.
        
        Returns:
            Source type identifier
        """
        return Source.ENTSOE
    
    def _get_base_url(self) -> str:
        """Get the base URL for the API.
        
        Returns:
            Base URL as string
        """
        return Network.URLs.ENTSOE
    
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
            # Run the fetch with retry logic
            return await self.error_handler.run_with_retry(
                self._fetch_data,
                client=client,
                area=area,
                reference_time=kwargs.get('reference_time')
            )
        finally:
            if session is None and client:
                await client.close()

    async def _fetch_data(self, client: ApiClient, area: str, reference_time: Optional[datetime] = None) -> Dict[str, Any]:
        api_key = self.config.get(Config.API_KEY) or self.config.get("api_key")
        if not api_key:
            _LOGGER.debug("No API key provided for ENTSO-E, skipping")
            raise ValueError("No API key provided for ENTSO-E")
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
        entsoe_area = AreaMapping.ENTSOE_MAPPING.get(area, area)
        headers = {
            "User-Agent": Network.Defaults.USER_AGENT,
            "Accept": ContentType.XML,
            "Content-Type": ContentType.XML
        }
        date_ranges = generate_date_ranges(reference_time, Source.ENTSOE)
        xml_responses = []
        dict_response_found = None
        found_doc_type = None
        # Try fetching data for each date range
        for start_date, end_date in date_ranges:
            period_start = start_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)
            period_end = end_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)
            doc_types = ["A44", "A65"]
            for doc_type in doc_types:
                params = {
                    "securityToken": api_key,
                    "documentType": doc_type,
                    "in_Domain": entsoe_area,
                    "out_Domain": entsoe_area,
                    "periodStart": period_start,
                    "periodEnd": period_end,
                }
                _LOGGER.debug(f"ENTSO-E fetch: doc_type={doc_type}, range={period_start}-{period_end}, params={params}")
                try:
                    response = await client.fetch(
                        self.base_url,
                        params=params,
                        headers=headers,
                        timeout=Network.Defaults.TIMEOUT
                    )
                    if not response:
                        _LOGGER.debug(f"ENTSO-E empty response for doc_type={doc_type}, range={period_start}-{period_end}")
                        continue
                    if isinstance(response, str):
                        if "Not authorized" in response:
                            _LOGGER.error("ENTSO-E API authentication failed: Not authorized. Check your API key.")
                            raise ValueError("ENTSO-E API authentication failed: Not authorized")
                        elif "No matching data found" in response:
                            _LOGGER.debug(f"ENTSO-E 'No matching data found' for doc_type={doc_type}, range={period_start}-{period_end}")
                            continue
                        elif "Publication_MarketDocument" in response:
                            _LOGGER.info(f"Fetched ENTSO-E XML data with doc_type={doc_type} for area {area}")
                            xml_responses.append(response)
                            break
                        else:
                            _LOGGER.error(f"Unexpected string response from ENTSO-E for doc_type={doc_type}: {response[:200]}...")
                            raise ValueError(f"Unexpected string response from ENTSO-E: {response}")
                    elif isinstance(response, dict) and response:
                        _LOGGER.info(f"Fetched ENTSO-E dict data with doc_type={doc_type} for area {area}")
                        if not dict_response_found:
                            dict_response_found = response
                            found_doc_type = doc_type
                        break
                except asyncio.TimeoutError:
                    _LOGGER.warning(f"ENTSO-E request timed out for doc_type={doc_type}, range={period_start}-{period_end}")
                    continue
                except Exception as e:
                    _LOGGER.error(f"Error fetching ENTSO-E data with doc_type={doc_type}: {e}")
                    continue
            if xml_responses or dict_response_found:
                _LOGGER.info(f"Got valid ENTSO-E response(s) for date range {period_start} to {period_end}, skipping remaining ranges")
                break
        # Tomorrow's data retry logic
        tomorrow_xml = None
        now_utc = datetime.now(timezone.utc)
        now_cet = now_utc.astimezone(timezone(timedelta(hours=1)))
        if now_cet.hour >= 13:
            tomorrow = (reference_time + timedelta(days=1))
            period_start = tomorrow.strftime(TimeFormat.ENTSOE_DATE_HOUR)
            period_end = (tomorrow + timedelta(hours=23)).strftime(TimeFormat.ENTSOE_DATE_HOUR)
            params_tomorrow = {
                "securityToken": api_key,
                "documentType": "A44",
                "in_Domain": entsoe_area,
                "out_Domain": entsoe_area,
                "periodStart": period_start,
                "periodEnd": period_end,
            }
            async def fetch_tomorrow():
                return await client.fetch(self.base_url, params=params_tomorrow, headers=headers, timeout=Network.Defaults.TIMEOUT)
            def is_data_available(data):
                return data and "Publication_MarketDocument" in str(data)
            tomorrow_xml = await fetch_with_retry(
                fetch_tomorrow,
                is_data_available,
                retry_interval=1800,
                end_time=time(23, 50),
                local_tz_name=TimezoneName.EUROPE_PARIS
            )
            if tomorrow_xml:
                xml_responses.append(tomorrow_xml)
        final_result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_timezone": SourceTimezone.API_TIMEZONES[Source.ENTSOE],
            "source": Source.ENTSOE,
            "area": area,
            "entsoe_area": entsoe_area
        }
        if dict_response_found:
            final_result["dict_response"] = dict_response_found
            final_result["document_type"] = found_doc_type
            if xml_responses:
                final_result["xml_responses"] = xml_responses
            return final_result
        elif xml_responses:
            final_result["xml_responses"] = xml_responses
            return final_result
        else:
            _LOGGER.warning(f"ENTSO-E: No data found for area {area} after trying multiple date ranges and document types")
            raise ValueError(f"No matching data found for area {area} after trying multiple date ranges and document types")

    async def parse_raw_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(raw_data, dict):
            _LOGGER.error(f"ENTSOE parse_raw_data expected dict, got {type(raw_data).__name__}: {raw_data}")
            raise ValueError(f"ENTSOE parse_raw_data expected dict, got {type(raw_data).__name__}: {raw_data}")
        xml_responses = raw_data.get("xml_responses", [])
        dict_response = raw_data.get("dict_response")
        all_hourly_prices = {}
        # Parse XML responses if available
        if xml_responses:
            for xml_response in xml_responses:
                parsed = self.parser.parse({"raw_data": xml_response})
                if parsed and "hourly_prices" in parsed:
                    all_hourly_prices.update(parsed["hourly_prices"])
        # Parse dictionary response if available
        if dict_response:
            parsed = self.parser.parse(dict_response)
            if parsed and "hourly_prices" in parsed:
                all_hourly_prices.update(parsed["hourly_prices"])
        return {
            "hourly_raw": all_hourly_prices,
            "timezone": raw_data.get("api_timezone", "Etc/UTC"),
            "currency": "EUR",
            "source_name": "entsoe",
            "raw_data": raw_data,
        }

async def validate_api_key(api_key, area, session=None):
    """Validate an API key by making a test request.
    
    Args:
        api_key: The ENTSO-E API key to validate
        area: Area code to test with
        session: Optional session for API requests
        
    Returns:
        Boolean indicating if the API key is valid
    """
    try:
        _LOGGER.info(f"Validating ENTSO-E API key for area {area}")
        
        # Create a simple configuration for validation
        config = {
            "area": area,
            "api_key": api_key
        }

        # Create a temporary instance of the API
        api = EntsoeAPI(config, session)
        
        # Try to fetch data with minimal parameters
        try:
            await api.fetch_raw_data(area, session)
            _LOGGER.info(f"API key validation successful for area {area}")
            return True
        except ValueError as e:
            if "Not authorized" in str(e) or "authentication failed" in str(e):
                _LOGGER.warning(f"API key validation failed: {e}")
                return False
            elif "No matching data found" in str(e):
                # This is a valid key even if there's no data for this specific area
                _LOGGER.info(f"API key is valid but no data found for area {area}")
                return True
            else:
                # Try alternative areas if this one failed for non-auth reasons
                _LOGGER.warning(f"API key validation encountered an error with area {area}: {e}")
                
                # Try alternative areas that are known to have good data availability
                # These areas were identified in the improvements document
                alternative_areas = ["DE-LU", "FR", "ES", "NL", "BE"]
                
                # Skip the already tried area
                if area in alternative_areas:
                    alternative_areas.remove(area)

                # Try each alternative area
                for alt_area in alternative_areas:
                    _LOGGER.info(f"Trying alternative area {alt_area} for API key validation")
                    try:
                        # Reuse the client but with different area
                        await api.fetch_raw_data(alt_area, session)
                        _LOGGER.info(f"API key validation successful with alternative area {alt_area}")
                        return True
                    except ValueError as alt_e:
                        if "Not authorized" in str(alt_e) or "authentication failed" in str(alt_e):
                            _LOGGER.warning(f"API key validation failed with alternative area {alt_area}: {alt_e}")
                            return False
                        elif "No matching data found" in str(alt_e):
                            # This is a valid key even if there's no data
                            _LOGGER.info(f"API key is valid but no data found for alternative area {alt_area}")
                            return True
                        else:
                            _LOGGER.warning(f"Error with alternative area {alt_area}: {alt_e}")
                            # Continue to the next alternative area
                            continue
                
                # If we get here, all attempts failed but not due to auth issues
                # Assume key is valid if the error is not clearly an auth error
                _LOGGER.info("API key seems valid but encountered data retrieval issues with all areas")
                return True
    except Exception as e:
        _LOGGER.error(f"Error validating ENTSO-E API key: {e}")
        return False
