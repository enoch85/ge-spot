"""API handler for ComEd Hourly Pricing."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import asyncio
import json
import re

from ..utils.api_client import ApiClient
from ..timezone import TimezoneService
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.api import ComEd
from .parsers.comed_parser import ComedParser
from ..utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

async def fetch_day_ahead_prices(source_type, config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch electricity prices using ComEd Hourly Pricing API (refactored: returns only raw, standardized data)."""
    client = ApiClient(session=session)
    try:
        # Fetch raw data
        raw_data = await _fetch_data(client, config, area, reference_time)
        if not raw_data:
            _LOGGER.warning(f"No data received from ComEd API for area {area}")
            return None

        # Use the parser to extract raw, standardized data
        parser = ComedParser()
        parsed = parser.parse(raw_data)
        metadata = parser.extract_metadata(raw_data)

        # Build standardized raw result
        result = {
            "hourly_prices": parsed.get("hourly_prices", {}),  # keys: HH:00 or ISO, values: price in cents/kWh
            "currency": metadata.get("currency", "cents"),
            "timezone": metadata.get("timezone", "America/Chicago"),
            "area": area,
            "raw_data": raw_data,  # keep original for debugging/fallback
            "source": Source.COMED,
            "metadata": metadata,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        return result
    except Exception as e:
        _LOGGER.error(f"Error in ComEd fetch_day_ahead_prices: {e}", exc_info=True)
        return None
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from ComEd Hourly Pricing API."""
    try:
        # Map area to endpoint if it's a valid ComEd area
        if area in ComEd.AREAS:
            endpoint = area
        else:
            # Default to 5minutefeed if area is not recognized
            _LOGGER.warning(f"Unrecognized ComEd area: {area}, defaulting to 5minutefeed")
            endpoint = ComEd.FIVE_MINUTE_FEED

        # Generate date ranges to try - ComEd uses 5-minute intervals
        # Ensure reference_time is not None to avoid TypeError
        current_time = reference_time if reference_time is not None else datetime.now(timezone.utc)
        date_ranges = generate_date_ranges(current_time, Source.COMED)

        # Try each date range until we get a valid response
        for start_date, end_date in date_ranges:
            url = f"{ComEd.BASE_URL}?type={endpoint}"

            # ComEd API doesn't use date parameters in the URL, but we log the date range for debugging
            _LOGGER.debug(f"Fetching ComEd data from URL: {url} for date range: {start_date.isoformat()} to {end_date.isoformat()}")

            response = None
            try:
                async with asyncio.timeout(60):
                    response = await client.fetch(url)
            except TimeoutError:
                _LOGGER.error("Timeout fetching ComEd data")
                continue  # Try next date range
            except Exception as e:
                _LOGGER.error(f"Error fetching ComEd data: {e}")
                continue  # Try next date range

            if not response:
                _LOGGER.warning(f"Empty response from ComEd API for date range: {start_date.isoformat()} to {end_date.isoformat()}")
                continue  # Try next date range

            # If we got a valid response, process it
            if response:
                break

        # If we've tried all date ranges and still have no data, return None
        if not response:
            _LOGGER.warning("No valid data found from ComEd after trying multiple date ranges")
            return None

        # Check if response is valid
        if isinstance(response, dict) and "error" in response:
            _LOGGER.error(f"Error response from ComEd API: {response.get('message', 'Unknown error')}")
            return None

        # Check if response is valid JSON
        try:
            # If response is already a string, try to parse it as JSON
            if isinstance(response, str):
                # First try standard JSON parsing
                json.loads(response)
            # If response is already parsed JSON (dict or list), no need to parse
        except json.JSONDecodeError:
            # If that fails, try to fix the malformed JSON
            try:
                # Add missing commas between properties
                fixed_json = re.sub(r'""', '","', response)
                # Fix array brackets if needed
                if not fixed_json.startswith('['):
                    fixed_json = '[' + fixed_json
                if not fixed_json.endswith(']'):
                    fixed_json = fixed_json + ']'
                json.loads(fixed_json)
                _LOGGER.debug("Successfully fixed malformed JSON from ComEd API")
                # Replace the response with the fixed JSON
                response = fixed_json
            except (json.JSONDecodeError, ValueError) as e:
                _LOGGER.error(f"Invalid JSON response from ComEd API: {e}")
                return None

        return {
            "raw_data": response,
            "endpoint": endpoint,
            "url": url
        }
    except Exception as e:
        _LOGGER.error(f"Failed to fetch data from ComEd API: {e}", exc_info=True)
        return None
