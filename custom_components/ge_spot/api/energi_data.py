"""API handler for Energi Data Service."""
import logging
from datetime import datetime, timezone, timedelta, time
import json
from typing import Dict, Any, Optional

from ..timezone import TimezoneService
from ..utils.api_client import ApiClient
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from .parsers.energi_data_parser import EnergiDataParser
from ..utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.energidataservice.dk/dataset/Elspotprices"

async def fetch_day_ahead_prices(source_type, config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using Energi Data Service API (refactored: returns only raw, standardized data)."""
    client = ApiClient(session=session)
    try:
        # Fetch raw data
        raw_data = await _fetch_data(client, config, area, reference_time)
        if not raw_data:
            return None

        # Use the parser to extract raw, standardized data
        parser = EnergiDataParser()
        parsed = parser.parse(raw_data)
        metadata = parser.extract_metadata(raw_data)

        # Build standardized raw result
        result = {
            "hourly_prices": parsed.get("hourly_prices", {}),  # keys: HH:00, values: price in DKK
            "currency": metadata.get("currency", "DKK"),
            "timezone": metadata.get("timezone", "Europe/Copenhagen"),
            "area": metadata.get("area", area),
            "raw_data": raw_data,  # keep original for debugging/fallback
            "source": Source.ENERGI_DATA_SERVICE,
            "metadata": metadata,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from Energi Data Service."""
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)

    # Generate date ranges to try
    date_ranges = generate_date_ranges(reference_time, Source.ENERGI_DATA_SERVICE)

    # Use area from config
    area_code = config.get("area", "DK1")  # Default to Western Denmark

    # Try each date range until we get a valid response
    for start_date, end_date in date_ranges:
        # Format dates for Energi Data Service API
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        params = {
            "start": f"{start_str}T00:00",
            "end": f"{end_str}T00:00",
            "filter": json.dumps({"PriceArea": area_code}),
            "sort": "HourDK",
            "timezone": "dk",
        }

        _LOGGER.debug(f"Fetching Energi Data Service with params: {params}")

        response = await client.fetch(BASE_URL, params=params)

        # Check if we got a valid response with records
        if response and isinstance(response, dict) and "records" in response and response["records"]:
            _LOGGER.info(f"Successfully fetched Energi Data Service data for {start_str} to {end_str}")
            return response
        else:
            _LOGGER.debug(f"No valid data from Energi Data Service for {start_str} to {end_str}, trying next range")

    # If we've tried all date ranges and still have no data, log a warning
    _LOGGER.warning("No valid data found from Energi Data Service after trying multiple date ranges")
    return None
