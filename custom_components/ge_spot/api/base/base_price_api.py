"""Base price API interface for standardizing price source implementations."""
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Union

from homeassistant.core import HomeAssistant

from ...utils.api_client import ApiClient
from ...const.sources import Source
from ...const.time import TimeFormat
from ...utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

class BasePriceAPI(ABC):
    """Abstract base class for all price APIs."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, session=None):
        """Initialize the API.
        
        Args:
            config: Configuration dictionary
            session: Optional session for API requests
        """
        self.config = config or {}
        self.session = session
        self.source_type = self._get_source_type()
        self.base_url = self._get_base_url()
        self.client = None

    @abstractmethod
    def _get_source_type(self) -> str:
        """Get the source type identifier.
        
        Returns:
            Source type identifier
        """
        pass
    
    @abstractmethod
    def _get_base_url(self) -> str:
        """Get the base URL for the API.
        
        Returns:
            Base URL as string
        """
        pass
    
    @abstractmethod
    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> List[Dict[str, Any]]:
        """Fetch raw price data for the given area.
        
        Args:
            area: Area code
            session: Optional session for API requests
            **kwargs: Additional parameters
            
        Returns:
            List of standardized price data dictionaries
        """
        pass
    
    @abstractmethod
    async def parse_raw_data(self, raw_data: Any) -> Dict[str, Any]:
        """Parse raw data into standardized format.
        
        Args:
            raw_data: Raw data from API
            
        Returns:
            Parsed data in standardized format
        """
        pass
    
    async def fetch_day_ahead_prices(
        self, 
        area: str,
        currency: str = "EUR",
        reference_time: Optional[datetime] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Fetch day-ahead prices for the given area.

        Args:
            area: The area code (e.g., 'SE1', 'FI')
            currency: The currency code (default: EUR)
            reference_time: Optional reference time for price period
            **kwargs: Additional keyword arguments

        Returns:
            Dictionary with standardized price data
        """
        try:
            _LOGGER.debug(f"{self.source_type}: Fetching day-ahead prices for area {area}")
            
            # Get source timezone for this area
            source_timezone = self.get_timezone_for_area(area)
            
            # Get user/target timezone
            target_timezone = self.timezone_service.get_target_timezone()
            
            # Fetch raw data
            raw_data = await self.fetch_raw_data(area, reference_time, **kwargs)
            if not raw_data:
                _LOGGER.warning(f"{self.source_type}: No data returned for area {area}")
                return {}
                
            # Create parser with our timezone service
            parser = self.get_parser_for_area(area)
            
            # Parse raw data
            parsed_data = parser.parse(raw_data)
            
            # Add area and timezone info
            parsed_data["area"] = area
            parsed_data["api_timezone"] = str(source_timezone)
            parsed_data["target_timezone"] = str(target_timezone)
            
            # Normalize timestamps and separate today/tomorrow data
            if "hourly_prices" in parsed_data and parsed_data["hourly_prices"]:
                normalized_data = parser.normalize_timestamps(
                    parsed_data["hourly_prices"],
                    source_timezone,
                    target_timezone
                )
                
                # Store today's prices
                parsed_data["hourly_prices"] = normalized_data["today"]
                
                # Store tomorrow's prices if available
                if normalized_data["tomorrow"]:
                    parsed_data["tomorrow_hourly_prices"] = normalized_data["tomorrow"]
                    parsed_data["has_tomorrow_prices"] = True
                else:
                    parsed_data["tomorrow_hourly_prices"] = {}
                    parsed_data["has_tomorrow_prices"] = False
                
                # Store any other period prices for potential future use
                if normalized_data["other"]:
                    parsed_data["other_period_prices"] = normalized_data["other"]
            
            # Calculate current and next hour prices
            self._calculate_current_next_hour(parsed_data)
            
            # Calculate statistics if we have complete day data
            self._calculate_statistics(parsed_data)
            
            # Add metadata
            parsed_data["metadata"] = parser.extract_metadata(parsed_data)
            
            return parsed_data
            
        except Exception as e:
            _LOGGER.error(f"Error in fetch_day_ahead_prices for {self.source_type}: {str(e)}", exc_info=True)
            return {}
    
    def _calculate_current_next_hour(self, data: Dict[str, Any]) -> None:
        """Calculate current and next hour prices.
        
        Args:
            data: Parsed price data
        """
        if "hourly_prices" not in data:
            return
        
        hourly_prices = data["hourly_prices"]
        if not hourly_prices:
            return
        
        # Get current hour in the API's timezone
        # This should be handled better with proper timezone conversion
        current_hour = datetime.now(timezone.utc).hour
        current_hour_key = f"{current_hour:02d}:00"
        
        # Find next hour
        next_hour = (current_hour + 1) % 24
        next_hour_key = f"{next_hour:02d}:00"
        
        # Set current and next hour prices
        data["current_price"] = hourly_prices.get(current_hour_key)
        data["next_hour_price"] = hourly_prices.get(next_hour_key)
    
    def _calculate_statistics(self, data: Dict[str, Any]) -> None:
        """Calculate price statistics only when complete data is available.
        
        Args:
            data: Parsed price data
        """
        if "hourly_prices" not in data:
            _LOGGER.debug(f"No hourly_prices field found, skipping statistics calculation")
            return
        
        hourly_prices = data["hourly_prices"]
        if not hourly_prices:
            _LOGGER.debug(f"Empty hourly_prices, skipping statistics calculation")
            return
        
        # Validate we have complete data for today
        today = datetime.now(timezone.utc).date()
        tomorrow = today + timedelta(days=1)
        
        today_complete = self._validate_complete_day_data(hourly_prices, today)
        
        # Get the has_tomorrow_prices flag or default to False
        has_tomorrow_prices = data.get("has_tomorrow_prices", False)
        tomorrow_complete = has_tomorrow_prices and self._validate_complete_day_data(hourly_prices, tomorrow)
        
        if not today_complete:
            _LOGGER.warning(f"Incomplete data for today, skipping today's statistics calculation")
            data["statistics"] = {
                "min": None,
                "max": None,
                "average": None,
                "complete_data": False
            }
        else:
            # Extract prices for today
            today_prices = self._extract_prices_for_date(hourly_prices, today)
            if today_prices:
                # Calculate statistics for today
                data["statistics"] = {
                    "min": min(today_prices) if today_prices else None,
                    "max": max(today_prices) if today_prices else None,
                    "average": sum(today_prices) / len(today_prices) if today_prices else None,
                    "complete_data": True,
                    "peak_hours": self._calculate_peak_hours(hourly_prices, today),
                    "off_peak_hours": self._calculate_off_peak_hours(hourly_prices, today)
                }
            else:
                data["statistics"] = {
                    "min": None,
                    "max": None, 
                    "average": None,
                    "complete_data": False
                }
        
        # Calculate tomorrow's statistics if data is available
        if has_tomorrow_prices and tomorrow_complete:
            tomorrow_prices = self._extract_prices_for_date(hourly_prices, tomorrow)
            if tomorrow_prices:
                data["tomorrow_statistics"] = {
                    "min": min(tomorrow_prices),
                    "max": max(tomorrow_prices),
                    "average": sum(tomorrow_prices) / len(tomorrow_prices),
                    "complete_data": True,
                    "peak_hours": self._calculate_peak_hours(hourly_prices, tomorrow),
                    "off_peak_hours": self._calculate_off_peak_hours(hourly_prices, tomorrow)
                }
            else:
                data["tomorrow_statistics"] = {
                    "min": None,
                    "max": None,
                    "average": None,
                    "complete_data": False
                }
                _LOGGER.warning(f"No prices found for tomorrow despite has_tomorrow_prices being True")
        elif data.get("tomorrow_prices_expected", False):
            _LOGGER.warning(f"Tomorrow's prices expected but incomplete data available")
            data["tomorrow_statistics"] = {
                "min": None,
                "max": None,
                "average": None,
                "complete_data": False
            }
    
    def _validate_complete_day_data(self, hourly_prices: Dict[str, float], date: datetime.date) -> bool:
        """Validate that we have complete data for a given date.
        
        Args:
            hourly_prices: Dictionary mapping hour keys to prices
            date: Date to validate
            
        Returns:
            True if data is complete, False otherwise
        """
        # We should have 24 hours of data for a complete day
        required_hours = set(range(24))
        found_hours = set()
        
        for hour_key in hourly_prices.keys():
            try:
                # Try to extract datetime from hour key formats
                dt = None
                if 'T' in hour_key:
                    # Format: 2023-01-01T12:00:00[+00:00]
                    dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                elif ':' in hour_key:
                    # Format: 12:00
                    hour = int(hour_key.split(':')[0])
                    # We use this just to get the hour
                    dt = datetime.combine(date, datetime.min.time().replace(hour=hour))
                
                # Check if this is the date we want and add the hour
                if dt and dt.date() == date:
                    found_hours.add(dt.hour)
            except (ValueError, TypeError) as e:
                _LOGGER.debug(f"Error extracting datetime from hour key {hour_key}: {e}")
                continue
        
        # Check if we found all required hours
        return required_hours.issubset(found_hours)
    
    def _extract_prices_for_date(self, hourly_prices: Dict[str, float], date: datetime.date) -> List[float]:
        """Extract prices for a specific date.
        
        Args:
            hourly_prices: Dictionary mapping hour keys to prices
            date: Date to extract prices for
            
        Returns:
            List of prices for the specified date
        """
        prices = []
        
        for hour_key, price in hourly_prices.items():
            try:
                # Try to extract datetime from hour key formats
                dt = None
                if 'T' in hour_key:
                    # Format: 2023-01-01T12:00:00[+00:00]
                    dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                    if dt.date() == date:
                        prices.append(price)
            except (ValueError, TypeError):
                continue
        
        return prices
    
    def _calculate_peak_hours(self, hourly_prices: Dict[str, float], date: datetime.date) -> Dict[str, Any]:
        """Calculate peak hour statistics for a specific date.
        
        Args:
            hourly_prices: Hourly prices dictionary
            date: Date to calculate statistics for
            
        Returns:
            Dictionary with peak hour statistics
        """
        # Define peak hours (typically 06:00-22:00)
        peak_prices = []
        peak_hour_keys = []
        
        for hour_key, price in hourly_prices.items():
            try:
                # Try to extract datetime
                dt = None
                if 'T' in hour_key:
                    dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                elif ':' in hour_key:
                    hour = int(hour_key.split(':')[0])
                    dt = datetime.combine(date, datetime.min.time().replace(hour=hour))
                
                # Check if this is a peak hour (6-22) for the date we want
                if dt and dt.date() == date and 6 <= dt.hour < 22:
                    peak_prices.append(price)
                    peak_hour_keys.append(hour_key)
            except (ValueError, TypeError):
                continue
        
        if not peak_prices:
            return {"average": None, "min": None, "max": None, "hours": []}
        
        return {
            "average": sum(peak_prices) / len(peak_prices) if peak_prices else None,
            "min": min(peak_prices) if peak_prices else None,
            "max": max(peak_prices) if peak_prices else None,
            "hours": peak_hour_keys
        }
    
    def _calculate_off_peak_hours(self, hourly_prices: Dict[str, float], date: datetime.date) -> Dict[str, Any]:
        """Calculate off-peak hour statistics for a specific date.
        
        Args:
            hourly_prices: Hourly prices dictionary
            date: Date to calculate statistics for
            
        Returns:
            Dictionary with off-peak hour statistics
        """
        # Define off-peak hours (typically 22:00-06:00)
        off_peak_prices = []
        off_peak_hour_keys = []
        
        for hour_key, price in hourly_prices.items():
            try:
                # Try to extract datetime
                dt = None
                if 'T' in hour_key:
                    dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                elif ':' in hour_key:
                    hour = int(hour_key.split(':')[0])
                    dt = datetime.combine(date, datetime.min.time().replace(hour=hour))
                
                # Check if this is an off-peak hour for the date we want
                if dt and dt.date() == date and (dt.hour >= 22 or dt.hour < 6):
                    off_peak_prices.append(price)
                    off_peak_hour_keys.append(hour_key)
            except (ValueError, TypeError):
                continue
        
        if not off_peak_prices:
            return {"average": None, "min": None, "max": None, "hours": []}
        
        return {
            "average": sum(off_peak_prices) / len(off_peak_prices) if off_peak_prices else None,
            "min": min(off_peak_prices) if off_peak_prices else None,
            "max": max(off_peak_prices) if off_peak_prices else None,
            "hours": off_peak_hour_keys
        }

    def get_timezone_for_area(self, area: str) -> Any:
        """Get the source timezone for the specified area.
        
        Args:
            area: Area code
            
        Returns:
            Timezone object for the area
        """
        # Use TimezoneService to get the area-specific timezone if possible
        if self.timezone_service:
            area_timezone = self.timezone_service.get_area_timezone(area)
            if area_timezone:
                return area_timezone
        
        # Fallback to UTC
        _LOGGER.debug(f"No specific timezone found for area {area}, using UTC")
        return timezone.utc
        
    def get_parser_for_area(self, area: str) -> Any:
        """Get the appropriate parser for the specified area.
        
        Args:
            area: Area code
            
        Returns:
            Parser instance for the area
        """
        # Import here to avoid circular imports
        from ..parsers import get_parser_for_source
        
        # Create parser with our timezone service
        return get_parser_for_source(self.source_type, self.timezone_service) 