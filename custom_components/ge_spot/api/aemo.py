"""API handler for AEMO (Australian Energy Market Operator)."""
import logging
from datetime import datetime, timezone
import asyncio
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.api import Aemo
from .parsers.aemo_parser import AemoParser
from ..utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

# Documentation about AEMO's API structure
"""
AEMO (Australian Energy Market Operator) API Details:
-------------------------------------------------------
Unlike European markets, AEMO provides real-time spot prices at 5-minute intervals
rather than daily ahead auctions. The integration works with a consolidated endpoint:

1. ELEC_NEM_SUMMARY - A comprehensive endpoint that contains:
   - Current spot prices for all regions
   - Detailed price information including regulation and contingency prices
   - Market notices

The API provides data for five regions across Australia:
- NSW1 - New South Wales
- QLD1 - Queensland
- SA1  - South Australia
- TAS1 - Tasmania
- VIC1 - Victoria

For more information, see: https://visualisations.aemo.com.au/
"""

# Add a note about AEMO's data structure
"""
AEMO provides real-time spot prices rather than day-ahead prices like European markets.
This implementation combines data from multiple AEMO endpoints:
1. Current spot prices from ELEC_NEM_SUMMARY
2. Historical prices from DAILY_PRICE
3. Forecast prices from PREDISPATCH_PRICE

The data is then combined to create a dataset that's compatible with the GE-Spot integration.
If there are missing hours, the fallback manager will try to fill them from other APIs.
"""

async def fetch_day_ahead_prices(
    source_type, config, area, currency, reference_time=None, hass=None, session=None
):
    """Fetch electricity prices using AEMO APIs (refactored: returns only raw, standardized data)."""
    client = ApiClient(session=session)
    try:
        # Validate area
        if area not in Aemo.REGIONS:
            _LOGGER.error(f"Invalid AEMO region: {area}. Must be one of {Aemo.REGIONS}")
            return None

        # Fetch raw data from the consolidated ELEC_NEM_SUMMARY endpoint
        raw_data = await _fetch_summary_data(client, config, area, reference_time)
        if not raw_data:
            _LOGGER.error("Failed to fetch AEMO data")
            return None

        # Use the parser to extract raw, standardized data
        parser = AemoParser()
        parsed = parser.parse(raw_data)
        metadata = parser.extract_metadata(raw_data)

        # Build standardized raw result
        result = {
            "hourly_prices": parsed.get("hourly_prices", {}),  # keys: HH:00 or ISO, values: price in AUD
            "currency": metadata.get("currency", "AUD"),
            "timezone": metadata.get("timezone", "Australia/Sydney"),
            "area": area,
            "raw_data": raw_data,  # keep original for debugging/fallback
            "source": Source.AEMO,
            "metadata": metadata,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_summary_data(client, config, area, reference_time):
    """Fetch data from the consolidated AEMO endpoint."""
    try:
        # Generate date ranges to try - AEMO uses 5-minute intervals
        date_ranges = generate_date_ranges(reference_time, Source.AEMO)

        # Try each date range until we get a valid response
        for start_date, end_date in date_ranges:
            # Format the time for AEMO API - use start_date which is rounded to 5-minute intervals
            formatted_time = start_date.strftime("%Y%m%dT%H%M%S")

            params = {
                "time": formatted_time,
            }

            _LOGGER.debug(f"Fetching AEMO data with params: {params}")
            response = await client.fetch(Aemo.SUMMARY_URL, params=params)

            # If we got a valid response, return it
            if response and Aemo.SUMMARY_ARRAY in response:
                _LOGGER.info(f"Successfully fetched AEMO data with time: {formatted_time}")
                return response
            else:
                _LOGGER.debug(f"No valid data from AEMO for time: {formatted_time}, trying next range")

        # If we've tried all ranges and still have no data, log a warning
        _LOGGER.warning("No valid data found from AEMO after trying multiple date ranges")
        return None
    except Exception as e:
        _LOGGER.error(f"Error fetching AEMO data: {e}")
        return None
