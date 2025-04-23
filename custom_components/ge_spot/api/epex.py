"""API handler for EPEX SPOT."""
import logging
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..const.sources import Source
from ..const.config import Config
from ..const.display import DisplayUnit
from .parsers.epex_parser import EpexParser
from ..utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.epexspot.com/en/market-results"

async def fetch_day_ahead_prices(source_type, config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using EPEX SPOT API (refactored: returns only raw, standardized data)."""
    client = ApiClient(session=session)
    try:
        # Fetch raw data
        raw_data = await _fetch_data(client, config, area, reference_time)
        if not raw_data:
            return None

        # Use the parser to extract raw, standardized data
        parser = EpexParser()
        parsed = parser.parse(raw_data)
        metadata = parser.extract_metadata(raw_data)

        # Build standardized raw result
        result = {
            "hourly_prices": parsed.get("hourly_prices", {}),  # keys: HH:00 or ISO, values: price in EUR
            "currency": metadata.get("currency", "EUR"),
            "timezone": metadata.get("timezone", "Europe/Berlin"),
            "area": area,
            "raw_data": raw_data,  # keep original for debugging/fallback
            "source": Source.EPEX,
            "metadata": metadata,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from EPEX SPOT."""
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)

    # Generate date ranges to try
    date_ranges = generate_date_ranges(reference_time, Source.EPEX)

    # EPEX uses trading_date and delivery_date
    # We'll use the first range (today to tomorrow) as our primary range
    today_start, tomorrow_end = date_ranges[0]

    # Format dates for the query
    trading_date = today_start.strftime("%Y-%m-%d")
    delivery_date = tomorrow_end.strftime("%Y-%m-%d")

    params = {
        "market_area": area,
        "auction": "MRC",
        "trading_date": trading_date,
        "delivery_date": delivery_date,
        "modality": "Auction",
        "sub_modality": "DayAhead",
        "data_mode": "table"
    }

    _LOGGER.debug(f"Fetching EPEX with params: {params}")

    response = await client.fetch(BASE_URL, params=params)

    # If the first attempt fails, try with other date ranges
    if not response and len(date_ranges) > 1:
        for start_date, end_date in date_ranges[1:]:
            trading_date = start_date.strftime("%Y-%m-%d")
            delivery_date = end_date.strftime("%Y-%m-%d")

            params.update({
                "trading_date": trading_date,
                "delivery_date": delivery_date
            })

            _LOGGER.debug(f"Retrying EPEX with alternate dates - trading: {trading_date}, delivery: {delivery_date}")

            response = await client.fetch(BASE_URL, params=params)
            if response:
                _LOGGER.info(f"Successfully fetched EPEX data with alternate dates")
                break

    return response
