"""API handler for Nordpool."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..const.sources import Source
from ..const.currencies import Currency
from ..const.areas import AreaMapping
from ..const.time import TimeFormat
from ..const.network import Network
from ..const.config import Config
from .parsers.nordpool_parser import NordpoolPriceParser
from ..utils.date_range import generate_date_ranges
from .base.base_price_api import BasePriceAPI

_LOGGER = logging.getLogger(__name__)

BASE_URL = Network.URLs.NORDPOOL

class NordpoolAPI(BasePriceAPI):
    async def fetch_raw_data(self, area, session, **kwargs):
        """Fetch raw, per-hour price data for Nordpool."""
        client = ApiClient(session=session)
        try:
            # Fetch raw data from Nordpool
            raw_data = await _fetch_data(client, {}, area, kwargs.get('reference_time'))
            if not raw_data:
                return []
            parser = NordpoolPriceParser()
            parsed = parser.parse(raw_data)
            # Standardize output: list of dicts with ISO datetime, price, currency, timezone
            results = []
            currency = parsed.get("currency", "EUR")
            timezone_str = "Europe/Oslo"  # Could be improved with metadata
            for hour_key, price in parsed.get("hourly_prices", {}).items():
                # Try to parse hour_key as ISO, fallback to today with HH:00
                try:
                    if "T" in hour_key:
                        dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                    else:
                        # Assume today in Oslo time
                        today = datetime.now(timezone.utc).astimezone().date()
                        hour = int(hour_key.split(":")[0])
                        dt = datetime.combine(today, datetime.min.time().replace(hour=hour))
                    iso_dt = dt.isoformat()
                except Exception:
                    iso_dt = hour_key  # fallback
                results.append({
                    "datetime": iso_dt,
                    "price": float(price),
                    "currency": currency,
                    "timezone": timezone_str,
                    "source": Source.NORDPOOL
                })
            return results
        finally:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from Nordpool."""
    try:
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Map from area code to delivery area
        delivery_area = AreaMapping.NORDPOOL_DELIVERY.get(area, area)

        _LOGGER.debug(f"Fetching Nordpool data for area: {area}, delivery area: {delivery_area}")

        # Generate date ranges to try
        # For Nordpool, we need to handle today and tomorrow separately
        # We'll use the date range utility to generate the ranges, but we'll process them differently
        date_ranges = generate_date_ranges(reference_time, Source.NORDPOOL)

        # Fetch today's data (first range is today to tomorrow)
        today_start, today_end = date_ranges[0]
        today = today_start.strftime(TimeFormat.DATE_ONLY)

        params_today = {
            "currency": Currency.EUR,
            "date": today,
            "market": "DayAhead",
            "deliveryArea": delivery_area
        }

        today_data = await client.fetch(BASE_URL, params=params_today)

        # Try to fetch tomorrow's data if it's after 13:00 CET (when typically available)
        tomorrow_data = None
        now_utc = datetime.now(timezone.utc)
        now_cet = now_utc.astimezone(timezone(timedelta(hours=1)))

        if now_cet.hour >= 13:
            # Use the third range which is today to day after tomorrow
            # Extract tomorrow's date from it
            if len(date_ranges) >= 3:
                _, tomorrow_end = date_ranges[2]
                tomorrow = tomorrow_end.strftime(TimeFormat.DATE_ONLY)
            else:
                # Fallback to simple calculation if needed
                tomorrow = (reference_time + timedelta(days=1)).strftime(TimeFormat.DATE_ONLY)

            params_tomorrow = {
                "currency": Currency.EUR,
                "date": tomorrow,
                "market": "DayAhead",
                "deliveryArea": delivery_area
            }

            tomorrow_data = await client.fetch(BASE_URL, params=params_tomorrow)

        return {
            "today": today_data,
            "tomorrow": tomorrow_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        _LOGGER.error(f"Error in _fetch_data for Nordpool: {str(e)}", exc_info=True)
        return None
