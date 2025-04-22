"""API handler for Nordpool."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..utils.debug_utils import sanitize_sensitive_data
from ..const.sources import Source
from ..const.currencies import Currency
from ..const.areas import AreaMapping
from ..const.time import TimeFormat, TimezoneName
from ..const.network import Network, ContentType
from ..utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

BASE_URL = Network.URLs.NORDPOOL

# Market types for Nordpool API
MARKET_TYPES = ["DayAhead", "DayAhead-Spot", "DayAhead-Forecast"]

async def fetch_day_ahead_prices(source_type, config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using Nordpool API.
    
    This function only fetches raw data from the API without any processing.
    Processing is handled by the data managers.
    """
    client = ApiClient(session=session)
    try:
        # Fetch raw data
        raw_data = await _fetch_data(client, area, reference_time)
        if not raw_data:
            return None

        # Check if the API was skipped due to any reason
        if isinstance(raw_data, dict) and raw_data.get("skipped"):
            return raw_data

        # Return simplified format with just raw data and metadata
        # This follows the new simplified API response format
        result = {
            "raw_data": raw_data,
            "api_timezone": TimezoneName.UTC,  # Nordpool API uses UTC timezone
            "currency": Currency.EUR  # Nordpool API returns prices in EUR
        }

        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, area, reference_time):
    """Fetch data from Nordpool API."""
    try:
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Map from area code to delivery area
        delivery_area = AreaMapping.NORDPOOL_DELIVERY.get(area, area)

        _LOGGER.debug(f"Fetching Nordpool data for area: {area}, delivery area: {delivery_area}")

        # Use custom headers for Nordpool API
        headers = {
            "User-Agent": Network.Defaults.USER_AGENT,
            "Accept": ContentType.JSON,
            "Content-Type": ContentType.JSON
        }

        # Generate date ranges to try
        date_ranges = generate_date_ranges(reference_time, Source.NORDPOOL)

        # Try different date ranges and market types
        for start_date, end_date in date_ranges:
            # Format dates for Nordpool API (YYYY-MM-DD format)
            end_date_str = end_date.strftime(TimeFormat.DATE_ONLY)

            # Try different market types
            for market_type in MARKET_TYPES:
                params = {
                    "currency": Currency.EUR,
                    "date": end_date_str,
                    "market": market_type,
                    "deliveryArea": delivery_area
                }

                _LOGGER.debug(f"Trying Nordpool with market type {market_type} and date: {params['date']}")
                
                # Sanitize params before logging
                sanitized_params = params.copy()
                _LOGGER.debug(f"Nordpool request params: {sanitized_params}")

                response = await client.fetch(
                    BASE_URL,
                    params=params,
                    headers=headers,
                    timeout=Network.Defaults.PARALLEL_FETCH_TIMEOUT
                )

                if not response:
                    _LOGGER.debug(f"Nordpool returned empty response for market type {market_type} and date {params['date']}")
                    continue

                _LOGGER.debug(f"Nordpool response type: {type(response)}")
                
                # Handle error responses
                if isinstance(response, dict) and not response:
                    # Empty dictionary usually means HTTP error was encountered
                    _LOGGER.error("Nordpool API request failed: Empty response")
                    continue

                # Check for valid response structure
                if isinstance(response, dict) and "multiAreaEntries" in response:
                    # Check if we got data for the requested area
                    entries = response.get("multiAreaEntries", [])
                    if entries and any(area in entry.get("entryPerArea", {}) for entry in entries):
                        _LOGGER.info(f"Successfully fetched Nordpool data with market type {market_type} for area {area} ({len(entries)} entries)")
                        
                        # Now fetch tomorrow's data separately
                        tomorrow = (reference_time + timedelta(days=1)).strftime(TimeFormat.DATE_ONLY)
                        tomorrow_params = {
                            "currency": Currency.EUR,
                            "date": tomorrow,
                            "market": market_type,
                            "deliveryArea": delivery_area
                        }
                        
                        _LOGGER.debug(f"Fetching tomorrow's data for Nordpool area {area} with date: {tomorrow}")
                        tomorrow_response = await client.fetch(
                            BASE_URL,
                            params=tomorrow_params,
                            headers=headers,
                            timeout=Network.Defaults.PARALLEL_FETCH_TIMEOUT
                        )
                        
                        # Check if we got valid tomorrow data
                        if tomorrow_response and isinstance(tomorrow_response, dict) and "multiAreaEntries" in tomorrow_response:
                            tomorrow_entries = tomorrow_response.get("multiAreaEntries", [])
                            _LOGGER.info(f"Successfully fetched tomorrow's data for Nordpool area {area} ({len(tomorrow_entries)} entries)")
                        else:
                            _LOGGER.warning(f"Failed to fetch valid tomorrow's data for Nordpool area {area}")
                            tomorrow_response = None
                        
                        # Create a combined response with both today and tomorrow data
                        combined_response = {
                            "today": response,
                            "tomorrow": tomorrow_response,
                            "market_type": market_type
                        }
                        
                        return combined_response
                else:
                    # Unexpected response format, try next market type
                    _LOGGER.debug(f"Nordpool returned unexpected response format for market type {market_type}")
                    continue

        # If we've tried all date ranges and market types and still don't have data, return a structured response
        _LOGGER.warning(f"Nordpool: No data found for area {area} after trying multiple date ranges and market types")
        return {
            "error": "No matching data found after trying multiple date ranges and market types",
            "data_source": Source.NORDPOOL
        }
    except Exception as e:
        _LOGGER.error(f"Error in _fetch_data for Nordpool: {str(e)}", exc_info=True)
        return None
