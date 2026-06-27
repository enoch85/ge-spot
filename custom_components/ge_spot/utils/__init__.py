"""Utility functions for GE-Spot integration."""

import logging

# Import common exceptions for use throughout the codebase
from ..api.base.error_handler import ErrorHandler, retry_with_backoff

_LOGGER = logging.getLogger(__name__)

# Import DataValidator from the local file
from .data_validator import DataValidator

# Debug utilities
from .debug_utils import log_conversion, log_raw_data, log_statistics


# Define common exceptions for the integration
class APIError(Exception):
    """Base class for API errors."""


class RateLimitError(APIError):
    """Error raised when API rate limiting is detected."""


class AuthenticationError(APIError):
    """Error raised when API authentication fails."""


class DataParsingError(APIError):
    """Error raised when parsing API data fails."""


# Exchange service
from .exchange_service import ExchangeRateService, get_exchange_service

# Validation utilities
from .validation.schema_validator import SchemaValidator
from .validation.schema import Schema
from .validation.validation_error import ValidationError

__all__ = [
    # API utilities
    "DataValidator",
    # Debug utilities
    "log_conversion",
    "log_raw_data",
    "log_statistics",
    # Error handling
    "retry_with_backoff",
    "APIError",
    "RateLimitError",
    "AuthenticationError",
    "DataParsingError",
    "ErrorHandler",
    # Exchange service
    "ExchangeRateService",
    "get_exchange_service",
    # Validation utilities
    "SchemaValidator",
    "Schema",
    "ValidationError",
]
