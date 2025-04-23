"""API handler for OMIE (Operador del Mercado Ibérico de Energía)."""
import logging
from datetime import datetime, timezone, timedelta, time
import csv
import io
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..timezone import TimezoneService
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.currencies import Currency
from ..const.api import Omie
from .parsers.omie_parser import OmieParser
from ..utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

# Base URL template
BASE_URL_TEMPLATE = "https://www.omie.es/sites/default/files/dados/AGNO_{year}/MES_{month}/TXT/INT_PBC_EV_H_1_{day}_{month}_{year}_{day}_{month}_{year}.TXT"

async def fetch_day_ahead_prices(source_type, config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using OMIE API (refactored: returns only raw, standardized data)."""
    client = ApiClient(session=session)
    try:
        # Fetch raw data
        raw_data = await _fetch_data(client, config, area, reference_time)
        if not raw_data:
            return None

        # Use the parser to extract raw, standardized data
        parser = OmieParser()
        parsed = parser.parse(raw_data)
        metadata = parser.extract_metadata(raw_data)

        # Build standardized raw result
        result = {
            "hourly_prices": parsed.get("hourly_prices", {}),  # keys: HH:00 or ISO, values: price in EUR
            "currency": metadata.get("currency", "EUR"),
            "timezone": metadata.get("timezone", "Europe/Madrid"),
            "area": area,
            "raw_data": raw_data,  # keep original for debugging/fallback
            "source": Source.OMIE,
            "metadata": metadata,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from OMIE."""
    try:
        # Get proper date in the local timezone of the area (ES/PT)
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Generate date ranges to try
        date_ranges = generate_date_ranges(reference_time, Source.OMIE)

        # Try each date range until we get a valid response
        for start_date, end_date in date_ranges:
            # OMIE uses the start date for its files
            target_date = start_date.date()
            year = str(target_date.year)
            month = str.zfill(str(target_date.month), 2)
            day = str.zfill(str(target_date.day), 2)

            # Build OMIE URL using template
            url = BASE_URL_TEMPLATE.format(
                year=year, month=month, day=day
            )

            _LOGGER.debug(f"Fetching OMIE data from URL: {url}")

            # Fetch data with built-in retry mechanism - use ISO-8859-1 encoding for Spanish/Portuguese characters
            response = await client.fetch(url, timeout=30, encoding='iso-8859-1')

            # OMIE returns HTML for non-existent files rather than 404
            if not response:
                _LOGGER.warning(f"No response from OMIE for {day}_{month}_{year}, trying next date range")
                continue

            if isinstance(response, str) and ("<html" in response.lower() or "<!doctype" in response.lower()):
                _LOGGER.warning(f"HTML response from OMIE for {day}_{month}_{year}, likely data not available yet, trying next date range")
                continue

            # If we got a valid response, return it
            _LOGGER.info(f"Successfully fetched OMIE data for {day}_{month}_{year}")
            return {
                "raw_data": response,
                "date_str": f"{day}_{month}_{year}",
                "target_date": target_date,
                "url": url
            }

        # If we've tried all date ranges and still have no data, log a warning
        _LOGGER.warning("No valid data found from OMIE after trying multiple date ranges")
        return None
    except Exception as e:
        _LOGGER.error(f"Failed to fetch data from OMIE: {e}")
        return None
