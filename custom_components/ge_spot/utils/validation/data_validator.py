"""Data validation for API responses."""
import logging
from typing import Dict, Any

from ...const.sources import Source
from .schema import Schema
from .schema_validator import SchemaValidator
from .validation_error import ValidationError

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
