"""Data validity tracking for electricity spot prices.

This module provides tracking of how far into the future we have valid price data,
replacing the old 'complete_data' boolean with clear timestamp-based validity.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import logging

_LOGGER = logging.getLogger(__name__)


@dataclass
class DataValidity:
    """Track how far into the future we have valid price data.
    
    This replaces the ambiguous 'complete_data' boolean with clear timestamps
    that answer: "How long is our data valid for?"
    """
    
    # The last interval timestamp we have data for
    # e.g., "2025-10-03 23:45:00+02:00" means we have data up to and including this interval
    last_valid_interval: Optional[datetime] = None
    
    # When our data coverage runs out (same as last_valid_interval + interval duration)
    # This is the key field for decision making
    # If not provided, will be set to last_valid_interval
    data_valid_until: Optional[datetime] = None
    
    # Total number of intervals we have (for both today and tomorrow combined)
    interval_count: int = 0
    
    # Number of intervals we have for today specifically
    today_interval_count: int = 0
    
    # Number of intervals we have for tomorrow specifically  
    tomorrow_interval_count: int = 0
    
    # Whether we have data for the current interval (RIGHT NOW)
    # This is critical - if False, we MUST fetch immediately
    has_current_interval: bool = False
    
    # Whether we have at least the rest of today's data
    # (minimum viable data to keep the system running)
    has_minimum_data: bool = False
    
    def __post_init__(self):
        """Set data_valid_until to last_valid_interval if not provided."""
        if self.last_valid_interval and not self.data_valid_until:
            self.data_valid_until = self.last_valid_interval
    
    def hours_remaining(self, now: datetime) -> float:
        """Calculate how many hours of data we have remaining.
        
        Args:
            now: Current datetime
            
        Returns:
            Hours of data remaining, or 0 if no valid data
        """
        if not self.data_valid_until:
            return 0.0
            
        remaining_seconds = (self.data_valid_until - now).total_seconds()
        return max(0.0, remaining_seconds / 3600.0)
    
    def is_valid(self) -> bool:
        """Check if this validity object represents valid data.
        
        Returns:
            True if we have at least some valid data
        """
        return (
            self.last_valid_interval is not None 
            and self.data_valid_until is not None
            and self.interval_count > 0
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage/logging.
        
        Returns:
            Dictionary representation
        """
        return {
            "last_valid_interval": self.last_valid_interval.isoformat() if self.last_valid_interval else None,
            "data_valid_until": self.data_valid_until.isoformat() if self.data_valid_until else None,
            "interval_count": self.interval_count,
            "today_interval_count": self.today_interval_count,
            "tomorrow_interval_count": self.tomorrow_interval_count,
            "has_current_interval": self.has_current_interval,
            "has_minimum_data": self.has_minimum_data,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DataValidity":
        """Create from dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            DataValidity instance
        """
        from homeassistant.util import dt as dt_util
        
        return cls(
            last_valid_interval=dt_util.parse_datetime(data["last_valid_interval"]) if data.get("last_valid_interval") else None,
            data_valid_until=dt_util.parse_datetime(data["data_valid_until"]) if data.get("data_valid_until") else None,
            interval_count=data.get("interval_count", 0),
            today_interval_count=data.get("today_interval_count", 0),
            tomorrow_interval_count=data.get("tomorrow_interval_count", 0),
            has_current_interval=data.get("has_current_interval", False),
            has_minimum_data=data.get("has_minimum_data", False),
        )
    
    def __str__(self) -> str:
        """String representation for logging."""
        if not self.is_valid():
            return "DataValidity(no valid data)"
            
        return (
            f"DataValidity("
            f"valid_until={self.data_valid_until.strftime('%Y-%m-%d %H:%M') if self.data_valid_until else 'None'}, "
            f"intervals={self.interval_count} "
            f"(today={self.today_interval_count}, tomorrow={self.tomorrow_interval_count}), "
            f"has_current={self.has_current_interval})"
        )


def calculate_data_validity(
    interval_prices: dict,
    tomorrow_interval_prices: dict,
    now: datetime,
    current_interval_key: str
) -> DataValidity:
    """Calculate data validity from interval price dictionaries.
    
    This analyzes the price data to determine:
    - How far into the future we have data
    - Whether we have current interval data
    - Whether we have minimum viable data
    
    Args:
        interval_prices: Today's interval prices {interval_key: price}
        tomorrow_interval_prices: Tomorrow's interval prices {interval_key: price}
        now: Current datetime
        current_interval_key: Current interval key (e.g., "18:15")
        
    Returns:
        DataValidity object with calculated values
    """
    from homeassistant.util import dt as dt_util
    
    validity = DataValidity()
    
    # Count intervals
    validity.today_interval_count = len(interval_prices)
    validity.tomorrow_interval_count = len(tomorrow_interval_prices)
    validity.interval_count = validity.today_interval_count + validity.tomorrow_interval_count
    
    # Check if we have current interval
    validity.has_current_interval = current_interval_key in interval_prices
    
    # Find the last valid interval timestamp
    all_intervals = []
    today_date = now.date()
    
    # Parse today's intervals
    for interval_key in interval_prices.keys():
        try:
            hour, minute = map(int, interval_key.split(':'))
            interval_dt = datetime.combine(today_date, datetime.min.time().replace(hour=hour, minute=minute))
            # Make timezone aware using the current timezone
            interval_dt = dt_util.as_local(interval_dt)
            all_intervals.append(interval_dt)
        except (ValueError, AttributeError) as e:
            _LOGGER.warning(f"Failed to parse interval key '{interval_key}': {e}")
            continue
    
    # Parse tomorrow's intervals
    from datetime import timedelta
    tomorrow_date = today_date + timedelta(days=1)
    for interval_key in tomorrow_interval_prices.keys():
        try:
            hour, minute = map(int, interval_key.split(':'))
            interval_dt = datetime.combine(tomorrow_date, datetime.min.time().replace(hour=hour, minute=minute))
            # Make timezone aware using the current timezone
            interval_dt = dt_util.as_local(interval_dt)
            all_intervals.append(interval_dt)
        except (ValueError, AttributeError) as e:
            _LOGGER.warning(f"Failed to parse interval key '{interval_key}': {e}")
            continue
    
    if all_intervals:
        # Sort to find the last interval
        all_intervals.sort()
        validity.last_valid_interval = all_intervals[-1]
        
        # Add interval duration (15 minutes) to get data_valid_until
        from datetime import timedelta
        validity.data_valid_until = validity.last_valid_interval + timedelta(minutes=15)
        
        # Check if we have minimum data (at least rest of today)
        # This means we have intervals from now until at least end of today
        end_of_today = datetime.combine(today_date, datetime.max.time())
        end_of_today = dt_util.as_local(end_of_today)
        
        validity.has_minimum_data = (
            validity.has_current_interval 
            and validity.last_valid_interval >= end_of_today
        )
    else:
        _LOGGER.warning("No valid intervals found in price data")
    
    _LOGGER.debug(f"Calculated {validity}")
    
    return validity
