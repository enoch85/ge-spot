"""API handler for ENTSO-E Transparency Platform."""
import logging
from datetime import datetime, timezone, timedelta, time
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..utils.debug_utils import sanitize_sensitive_data
from ..timezone import TimezoneService
from ..const.sources import Source
from ..const.areas import AreaMapping
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.api import EntsoE
from ..utils.date_range import generate_date_ranges

# Document types for ENTSO-E API
DOCUMENT_TYPES = ["A44", "A62", "A65"]
from ..const.network import Network, ContentType
from ..const.time import TimeFormat
from ..const.energy import EnergyUnit
from ..const.currencies import Currency
from .parsers.entsoe_parser import EntsoeParser

_LOGGER = logging.getLogger(__name__)

BASE_URL = Network.URLs.ENTSOE

async def fetch_day_ahead_prices(source_type, config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using ENTSO-E API (refactored: returns only raw, standardized data)."""
    client = ApiClient(session=session)
    try:
        # Fetch raw data
        raw_data = await _fetch_data(client, config, area, reference_time)
        if not raw_data:
            return None

        # Check if the API was skipped due to missing API key
        if isinstance(raw_data, dict) and raw_data.get("skipped"):
            return raw_data

        # Use the parser to extract raw, standardized data
        parser = EntsoeParser()
        parsed = parser.parse(raw_data)
        metadata = parser.extract_metadata(raw_data)

        # Build standardized raw result
        result = {
            "hourly_prices": parsed.get("hourly_prices", {}),  # keys: HH:00 or ISO, values: price in EUR
            "currency": metadata.get("currency", "EUR"),
            "timezone": metadata.get("timezone", "Europe/Brussels"),
            "area": area,
            "raw_data": raw_data,  # keep original for debugging/fallback
            "source": Source.ENTSOE,
            "metadata": metadata,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        return result
    finally:
        if not session and client:
            await client.close()

from .base.data_fetch import create_skipped_response

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from ENTSO-E."""
    api_key = config.get(Config.API_KEY) or config.get("api_key")
    if not api_key:
        _LOGGER.debug("No API key provided for ENTSO-E, skipping")
        return create_skipped_response(Source.ENTSOE, "missing_api_key")

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

    for start_date, end_date in date_ranges:
        # Format dates for ENTSO-E API (YYYYMMDDHHMM format)
        period_start = start_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)
        period_end = end_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)

        # Try different document types
        for doc_type in DOCUMENT_TYPES:
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

            response = await client.fetch(
                BASE_URL,
                params=params,
                headers=headers,
                timeout=Network.Defaults.PARALLEL_FETCH_TIMEOUT
            )

            if not response:
                _LOGGER.debug(f"ENTSO-E returned empty response for document type {doc_type} and date range {period_start} to {period_end}")
                continue

            _LOGGER.debug(f"ENTSO-E response type: {type(response)}")
            if isinstance(response, str):
                _LOGGER.debug(f"ENTSO-E response preview: {response[:200]}...")

            # Handle authentication errors
            if isinstance(response, dict) and not response:
                # Empty dictionary usually means HTTP error was encountered
                _LOGGER.error("ENTSO-E API authentication failed: Unauthorized. Check your API key.")
                return create_skipped_response(Source.ENTSOE, "invalid_api_key")

            # Check for authentication errors in string response
            if isinstance(response, str):
                if "Not authorized" in response:
                    _LOGGER.error("ENTSO-E API authentication failed: Not authorized. Check your API key.")
                    return create_skipped_response(Source.ENTSOE, "invalid_api_key")
                elif "No matching data found" in response:
                    # Try next document type
                    _LOGGER.debug(f"ENTSO-E returned 'No matching data found' for document type {doc_type} and date range {period_start} to {period_end}")
                    continue
                elif "Publication_MarketDocument" in response:
                    # We got a valid response with data
                    _LOGGER.info(f"Successfully fetched ENTSO-E data with document type {doc_type} for area {area}")
                    return response
                else:
                    # Unexpected response format, try next document type
                    _LOGGER.debug(f"ENTSO-E returned unexpected response format for document type {doc_type}")
                    continue
            elif isinstance(response, dict):
                # We got a valid response with data
                return response
            else:
                # Unexpected response type
                _LOGGER.debug(f"ENTSO-E returned unexpected response type for document type {doc_type} and date range {period_start} to {period_end}")
                continue

    # If we've tried all date ranges and still have no data, return a structured response
    _LOGGER.warning(f"ENTSO-E: No data found for area {area} after trying multiple date ranges")
    return {
        "hourly_prices": {},
        "raw_data": "No matching data found after trying multiple date ranges",
        "data_source": "ENTSO-E",
        "message": "No matching data found"
    }

async def validate_api_key(api_key, area, session=None):
    """Validate an API key by making a test request."""
    try:
        # Create a simple configuration for validation
        config = {
            "area": area,
            "api_key": api_key
        }

        client = ApiClient(session=session)
        try:
            # Try to fetch data
            result = await _fetch_data(client, config, area, None)

            # Check if we got a valid response
            if result and isinstance(result, str) and "<Publication_MarketDocument" in result:
                return True
            elif isinstance(result, dict) and result.get("hourly_prices") is not None:
                # Valid response with data
                return True
            elif isinstance(result, str) and "Not authorized" in result:
                return False
            elif isinstance(result, str) and "No matching data found" in result:
                # This is a valid key even if there's no data
                return True
            elif isinstance(result, dict) and result.get("skipped") and result.get("reason") == "invalid_api_key":
                return False
            elif isinstance(result, dict) and result.get("message") == "No matching data found":
                # Valid key but no data
                return True
            else:
                # Try one more direct test with a specific document type and date range
                _LOGGER.debug("Trying direct API key validation with specific parameters")

                # Use custom headers for ENTSO-E API
                headers = {
                    "User-Agent": Network.Defaults.USER_AGENT,
                    "Accept": ContentType.XML,
                    "Content-Type": ContentType.XML
                }

                # Map our area code to ENTSO-E area code
                entsoe_area = AreaMapping.ENTSOE_MAPPING.get(area, area)

                # Generate a standard date range for validation
                now = datetime.now(timezone.utc)
                date_ranges = generate_date_ranges(now, Source.ENTSOE, include_historical=False, include_future=False)
                start_date, end_date = date_ranges[0]  # Use just the first range for validation
                period_start = start_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)
                period_end = end_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)

                # Try each document type
                for doc_type in DOCUMENT_TYPES:
                    params = {
                        "securityToken": api_key,
                        "documentType": doc_type,
                        "in_Domain": entsoe_area,
                        "out_Domain": entsoe_area,
                        "periodStart": period_start,
                        "periodEnd": period_end,
                    }

                    # Sanitize params before logging to hide security token
                    sanitized_params = sanitize_sensitive_data(params)
                    _LOGGER.debug(f"ENTSO-E validation params: {sanitized_params}")

                    response = await client.fetch(
                        BASE_URL,
                        params=params,
                        headers=headers,
                        timeout=Network.Defaults.PARALLEL_FETCH_TIMEOUT
                    )

                    if response and isinstance(response, str):
                        if "<Publication_MarketDocument" in response:
                            return True
                        elif "Not authorized" in response:
                            return False

                # If we've tried everything and still can't determine, assume it's invalid
                return False
        finally:
            if not session and client:
                await client.close()

    except Exception as e:
        _LOGGER.error(f"API key validation error: {e}")
        return False
