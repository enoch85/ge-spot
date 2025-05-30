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
        hourly_prices: Hourly prices dictionary (RAW, from parser, likely ISO keys)
        reference_time: Optional reference time
        api_timezone: Optional API timezone
        vat_rate: Optional VAT rate
        vat_included: Whether VAT is included
        raw_data: Optional raw API response
        validate_complete: Whether to validate data completeness (REMOVED - validation should happen AFTER normalization)
        has_tomorrow_prices: Whether complete data for tomorrow is available (determined by parser/fetcher)
        tomorrow_prices_expected: Whether tomorrow's prices are expected to be available (determined by parser/fetcher)

    Returns:
        StandardizedPriceData object containing mostly raw/parsed data
    """
    now = datetime.now()
    today = now.date()

    # REMOVED: Validation logic - should happen in DataProcessor after normalization
    # REMOVED: Statistics calculation
    # REMOVED: Current/Next hour price calculation

    # Create raw_prices list from the input hourly_prices (assuming ISO keys from parser)
    raw_prices_list = []
    for hour_key, price in hourly_prices.items():
        try:
            # Attempt to parse ISO string key
            dt_obj = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
            # Create simple HH:00 key for compatibility if needed, but prefer ISO
            simple_hour_key = dt_obj.strftime("%H:00")
        except (ValueError, TypeError):
            # Fallback if key is not ISO (e.g., HH:00) - less ideal
            iso_dt = f"{today.isoformat()}T{hour_key}:00" # Placeholder
            simple_hour_key = hour_key

        raw_prices_list.append(HourlyPrice(
            datetime=hour_key, # Store original key as datetime string
            price=price,
            hour_key=simple_hour_key, # Store HH:00 for potential compatibility
            currency=currency,
            timezone=api_timezone or "UTC",
            source=source,
            vat_included=vat_included
        ))

    # Return a simplified object with raw data
    return StandardizedPriceData(
        source=source,
        area=area,
        currency=currency,
        fetched_at=now.isoformat(),
        reference_time=reference_time.isoformat() if reference_time else None,
        hourly_prices=hourly_prices, # Store the RAW hourly prices dict from parser
        raw_prices=raw_prices_list,
        api_timezone=api_timezone,
        vat_rate=vat_rate,
        vat_included=vat_included,
        raw_data=raw_data,
        has_tomorrow_prices=has_tomorrow_prices,
        tomorrow_prices_expected=tomorrow_prices_expected,
        # Fields below will be populated by DataProcessor
        current_price=None,
        next_hour_price=None,
        current_hour_key=None,
        next_hour_key=None,
        statistics=None,
        peak_hours=None,
        off_peak_hours=None
    )