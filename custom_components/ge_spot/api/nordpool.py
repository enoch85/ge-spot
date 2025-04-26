"""API handler for Nordpool."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

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
from .base.error_handler import ErrorHandler
from .base.data_structure import create_standardized_price_data

_LOGGER = logging.getLogger(__name__)

class NordpoolAPI(BasePriceAPI):
    """Nordpool API implementation."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, session=None, timezone_service=None):
        """Initialize the API.
        
        Args:
            config: Configuration dictionary
            session: Optional session for API requests
            timezone_service: Optional timezone service
        """
        super().__init__(config, session, timezone_service=timezone_service)
        self.error_handler = ErrorHandler(self.source_type)
        self.parser = NordpoolPriceParser()
    
    def _get_source_type(self) -> str:
        """Get the source type identifier.
        
        Returns:
            Source type identifier
        """
        return Source.NORDPOOL
    
    def _get_base_url(self) -> str:
        """Get the base URL for the API.
        
        Returns:
            Base URL as string
        """
        return Network.URLs.NORDPOOL
    
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
            data = await self.error_handler.run_with_retry(
                self._fetch_data,
                client=client,
                area=area,
                reference_time=kwargs.get('reference_time')
            )
            if not data or not isinstance(data, dict) or not data.get('today'):
                _LOGGER.error(f"Nordpool API returned empty or invalid data for area {area}: {data}")
            return data
        finally:
            if session is None:
                await client.close()
    
    async def _fetch_data(self, client: ApiClient, area: str, reference_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Fetch data from Nordpool.
        
        Args:
            client: API client
            area: Area code
            reference_time: Optional reference time
            
        Returns:
            Raw data from API
        """
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Map from area code to delivery area
        delivery_area = AreaMapping.NORDPOOL_DELIVERY.get(area, area)

        _LOGGER.debug(f"Fetching Nordpool data for area: {area}, delivery area: {delivery_area}")

        # Generate date ranges to try
        # For Nordpool, we need to handle today and tomorrow separately
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

        today_data = await client.fetch(self.base_url, params=params_today)

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

            tomorrow_data = await client.fetch(self.base_url, params=params_tomorrow)

        return {
            "today": today_data,
            "tomorrow": tomorrow_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_timezone": "Europe/Oslo",  # Nordpool uses Central European Time
            "source": Source.NORDPOOL,
            "area": area,
            "delivery_area": delivery_area
        }
    
    async def parse_raw_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw data into standardized format.
        
        Args:
            raw_data: Raw data from API
            
        Returns:
            Parsed data in standardized format
        """
        # Extract data
        today_data = raw_data.get("today")
        tomorrow_data = raw_data.get("tomorrow")
        area = raw_data.get("area")
        api_timezone = raw_data.get("api_timezone", "Europe/Oslo")
        # Parse data using the Nordpool parser, always passing area
        parsed_today = self.parser.parse(today_data, area=area) if today_data else {}
        parsed_tomorrow = self.parser.parse(tomorrow_data, area=area) if tomorrow_data else {}
        
        # Merge hourly prices
        hourly_prices = {}
        hourly_prices.update(parsed_today.get("hourly_prices", {}))
        hourly_prices.update(parsed_tomorrow.get("hourly_prices", {}))
        
        # Get current date and time
        now = datetime.now(timezone.utc)
        today = now.date()
        tomorrow = today + timedelta(days=1)
        
        # Convert to market timezone (usually CET/CEST for Nordpool)
        market_tz = timezone(timedelta(hours=1))  # CET/CEST
        now_market = now.astimezone(market_tz)
        
        # Check if we should have tomorrow's prices available
        expect_tomorrow = now_market.hour >= 13  # Tomorrow's prices typically published after 13:00 CET
        
        # Check for completeness of today's data
        expected_hours = set(range(24))
        found_today_hours = set()
        found_tomorrow_hours = set()
        
        for hour_key in hourly_prices.keys():
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
                    if dt.date() == today:
                        found_today_hours.add(dt.hour)
                    elif dt.date() == tomorrow:
                        found_tomorrow_hours.add(dt.hour)
            except (ValueError, TypeError):
                continue
        
        # Check if we have complete data for today
        today_complete = expected_hours.issubset(found_today_hours)
        if not today_complete:
            missing_hours = expected_hours - found_today_hours
            _LOGGER.warning(
                f"Incomplete data from Nordpool for area {area}: missing {len(missing_hours)} hours today "
                f"({sorted(missing_hours)}). Found {len(found_today_hours)}/24 hours for today."
            )
        
        # Check if we have tomorrow's data when expected
        tomorrow_complete = False
        if expect_tomorrow:
            tomorrow_complete = expected_hours.issubset(found_tomorrow_hours)
            if not tomorrow_complete:
                missing_hours = expected_hours - found_tomorrow_hours
                _LOGGER.warning(
                    f"Incomplete tomorrow data from Nordpool for area {area}: missing {len(missing_hours)} hours "
                    f"({sorted(missing_hours)}). Found {len(found_tomorrow_hours)}/24 hours for tomorrow."
                )
        else:
            _LOGGER.debug(f"Not expecting tomorrow's prices yet (current market time: {now_market.hour:02d}:00, "
                         f"cutoff is 13:00)")
        
        # Create standardized price data using the simplified helper
        # Pass raw hourly_prices (with ISO keys from parser), source currency/timezone
        result = create_standardized_price_data(
            source=Source.NORDPOOL,
            area=area,
            currency=Currency.EUR,  # Nordpool returns prices in EUR by default
            hourly_prices=hourly_prices, # Pass the dict with ISO keys
            reference_time=now,
            api_timezone=api_timezone,
            raw_data=raw_data,
            has_tomorrow_prices=expect_tomorrow and tomorrow_complete,
            tomorrow_prices_expected=expect_tomorrow
        )
        
        # Convert to dictionary
        return result.to_dict()
