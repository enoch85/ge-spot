"""Debug utilities for GE-Spot integration."""
import json
import logging
from typing import Any, Dict, List, Optional

_LOGGER = logging.getLogger(__name__)

def log_conversion(original: float, converted: float, 
                  from_currency: str, to_currency: str,
                  from_unit: str, to_unit: str,
                  vat: float, exchange_rate: Optional[float] = None) -> None:
    """Log conversion details in consistent format."""
    _LOGGER.debug(
        f"Conversion: {original} {from_currency}/{from_unit} → "
        f"{converted} {to_currency}/{to_unit} "
        f"(VAT: {vat:.2%}, rate: {exchange_rate if exchange_rate else 'from service'})"
    )

def log_raw_data(area: str, sensor_type: str, raw_data: List) -> None:
    """Log raw price data."""
    _LOGGER.debug(f"Raw data for {sensor_type}_{area}: {len(raw_data)} entries")
    _LOGGER.debug(f"Complete raw data: {json.dumps(raw_data)}")

def log_statistics(stats: Dict[str, Any], day_offset: int = 0) -> None:
    """Log price statistics."""
    _LOGGER.debug(
        f"Statistics for day+{day_offset}: "
        f"min={stats.get('min')} at {stats.get('min_timestamp')}, "
        f"max={stats.get('max')} at {stats.get('max_timestamp')}, "
        f"avg={stats.get('average')}"
    )
