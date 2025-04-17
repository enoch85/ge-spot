"""Utility functions for GE-Spot integration."""

# API client and validation
from .api_client import ApiClient, ApiFallbackManager
from .api_validator import ApiValidator
# Import DataValidator from the local file
from .data_validator import DataValidator

# Debug utilities
from .debug_utils import log_conversion, log_raw_data, log_statistics

# Error handling
from .error.__init__ import retry_with_backoff as retry_async
from .error.__init__ import with_retry
from .error.__init__ import ErrorManager
from .error.__init__ import with_error_handling as handle_api_errors
from .error.error_record import ErrorRecord
from .error.error_tracker import ErrorTracker

# Define error classes for backward compatibility
class APIError(Exception):
    """API error."""
    pass

class RateLimitError(APIError):
    """Rate limit error."""
    pass

class AuthenticationError(APIError):
    """Authentication error."""
    pass

class DataParsingError(APIError):
    """Data parsing error."""
    pass

# Exchange service
from .exchange_service import ExchangeRateService, get_exchange_service

# Form helper
from .form_helper import FormHelper

# Validation utilities
from .validation.schema_validator import SchemaValidator
from .validation.schema import Schema
from .validation.validation_error import ValidationError

__all__ = [
    # API utilities
    "ApiClient",
    "ApiFallbackManager",
    "ApiValidator",
    "DataValidator",

    # Debug utilities
    "log_conversion",
    "log_raw_data",
    "log_statistics",

    # Error handling
    "retry_async",
    "with_retry",
    "APIError",
    "RateLimitError",
    "AuthenticationError",
    "DataParsingError",
    "handle_api_errors",

    # Exchange service
    "ExchangeRateService",
    "get_exchange_service",

    # Form helper
    "FormHelper",

    # Validation utilities
    "SchemaValidator",
    "Schema",
    "ValidationError",
]
