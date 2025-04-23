"""Standardized data structure for price data."""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime

@dataclass
class HourlyPrice:
    """Hourly price data."""
    
    datetime: str  # ISO format datetime string
    price: float
    hour_key: str  # Format: HH:00
    currency: str
    timezone: str
    source: str
    vat_included: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

@dataclass
class PriceStatistics:
    """Price statistics.
    
    Note: Statistics should only be calculated when complete data is available.
    The complete_data flag indicates whether the statistics are based on a 
    complete dataset or not. If complete_data is False, the statistics should
    not be used for critical calculations.
    """
    
    min: Optional[float] = None
    max: Optional[float] = None
    average: Optional[float] = None
    median: Optional[float] = None
    complete_data: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

@dataclass
class PeakHourStatistics(PriceStatistics):
    """Peak hour statistics."""
    
    hours: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

@dataclass
class StandardizedPriceData:
    """Standardized price data format for all API implementations."""
    
    source: str
    area: str
    currency: str
    fetched_at: str  # ISO format datetime string
    reference_time: Optional[str] = None  # ISO format datetime string
    hourly_prices: Dict[str, float] = field(default_factory=dict)  # Key: HH:00, Value: price
    raw_prices: List[HourlyPrice] = field(default_factory=list)
    current_price: Optional[float] = None
    next_hour_price: Optional[float] = None
    api_timezone: Optional[str] = None
    current_hour_key: Optional[str] = None
    next_hour_key: Optional[str] = None
    statistics: Optional[PriceStatistics] = None
    peak_hours: Optional[PeakHourStatistics] = None
    off_peak_hours: Optional[PeakHourStatistics] = None
    vat_rate: Optional[float] = None
    vat_included: bool = False
    raw_data: Any = None  # Original API response
    has_tomorrow_prices: bool = False  # Whether we have complete data for tomorrow
    tomorrow_prices_expected: bool = False  # Whether tomorrow's prices are expected to be available
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format.
        
        Returns:
            Dictionary representation of the data
        """
        result = {
            "source": self.source,
            "area": self.area,
            "currency": self.currency,
            "fetched_at": self.fetched_at,
            "hourly_prices": self.hourly_prices,
            "current_price": self.current_price,
            "next_hour_price": self.next_hour_price,
            "vat_included": self.vat_included,
            "has_tomorrow_prices": self.has_tomorrow_prices,
            "tomorrow_prices_expected": self.tomorrow_prices_expected
        }
        
        # Add optional fields if set
        if self.reference_time:
            result["reference_time"] = self.reference_time
            
        if self.api_timezone:
            result["api_timezone"] = self.api_timezone
            
        if self.current_hour_key:
            result["current_hour_key"] = self.current_hour_key
            
        if self.next_hour_key:
            result["next_hour_key"] = self.next_hour_key
            
        if self.vat_rate is not None:
            result["vat_rate"] = self.vat_rate
            
        # Add statistics if available
        if self.statistics:
            result["statistics"] = self.statistics.to_dict()
            
        if self.peak_hours:
            result["peak_hours"] = self.peak_hours.to_dict()
            
        if self.off_peak_hours:
            result["off_peak_hours"] = self.off_peak_hours.to_dict()
            
        # Add raw prices
        if self.raw_prices:
            result["raw_prices"] = [price.to_dict() for price in self.raw_prices]
        
        return result
    
    @classmethod
    def create_empty(cls, source: str, area: str, currency: str) -> 'StandardizedPriceData':
        """Create an empty price data object.
        
        Args:
            source: Source identifier
            area: Area code
            currency: Currency code
            
        Returns:
            Empty StandardizedPriceData object
        """
        return cls(
            source=source,
            area=area,
            currency=currency,
            fetched_at=datetime.now().isoformat()
        )

def create_standardized_price_data(
    source: str,
    area: str,
    currency: str,
    hourly_prices: Dict[str, float],
    reference_time: Optional[datetime] = None,
    api_timezone: Optional[str] = None,
    vat_rate: Optional[float] = None,
    vat_included: bool = False,
    raw_data: Any = None,
    validate_complete: bool = True,
    has_tomorrow_prices: bool = False,
    tomorrow_prices_expected: bool = False
) -> StandardizedPriceData:
    """Create standardized price data from API response.
    
    Args:
        source: Source identifier
        area: Area code
        currency: Currency code
        hourly_prices: Hourly prices dictionary
        reference_time: Optional reference time
        api_timezone: Optional API timezone
        vat_rate: Optional VAT rate
        vat_included: Whether VAT is included
        raw_data: Optional raw API response
        validate_complete: Whether to validate data completeness
        has_tomorrow_prices: Whether complete data for tomorrow is available
        tomorrow_prices_expected: Whether tomorrow's prices are expected to be available
        
    Returns:
        StandardizedPriceData object
    """
    now = datetime.now()
    today = now.date()
    
    # Validate completeness if requested
    complete_data = True
    if validate_complete:
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
                    dt = datetime.combine(today, datetime.min.time().replace(hour=hour))
                
                # Check if this is the date we want and add the hour
                if dt and dt.date() == today:
                    found_hours.add(dt.hour)
            except (ValueError, TypeError):
                continue
        
        # Check if we found all required hours
        complete_data = required_hours.issubset(found_hours)
    
    # Create raw_prices list
    raw_prices = []
    for hour_key, price in hourly_prices.items():
        # Try to create datetime from hour_key
        try:
            if ":" in hour_key:
                hour = int(hour_key.split(":")[0])
                dt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            else:
                dt = datetime.fromisoformat(hour_key)
            
            iso_dt = dt.isoformat()
        except:
            iso_dt = f"{now.date().isoformat()}T{hour_key}:00"
            
        raw_prices.append(HourlyPrice(
            datetime=iso_dt,
            price=price,
            hour_key=hour_key,
            currency=currency,
            timezone=api_timezone or "UTC",
            source=source,
            vat_included=vat_included
        ))
    
    # Get current and next hour keys
    current_hour_key = f"{now.hour:02d}:00"
    next_hour = (now.hour + 1) % 24
    next_hour_key = f"{next_hour:02d}:00"
    
    # Get current and next hour prices
    current_price = hourly_prices.get(current_hour_key)
    next_hour_price = hourly_prices.get(next_hour_key)
    
    # Create statistics if we have complete data
    statistics = None
    if complete_data:
        # Extract prices for today
        today_prices = []
        for hour_key, price in hourly_prices.items():
            try:
                # Check if this is for today
                if ':' in hour_key:
                    # Format: 12:00
                    hour = int(hour_key.split(':')[0])
                    # We use this to get the hour for today
                    today_prices.append(price)
                elif 'T' in hour_key:
                    # Format: 2023-01-01T12:00:00[+00:00]
                    dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                    if dt.date() == today:
                        today_prices.append(price)
            except (ValueError, TypeError):
                continue
        
        if today_prices:
            # Sort prices for accurate median calculation
            today_prices.sort()
            mid = len(today_prices) // 2
            median = today_prices[mid] if len(today_prices) % 2 == 1 else (today_prices[mid-1] + today_prices[mid]) / 2
            
            statistics = PriceStatistics(
                min=min(today_prices),
                max=max(today_prices),
                average=sum(today_prices) / len(today_prices),
                median=median,
                complete_data=complete_data
            )
    
    # Create standardized data
    return StandardizedPriceData(
        source=source,
        area=area,
        currency=currency,
        fetched_at=now.isoformat(),
        reference_time=reference_time.isoformat() if reference_time else None,
        hourly_prices=hourly_prices,
        raw_prices=raw_prices,
        api_timezone=api_timezone,
        vat_rate=vat_rate,
        vat_included=vat_included,
        raw_data=raw_data,
        current_price=current_price,
        next_hour_price=next_hour_price,
        current_hour_key=current_hour_key,
        next_hour_key=next_hour_key,
        statistics=statistics,
        has_tomorrow_prices=has_tomorrow_prices,
        tomorrow_prices_expected=tomorrow_prices_expected
    ) 