"""Utility functions for GE-Spot integration."""
import logging
from typing import Dict, Any, Optional, Tuple, List, Union, Callable
from datetime import datetime, timedelta

# Import common exceptions for use throughout the codebase
from ..api.base.error_handler import ErrorHandler, retry_with_backoff

_LOGGER = logging.getLogger(__name__)

# API client and validation
from .api_client import ApiFallbackManager
from .api_validator import ApiValidator
# Import DataValidator from the local file
from .data_validator import DataValidator

# Debug utilities
from .debug_utils import log_conversion, log_raw_data, log_statistics

# Define common exceptions for the integration
class APIError(Exception):
    """Base class for API errors."""
    pass

class RateLimitError(APIError):
    """Error raised when API rate limiting is detected."""
    pass

class AuthenticationError(APIError):
    """Error raised when API authentication fails."""
    pass

class DataParsingError(APIError):
    """Error raised when parsing API data fails."""
    pass

# Exchange service
from .exchange_service import ExchangeRateService, get_exchange_service

# Form helper
# from .form_helper import FormHelper # Removed unused import

# Validation utilities
from .validation.schema_validator import SchemaValidator
from .validation.schema import Schema
from .validation.validation_error import ValidationError

__all__ = [
    # API utilities
    # "ApiClient", # Removed unused
    "ApiFallbackManager",
    "ApiValidator",
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

    # Form helper
    # "FormHelper", # Removed unused

    # Validation utilities
    "SchemaValidator",
    "Schema",
    "ValidationError"
]
