"""API handler for Stromligning.dk."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..const.sources import Source
from ..const.config import Config
from .parsers.stromligning_parser import StromligningParser
from ..utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://stromligning.dk/api/prices"

async def fetch_day_ahead_prices(source_type, config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using Stromligning.dk API (refactored: returns only raw, standardized data)."""
    client = ApiClient(session=session)
    try:
        # Fetch raw data
        raw_data = await _fetch_data(client, config, area, reference_time)
        if not raw_data:
            return None

        # Use the parser to extract raw, standardized data
        parser = StromligningParser()
        parsed = parser.parse(raw_data)
        metadata = parser.extract_metadata(raw_data)

        # Build standardized raw result
        result = {
            "hourly_prices": parsed.get("hourly_prices", {}),  # keys: HH:00 or ISO, values: price in DKK
            "currency": metadata.get("currency", "DKK"),
            "timezone": metadata.get("timezone", "Europe/Copenhagen"),
            "area": area,
            "raw_data": raw_data,  # keep original for debugging/fallback
            "source": Source.STROMLIGNING,
            "metadata": metadata,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from Stromligning.dk API."""
    try:
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Generate date ranges to try
        date_ranges = generate_date_ranges(reference_time, Source.STROMLIGNING)

        # Get area code - use the configured area (typically DK1 or DK2)
        area_code = config.get("area", "DK1")

        # Try each date range until we get a valid response
        for start_date, end_date in date_ranges:
            # Stromligning API expects a wider range than just the start/end dates
            # We'll use the start date as "from" and add 2 days to the end date as "to"
            from_date = start_date.date().isoformat() + "T00:00:00"
            to_date = (end_date.date() + timedelta(days=1)).isoformat() + "T23:59:59"

            params = {
                "from": from_date,
                "to": to_date,
                "priceArea": area_code,
                "lean": "false"  # We want the detailed response
            }

            _LOGGER.debug(f"Fetching Stromligning with params: {params}")

            response = await client.fetch(BASE_URL, params=params)

            # Check if we got a valid response with prices
            if response and isinstance(response, dict) and "prices" in response and response["prices"]:
                _LOGGER.info(f"Successfully fetched Stromligning data for {from_date} to {to_date}")
                return response
            else:
                _LOGGER.debug(f"No valid data from Stromligning for {from_date} to {to_date}, trying next range")

        # If we've tried all date ranges and still have no data, log a warning
        _LOGGER.warning("No valid data found from Stromligning after trying multiple date ranges")
        return None
    except Exception as e:
        _LOGGER.error(f"Error fetching Stromligning data: {e}")
        return None
