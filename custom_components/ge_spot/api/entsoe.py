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
from ..timezone.timezone_utils import get_timezone_object

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
        """Fetch data from ENTSO-E API.
        
        Args:
            client: API client
            area: Area code
            reference_time: Optional reference time
            
        Returns:
            Raw data dictionary
        """
        api_key = self.config.get(Config.API_KEY) or self.config.get("api_key")
        if not api_key:
            _LOGGER.debug("No API key provided for ENTSO-E, skipping")
            raise ValueError("No API key provided for ENTSO-E")
            
        # Use the provided reference time or current UTC time
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
            
        # Get the mapped ENTSO-E area code
        entsoe_area = AreaMapping.ENTSOE_MAPPING.get(area, area)
        
        # Set up headers for XML request
        headers = {
            "User-Agent": Network.Defaults.USER_AGENT,
            "Accept": ContentType.XML,
            "Content-Type": ContentType.XML
        }
        
        # Generate date ranges based on the reference time
        date_ranges = generate_date_ranges(reference_time, Source.ENTSOE)
        
        # Initialize storage for responses
        xml_responses = []
        dict_response_found = None
        found_doc_type = None
        last_exception = None
        
        # Try fetching data for each date range
        for start_date, end_date in date_ranges:
            period_start = start_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)
            period_end = end_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)
            
            # Try different document types (A44: day-ahead prices, A65: week-ahead prices)
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
                
                _LOGGER.debug(f"ENTSO-E fetch: doc_type={doc_type}, range={period_start}-{period_end}, params={sanitize_sensitive_data(params)}")
                
                try:
                    response = await client.fetch(
                        self.base_url,
                        params=params,
                        headers=headers,
                        timeout=Network.Defaults.TIMEOUT
                    )

                    # --- Refined Error Handling ---
                    # Explicitly check for the error dictionary format first
                    if isinstance(response, dict) and response.get("error"):
                        status_code = response.get("status_code")
                        message = response.get('message', 'Unknown API error')
                        _LOGGER.error(f"ENTSO-E API error (status {status_code}) for doc_type={doc_type}, range={period_start}-{period_end}: {message}")
                        if status_code == 401:
                            # Raise specific error for auth failure, including message from API if available
                            raise ValueError(f"ENTSO-E API authentication failed (401 Unauthorized). Check your API key. Message: {message}")
                        else:
                            # For other HTTP errors (e.g., 400, 500), log and continue to the next attempt
                            continue # Go to next doc_type/date_range

                    # --- Handle Non-Error Responses ---
                    # If it wasn't an error dict, proceed with normal checks
                    if not response:
                        _LOGGER.debug(f"ENTSO-E empty response for doc_type={doc_type}, range={period_start}-{period_end}")
                        continue

                    if isinstance(response, str):
                        # Check for specific error strings in text/xml response (redundant for 401 now, but good practice)
                        if "Not authorized" in response:
                            _LOGGER.error("ENTSO-E API authentication failed: 'Not authorized' string found in response.")
                            raise ValueError("ENTSO-E API authentication failed: 'Not authorized' string found.")
                        elif "No matching data found" in response:
                            _LOGGER.debug(f"ENTSO-E 'No matching data found' for doc_type={doc_type}, range={period_start}-{period_end}")
                            continue
                        elif "Publication_MarketDocument" in response:
                            _LOGGER.info(f"Fetched ENTSO-E XML data with doc_type={doc_type} for area {area}")
                            xml_responses.append(response)
                            break # Got XML data, break inner loop (doc_types)
                        else:
                            _LOGGER.warning(f"Unexpected string response content from ENTSO-E for doc_type={doc_type}: {response[:200]}...")
                            # Treat as potentially recoverable, continue to next attempt
                            continue
                    elif isinstance(response, dict) and response: # Now this should only catch *valid* dict responses
                        _LOGGER.info(f"Fetched ENTSO-E dict data with doc_type={doc_type} for area {area}")
                        if not dict_response_found:
                            dict_response_found = response
                            found_doc_type = doc_type
                        break # Got dict data, break inner loop (doc_types)
                    else:
                        # Handle unexpected response types if necessary
                        _LOGGER.warning(f"Unexpected response type from ENTSO-E: {type(response).__name__}")
                        continue

                except asyncio.TimeoutError:
                    _LOGGER.warning(f"ENTSO-E request timed out for doc_type={doc_type}, range={period_start}-{period_end}")
                    continue # Go to next doc_type/date_range
                except ValueError as e:
                    # Catch specific ValueErrors raised above (like auth error) or potentially from parsing
                    _LOGGER.error(f"ValueError during ENTSO-E fetch processing for doc_type={doc_type}: {e}")
                    if "authentication failed" in str(e):
                        raise e # Re-raise auth error to be caught by caller (validate_api_key or error_handler)
                    # For other ValueErrors, treat as failure for this attempt and continue
                    continue
                except Exception as e:
                    # Catch other unexpected exceptions during fetch/processing for this attempt
                    _LOGGER.error(f"Unexpected error during ENTSO-E fetch for doc_type={doc_type}: {e}", exc_info=True)
                    continue # Go to next doc_type/date_range
                    
            if xml_responses or dict_response_found:
                _LOGGER.info(f"Got valid ENTSO-E response(s) for date range {period_start} to {period_end}, skipping remaining ranges")
                break
        
        # Tomorrow's data retry logic
        tomorrow_xml = None
        now_utc = datetime.now(timezone.utc)
        # Use the imported function directly
        cet_tz = get_timezone_object("Europe/Paris") # Use Paris time for ENTSO-E
        now_cet = now_utc.astimezone(cet_tz)

        # Define expected release hour (e.g., 13:00 CET)
        release_hour_cet = 13
        # Define a buffer hour to consider it a failure (e.g., 16:00 CET)
        failure_check_hour_cet = 16

        should_fetch_tomorrow = now_cet.hour >= release_hour_cet
        
        if should_fetch_tomorrow:
            tomorrow = (reference_time + timedelta(days=1))
            # Corrected periodEnd for tomorrow to cover the full day
            period_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).strftime(TimeFormat.ENTSOE_DATE_HOUR)
            period_end = (tomorrow.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).strftime(TimeFormat.ENTSOE_DATE_HOUR)
            
            params_tomorrow = {
                "securityToken": api_key,
                "documentType": "A44", # Only fetch DayAhead for tomorrow
                "in_Domain": entsoe_area,
                "out_Domain": entsoe_area,
                "periodStart": period_start,
                "periodEnd": period_end,
            }
            
            async def fetch_tomorrow():
                return await client.fetch(self.base_url, params=params_tomorrow, headers=headers, timeout=Network.Defaults.TIMEOUT)
                
            def is_data_available(data):
                # Check for non-empty string containing the success marker
                return data and isinstance(data, str) and "Publication_MarketDocument" in data
                
            tomorrow_xml = await fetch_with_retry(
                fetch_tomorrow,
                is_data_available,
                retry_interval=1800,
                end_time=time(23, 50),
                local_tz_name=TimezoneName.EUROPE_PARIS
            )
            
            if tomorrow_xml:
                xml_responses.append(tomorrow_xml)

            # --- Fallback Trigger Logic ---
            # If it's past the failure check time and tomorrow's data is still not available/valid,
            # treat this fetch attempt as a failure to trigger fallback.
            if now_cet.hour >= failure_check_hour_cet and not is_data_available(tomorrow_xml):
                _LOGGER.warning(
                    f"ENTSO-E fetch failed for area {area}: Tomorrow's data expected after {failure_check_hour_cet}:00 CET "
                    f"but was not available or invalid. Triggering fallback."
                )
                # Store the specific error before returning None
                last_exception = ValueError(f"Tomorrow's data missing after {failure_check_hour_cet}:00 CET") 
                # Return None to signal failure for tomorrow's data
                return None 
        
        # --- Final Check for Today's Data --- 
        # Ensure we have *some* valid data (today or initial fetch) before proceeding
        if not dict_response_found and not xml_responses:
            _LOGGER.error(f"ENTSO-E fetch failed for area {area}: No valid data found for today either.")
            # If last_exception was set during initial loops or the tomorrow check, use it, otherwise create a generic one
            final_error = last_exception if last_exception else ValueError(f"No valid data found for area {area}")
            # Return the error structure expected by FallbackManager
            return {"attempted_sources": [self.source_type], "error": final_error}

        # Prepare the final result
        final_result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_timezone": SourceTimezone.API_TIMEZONES[Source.ENTSOE],
            "source": Source.ENTSOE,
            "area": area,
            "entsoe_area": entsoe_area,
            # Ensure raw_data key exists for FallbackManager check
            "raw_data": {}
        }
        
        if dict_response_found:
            final_result["dict_response"] = dict_response_found
            final_result["document_type"] = found_doc_type
            # Add to raw_data for parser
            final_result["raw_data"]["dict_response"] = dict_response_found 
        if xml_responses:
            final_result["xml_responses"] = xml_responses
            # Add to raw_data for parser
            final_result["raw_data"]["xml_responses"] = xml_responses
        
        # If raw_data is still empty, something went wrong, signal failure
        if not final_result["raw_data"]:
             _LOGGER.error(f"ENTSO-E logic error: No dict_response or xml_responses added to raw_data for area {area}")
             return None

        return final_result

    async def parse_raw_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse the raw data dictionary fetched by fetch_raw_data."""
        _LOGGER.debug(f"ENTSOE API: Starting parse_raw_data with input keys: {list(raw_data.keys())}")
        
        # The parser expects the dictionary containing 'xml_responses' or 'raw_data'
        # No need to loop here, the parser handles the list internally.
        try:
            # Pass the entire raw_data dictionary directly to the parser instance
            parsed_data = self.parser.parse(raw_data) 
            
            if not parsed_data or not parsed_data.get("hourly_raw"):
                 _LOGGER.warning("ENTSOE API: Parser returned no hourly_raw data.")
                 return {}

            _LOGGER.debug(f"ENTSOE API: Parser returned keys: {list(parsed_data.keys())}")
            
            # Add source name for consistency if not already present
            if "source_name" not in parsed_data:
                parsed_data["source_name"] = Source.ENTSOE

            # Include the original raw data for potential debugging/caching
            parsed_data["raw_data"] = raw_data
            
            # Remove the deprecated key if it exists
            if "hourly_prices" in parsed_data:
                del parsed_data["hourly_prices"]

            return parsed_data

        except Exception as e:
            _LOGGER.error(f"ENTSOE API: Error during parsing: {e}", exc_info=True)
            return {}

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
            # Check specifically for the auth failure string raised in _fetch_data
            if "ENTSO-E API authentication failed" in str(e):
                _LOGGER.warning(f"API key validation failed: {e}")
                return False
            elif "No matching data found" in str(e):
                # This is a valid key even if there's no data for this specific area
                _LOGGER.info(f"API key is valid but no data found for area {area}")
                return True
            else:
                # Try alternative areas if this one failed for non-auth, non-'no data' reasons
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
                        # Create a new config and API instance for the alternative area
                        alt_config = {"area": alt_area, "api_key": api_key}
                        alt_api = EntsoeAPI(alt_config, session)
                        await alt_api.fetch_raw_data(alt_area, session)
                        _LOGGER.info(f"API key validation successful with alternative area {alt_area}")
                        return True
                    except ValueError as alt_e:
                        # Check specifically for auth failure with the alternative area
                        if "ENTSO-E API authentication failed" in str(alt_e):
                            _LOGGER.warning(f"API key validation failed with alternative area {alt_area}: {alt_e}")
                            return False
                        elif "No matching data found" in str(alt_e):
                            _LOGGER.info(f"API key is valid but no data found for alternative area {alt_area}")
                            return True
                        else:
                            _LOGGER.warning(f"Error with alternative area {alt_area}: {alt_e}")
                            continue # Continue to the next alternative area
                
                # If we get here, all attempts failed but not due to auth issues
                # Assume key is valid if the error is not clearly an auth error
                _LOGGER.info("API key seems valid but encountered data retrieval issues with all tested areas")
                return True
    except Exception as e:
        _LOGGER.error(f"Error validating ENTSO-E API key: {e}")
        return False
