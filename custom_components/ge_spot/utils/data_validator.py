"""Data validation utilities for API responses."""
import logging
from typing import Dict, Any, Optional, List
import statistics
from datetime import datetime

from ..const.sources import Source
from .validation.schema import Schema
from .validation.schema_validator import SchemaValidator
from .validation.validation_error import ValidationError

_LOGGER = logging.getLogger(__name__)

# Define schemas for different API sources
_SCHEMAS = {
    Source.NORDPOOL: Schema({
        "type": "object",
        "properties": {
            "data": {"type": "object", "optional": True},
            "currency": {"type": "string", "optional": True},
            "interval_prices": {"type": "object", "optional": True},
            "current_price": {"type": "number", "optional": True},
            "next_interval_price": {"type": "number", "optional": True},
            "raw_data": {"type": "string", "optional": True}
        }
    }),
    Source.ENTSOE: Schema({
        "type": "object",
        "properties": {
            "currency": {"type": "string", "optional": True},
            "interval_prices": {"type": "object", "optional": True},
            "current_price": {"type": "number", "optional": True},
            "next_interval_price": {"type": "number", "optional": True},
            "raw_data": {"type": "string", "optional": True}
        }
    }),
    Source.ENERGI_DATA_SERVICE: Schema({
        "type": "object",
        "properties": {
            "records": {"type": "array", "optional": True},
            "currency": {"type": "string", "optional": True},
            "interval_prices": {"type": "object", "optional": True},
            "current_price": {"type": "number", "optional": True},
            "next_interval_price": {"type": "number", "optional": True},
            "raw_data": {"type": "string", "optional": True}
        }
    }),
    Source.AEMO: Schema({
        "type": "object",
        "properties": {
            "currency": {"type": "string", "optional": True},
            "interval_prices": {"type": "object", "optional": True},
            "current_price": {"type": "number", "optional": True},
            "next_interval_price": {"type": "number", "optional": True},
            "raw_data": {"type": "string", "optional": True}
        }
    }),
    Source.EPEX: Schema({
        "type": "object",
        "properties": {
            "currency": {"type": "string", "optional": True},
            "interval_prices": {"type": "object", "optional": True},
            "current_price": {"type": "number", "optional": True},
            "next_interval_price": {"type": "number", "optional": True},
            "raw_data": {"type": "string", "optional": True}
        }
    }),
    Source.OMIE: Schema({
        "type": "object",
        "properties": {
            "currency": {"type": "string", "optional": True},
            "interval_prices": {"type": "object", "optional": True},
            "current_price": {"type": "number", "optional": True},
            "next_interval_price": {"type": "number", "optional": True},
            "raw_data": {"type": "string", "optional": True}
        }
    }),
    Source.STROMLIGNING: Schema({
        "type": "object",
        "properties": {
            "prices": {"type": "array", "optional": True},
            "currency": {"type": "string", "optional": True},
            "interval_prices": {"type": "object", "optional": True},
            "current_price": {"type": "number", "optional": True},
            "next_interval_price": {"type": "number", "optional": True},
            "raw_data": {"type": "string", "optional": True}
        }
    })
}

# Default schema for unknown sources
_DEFAULT_SCHEMA = Schema({
    "type": "object",
    "properties": {
        "currency": {"type": "string", "optional": True},
        "interval_prices": {"type": "object", "optional": True},
        "current_price": {"type": "number", "optional": True},
        "next_interval_price": {"type": "number", "optional": True},
        "raw_data": {"type": "string", "optional": True}
    }
})

def validate_data(data: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Validate API response data.

    Args:
        data: Data to validate
        source: Source identifier

    Returns:
        Validated data
    """
    if not isinstance(data, dict):
        _LOGGER.warning(f"Invalid data type for {source}: {type(data)}")
        return {}

    # Get schema for source
    schema = _SCHEMAS.get(source, _DEFAULT_SCHEMA)

    # Create validator
    validator = SchemaValidator(schema)

    try:
        # Validate data
        validator.validate(data)
        return data
    except ValidationError as e:
        _LOGGER.warning(f"Validation error for {source}: {e}")

        # Return original data even if validation fails
        # This allows parsers to handle partial or invalid data
        return data

class DataValidator:
    """Utility class for validating API data."""

    def __init__(self):
        """Initialize the data validator."""
        self._validation_history = {}
        self._anomaly_threshold = 3.0  # Z-score threshold for anomalies

    def validate_price_data(self, data: Dict[str, Any], source_name: str = "unknown") -> Dict[str, Any]:
        """Validate price data from an API.

        Args:
            data: API response data
            source_name: Name of the API source

        Returns:
            Dict with validation results
        """
        result = {
            "valid": False,
            "source": source_name,
            "timestamp": datetime.now().isoformat(),
            "errors": [],
            "warnings": [],
            "anomalies": []
        }

        # Basic validation
        if not data:
            result["errors"].append("Empty data")
            return result

        if not isinstance(data, dict):
            result["errors"].append(f"Invalid data type: {type(data)}")
            return result

        # Validate using schema
        validated_data = validate_data(data, source_name)

        # Check for interval prices
        interval_prices = data.get("interval_prices", {})
        if not interval_prices:
            result["errors"].append("No interval prices")
            return result

        # Check for anomalies in interval prices
        try:
            prices = list(interval_prices.values())
            if len(prices) >= 3:  # Need at least 3 values for meaningful statistics
                mean = statistics.mean(prices)
                stdev = statistics.stdev(prices)

                if stdev > 0:  # Avoid division by zero
                    for interval, price in interval_prices.items():
                        z_score = abs((price - mean) / stdev)
                        if z_score > self._anomaly_threshold:
                            result["anomalies"].append({
                                "interval": interval,
                                "price": price,
                                "z_score": z_score
                            })
        except Exception as e:
            result["warnings"].append(f"Error checking for anomalies: {e}")

        # Mark as valid if no errors
        if not result["errors"]:
            result["valid"] = True

        return result

    def track_validation_result(self, source_name: str, result: Dict[str, Any]) -> None:
        """Track validation result for historical analysis.

        Args:
            source_name: Name of the API source
            result: Validation result
        """
        if source_name not in self._validation_history:
            self._validation_history[source_name] = {
                "total": 0,
                "valid": 0,
                "invalid": 0,
                "anomalies": 0,
                "last_result": None,
                "last_timestamp": None
            }

        history = self._validation_history[source_name]
        history["total"] += 1
        if result["valid"]:
            history["valid"] += 1
        else:
            history["invalid"] += 1

        if result.get("anomalies"):
            history["anomalies"] += 1

        history["last_result"] = result["valid"]
        history["last_timestamp"] = result["timestamp"]

    def get_source_reliability(self, source_name: str) -> Dict[str, Any]:
        """Get reliability metrics for a source.

        Args:
            source_name: Source identifier

        Returns:
            Dict with reliability metrics
        """
        if source_name not in self._validation_history:
            return {
                "source": source_name,
                "reliability": 0.0,
                "total_requests": 0,
                "valid_responses": 0,
                "anomaly_rate": 0.0
            }

        history = self._validation_history[source_name]
        reliability = history["valid"] / history["total"] if history["total"] > 0 else 0.0
        anomaly_rate = history["anomalies"] / history["valid"] if history["valid"] > 0 else 0.0

        return {
            "source": source_name,
            "reliability": reliability,
            "total_requests": history["total"],
            "valid_responses": history["valid"],
            "anomaly_rate": anomaly_rate,
            "last_result": history["last_result"],
            "last_timestamp": history["last_timestamp"]
        }
