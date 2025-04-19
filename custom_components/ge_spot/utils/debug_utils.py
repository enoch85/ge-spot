"""Debug utilities for GE-Spot integration."""
import json
import logging
import copy
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

def sanitize_sensitive_data(data: Dict[str, Any], sensitive_keys: List[str] = None) -> Dict[str, Any]:
    """Sanitize sensitive data for logging.

    Args:
        data: Dictionary containing data to sanitize
        sensitive_keys: List of keys to sanitize (default: ['securityToken', 'api_key', 'token'])

    Returns:
        Sanitized copy of the data
    """
    if sensitive_keys is None:
        sensitive_keys = ['securityToken', 'api_key', 'token']

    # Create a deep copy to avoid modifying the original
    sanitized = copy.deepcopy(data)

    for key in sensitive_keys:
        if key in sanitized and sanitized[key]:
            # Mask all but first and last 4 characters
            value = str(sanitized[key])
            if len(value) > 8:
                sanitized[key] = f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"
            else:
                sanitized[key] = "****"

    return sanitized

def log_rate_limiting(area: str, decision: bool, reason: str, source: Optional[str] = None) -> None:
    """Log rate limiting decisions.

    Args:
        area: The area/region code
        decision: True if fetch should be skipped, False otherwise
        reason: Reason for the decision
        source: Optional source name
    """
    action = "SKIPPING" if decision else "ALLOWING"
    source_info = f" for {source}" if source else ""
    _LOGGER.debug(
        f"Rate limiting{source_info} [{area}]: {action} fetch - {reason}"
    )
