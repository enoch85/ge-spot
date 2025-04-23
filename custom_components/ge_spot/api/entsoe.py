"""API handler for ENTSO-E Transparency Platform."""
import logging
from datetime import datetime, timezone, timedelta, time
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional, List

from ..utils.api_client import ApiClient
from ..utils.debug_utils import sanitize_sensitive_data
from ..timezone import TimezoneService
from ..const.sources import Source
from ..const.areas import AreaMapping
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.api import EntsoE
from ..utils.date_range import generate_date_ranges
from ..const.network import Network, ContentType
from ..const.time import TimeFormat
from ..const.energy import EnergyUnit
from ..const.currencies import Currency
from .parsers.entsoe_parser import EntsoeParser
from .base.base_price_api import BasePriceAPI
from .base.error_handler import ErrorHandler
from .base.data_structure import create_standardized_price_data

_LOGGER = logging.getLogger(__name__)

class EntsoeAPI(BasePriceAPI):
    """API implementation for ENTSO-E Transparency Platform."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, session=None):
        """Initialize the API.
        
        Args:
            config: Configuration dictionary
            session: Optional session for API requests
        """
        super().__init__(config, session)
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
        """Fetch data from ENTSO-E.
        
        Args:
            client: API client
            area: Area code
            reference_time: Optional reference time
            
        Returns:
            Raw data from API
        """
        api_key = self.config.get(Config.API_KEY) or self.config.get("api_key")
    if not api_key:
        _LOGGER.debug("No API key provided for ENTSO-E, skipping")
            raise ValueError("No API key provided for ENTSO-E")

    if reference_time is None:
        reference_time = datetime.now(timezone.utc)

    # Map our area code to ENTSO-E area code
    entsoe_area = AreaMapping.ENTSOE_MAPPING.get(area, area)
    _LOGGER.debug(f"Using ENTSO-E area code {entsoe_area} for area {area}")

    # Use custom headers for ENTSO-E API
    headers = {
        "User-Agent": Network.Defaults.USER_AGENT,
        "Accept": ContentType.XML,
        "Content-Type": ContentType.XML
    }

    # Generate date ranges to try
    # ENTSO-E sometimes has data for different time periods depending on the area
    date_ranges = generate_date_ranges(reference_time, Source.ENTSOE)

        # Store all successful responses
        xml_responses = []
        
        # Try fetching data for each date range
    for start_date, end_date in date_ranges:
        # Format dates for ENTSO-E API (YYYYMMDDHHMM format)
        period_start = start_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)
        period_end = end_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)

            # Document types to try - based on ENTSO-E improvements
            doc_types = ["A44", "A62", "A65"]
            doc_type_tasks = []
            
            # Create tasks for all document types to run in parallel
            for doc_type in doc_types:
            # Build query parameters
            params = {
                "securityToken": api_key,
                "documentType": doc_type,
                "in_Domain": entsoe_area,
                "out_Domain": entsoe_area,
                "periodStart": period_start,
                "periodEnd": period_end,
            }

            _LOGGER.debug(f"Trying ENTSO-E with document type {doc_type} and date range: {period_start} to {period_end}")

            # Sanitize params before logging to hide security token
            sanitized_params = sanitize_sensitive_data(params)
            _LOGGER.debug(f"ENTSO-E request params: {sanitized_params}")

                # Create task for fetching with this document type
                task = client.fetch(
                    self.base_url,
                params=params,
                headers=headers,
                timeout=Network.Defaults.PARALLEL_FETCH_TIMEOUT
            )
                doc_type_tasks.append((doc_type, task))
            
            # Wait for all tasks to complete and process results
            import asyncio
            for doc_type, task in doc_type_tasks:
                try:
                    response = await task

            if not response:
                _LOGGER.debug(f"ENTSO-E returned empty response for document type {doc_type} and date range {period_start} to {period_end}")
                continue

            # Handle authentication errors
            if isinstance(response, str):
                if "Not authorized" in response:
                    _LOGGER.error("ENTSO-E API authentication failed: Not authorized. Check your API key.")
                            raise ValueError("ENTSO-E API authentication failed: Not authorized")
                elif "No matching data found" in response:
                            # Log but continue with next document type
                    _LOGGER.debug(f"ENTSO-E returned 'No matching data found' for document type {doc_type} and date range {period_start} to {period_end}")
                    continue
                elif "Publication_MarketDocument" in response:
                    # We got a valid response with data
                    _LOGGER.info(f"Successfully fetched ENTSO-E data with document type {doc_type} for area {area}")
                            xml_responses.append(response)
                    elif isinstance(response, dict) and response:
                        # We got a valid response with data in dictionary format
                        return {
                            "xml_responses": xml_responses,
                            "dict_response": response,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "api_timezone": "Europe/Brussels",  # ENTSO-E typically uses CET/CEST
                            "source": Source.ENTSOE,
                            "area": area,
                            "entsoe_area": entsoe_area,
                            "document_type": doc_type
                        }
                except asyncio.TimeoutError:
                    _LOGGER.warning(f"ENTSO-E request timed out for document type {doc_type} and date range {period_start} to {period_end}")
                except Exception as e:
                    _LOGGER.error(f"Error fetching ENTSO-E data with document type {doc_type}: {str(e)}")
            
            # If we got any valid responses from this date range, don't try the next one
            if xml_responses:
                _LOGGER.info(f"Got valid ENTSO-E responses for date range {period_start} to {period_end}, skipping remaining ranges")
                break

        # If we got any valid XML responses, return them
        if xml_responses:
            return {
                "xml_responses": xml_responses,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "api_timezone": "Europe/Brussels",  # ENTSO-E typically uses CET/CEST
                "source": Source.ENTSOE,
                "area": area,
                "entsoe_area": entsoe_area
            }

        # If we've tried all date ranges and still have no data, raise an error
        _LOGGER.warning(f"ENTSO-E: No data found for area {area} after trying multiple date ranges")
        raise ValueError(f"No matching data found for area {area} after trying multiple date ranges and document types")
    
    async def parse_raw_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw data into standardized format.
        
        Args:
            raw_data: Raw data from API
            
        Returns:
            Parsed data in standardized format
        """
        area = raw_data.get("area")
        api_timezone = raw_data.get("api_timezone", "Europe/Brussels")
        entsoe_area = raw_data.get("entsoe_area", area)  # Use the mapped ENTSO-E area if available
        
        _LOGGER.debug(f"Parsing ENTSO-E data for area {area} (ENTSO-E area: {entsoe_area})")
        
        # Parse data using the ENTSO-E parser
        xml_responses = raw_data.get("xml_responses", [])
        dict_response = raw_data.get("dict_response")
        
        all_hourly_prices = {}
        all_metadata = []
        
        # Parse XML responses if available
        if xml_responses:
            for i, xml_response in enumerate(xml_responses):
                try:
                    parsed = self.parser.parse({"raw_data": xml_response})
                    if parsed and "hourly_prices" in parsed:
                        # Log the number of prices from this response
                        price_count = len(parsed["hourly_prices"])
                        _LOGGER.debug(f"Parsed {price_count} prices from ENTSO-E XML response {i+1}")
                        
                        # Collect metadata for later analysis
                        if "metadata" in parsed:
                            all_metadata.append(parsed["metadata"])
                        
                        # Update hourly prices with new values
                        all_hourly_prices.update(parsed["hourly_prices"])
                except Exception as e:
                    _LOGGER.error(f"Failed to parse ENTSO-E XML response {i+1}: {e}")
        
        # Parse dictionary response if available
        if dict_response:
            try:
                parsed = self.parser.parse(dict_response)
                if parsed and "hourly_prices" in parsed:
                    # Log the number of prices from this response
                    price_count = len(parsed["hourly_prices"])
                    _LOGGER.debug(f"Parsed {price_count} prices from ENTSO-E dictionary response")
                    
                    # Collect metadata
                    if "metadata" in parsed:
                        all_metadata.append(parsed["metadata"])
                    
                    # Update hourly prices
                    all_hourly_prices.update(parsed["hourly_prices"])
            except Exception as e:
                _LOGGER.error(f"Failed to parse ENTSO-E dictionary response: {e}")
        
        # Get current date and time
        now = datetime.now(timezone.utc)
        today = now.date()
        tomorrow = today + timedelta(days=1)
        
        # Convert to market timezone (CET/CEST for ENTSO-E)
        market_tz = timezone(timedelta(hours=1))  # CET/CEST
        now_market = now.astimezone(market_tz)
        
        # Check if we should have tomorrow's prices available
        expect_tomorrow = now_market.hour >= 12  # ENTSO-E publishes tomorrow's prices around noon CET
        
        # Check for completeness of today's data
        expected_hours = set(range(24))
        found_today_hours = set()
        found_tomorrow_hours = set()
        
        for hour_key in all_hourly_prices.keys():
            try:
                dt = None
                if "T" in hour_key:
                    # Format: 2023-01-01T12:00:00[+00:00]
                    dt = datetime.fromisoformat(hour_key.replace("Z", "+00:00"))
                elif ":" in hour_key:
                    # Format: 12:00
                    hour = int(hour_key.split(":")[0])
                    dt = datetime.combine(today, datetime.min.time().replace(hour=hour))
                
                if dt:
                    # Convert to UTC for consistent comparison
                    if dt.tzinfo is None:
                        # If no timezone, assume UTC
                        dt = dt.replace(tzinfo=timezone.utc)
                    
                    # Check if it's today or tomorrow in market timezone
                    dt_market = dt.astimezone(market_tz)
                    dt_date = dt_market.date()
                    
                    if dt_date == today:
                        found_today_hours.add(dt_market.hour)
                    elif dt_date == tomorrow:
                        found_tomorrow_hours.add(dt_market.hour)
            except (ValueError, TypeError) as e:
                _LOGGER.warning(f"Error parsing hour key {hour_key}: {e}")
                continue

        # Check if we have complete data for today
        today_complete = expected_hours.issubset(found_today_hours)
        today_coverage = len(found_today_hours) / 24.0 * 100 if found_today_hours else 0
        
        if not today_complete:
            missing_hours = expected_hours - found_today_hours
            _LOGGER.warning(
                f"Incomplete data from ENTSO-E for area {area} (EIC: {entsoe_area}): missing {len(missing_hours)} hours today "
                f"({sorted(missing_hours)}). Coverage: {today_coverage:.1f}% ({len(found_today_hours)}/24 hours)."
            )
        else:
            _LOGGER.info(f"Complete today data from ENTSO-E for area {area} (EIC: {entsoe_area}). Coverage: 100% (24/24 hours).")
        
        # Check if we have tomorrow's data when expected
        tomorrow_complete = False
        tomorrow_coverage = 0
        
        if expect_tomorrow:
            tomorrow_complete = expected_hours.issubset(found_tomorrow_hours)
            tomorrow_coverage = len(found_tomorrow_hours) / 24.0 * 100 if found_tomorrow_hours else 0
            
            if not tomorrow_complete:
                missing_hours = expected_hours - found_tomorrow_hours
                _LOGGER.warning(
                    f"Incomplete tomorrow data from ENTSO-E for area {area} (EIC: {entsoe_area}): missing {len(missing_hours)} hours "
                    f"({sorted(missing_hours)}). Coverage: {tomorrow_coverage:.1f}% ({len(found_tomorrow_hours)}/24 hours)."
                )
            else:
                _LOGGER.info(f"Complete tomorrow data from ENTSO-E for area {area} (EIC: {entsoe_area}). Coverage: 100% (24/24 hours).")
        else:
            _LOGGER.debug(f"Not expecting tomorrow's prices yet (current market time: {now_market.hour:02d}:00, "
                          f"cutoff is 12:00)")
        
        # Gather the combined metadata
        combined_metadata = {
            "source": Source.ENTSOE,
            "area": area,
            "entsoe_area": entsoe_area,
            "price_count": len(all_hourly_prices),
            "today_complete": today_complete,
            "today_coverage": today_coverage,
            "tomorrow_complete": tomorrow_complete if expect_tomorrow else None,
            "tomorrow_coverage": tomorrow_coverage if expect_tomorrow else None,
            "expect_tomorrow": expect_tomorrow,
            "currency": "EUR",  # Default for ENTSO-E
            "xml_responses_count": len(xml_responses)
        }
        
        # Add any additional metadata from the responses
        for metadata in all_metadata:
            # Add anything not already in combined_metadata
            for key, value in metadata.items():
                if key not in combined_metadata:
                    combined_metadata[key] = value
        
        # Create standardized price data with validation
        result = create_standardized_price_data(
            source=Source.ENTSOE,
            area=area,
            currency=Currency.EUR,  # ENTSO-E returns prices in EUR by default
            hourly_prices=all_hourly_prices,
            reference_time=now,
            api_timezone=api_timezone,
            raw_data=raw_data,
            validate_complete=True,  # Enable validation to ensure we don't calculate stats for incomplete data
            has_tomorrow_prices=expect_tomorrow and tomorrow_complete,
            tomorrow_prices_expected=expect_tomorrow,
            metadata=combined_metadata
        )
        
        # Convert to dictionary
        return result.to_dict()

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
