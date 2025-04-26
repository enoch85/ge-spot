"""Error message constants for GE-Spot integration."""

class ErrorMessages:
    """Error message constants."""
    INVALID_API_KEY = "invalid_api_key"
    API_KEY_REQUIRED = "api_key_required"
    API_CREATION_FAILED = "api_creation_failed"
    NO_SOURCES_FOR_REGION = "no_sources_for_region"
    ERROR_SOURCES_FOR_REGION = "error_sources_for_region"
    UNKNOWN = "unknown"

    # Translation strings
    TRANSLATIONS = {
        INVALID_API_KEY: "API key validation failed. Please check your key and try again.",
        API_KEY_REQUIRED: "API key is required for this source.",
        API_CREATION_FAILED: "Failed to create API instance. Please try again.",
        NO_SOURCES_FOR_REGION: "No data sources available for this region.",
        ERROR_SOURCES_FOR_REGION: "Error retrieving sources for region.",
        UNKNOWN: "An unexpected error occurred.",
    }

class Errors:
    """Error code constants."""
    API_ERROR = "api_error"
    NO_DATA = "no_data"
    INVALID_DATA = "invalid_data"
    RATE_LIMITED = "rate_limited"
    NETWORK_ERROR = "network_error"
    TIMEZONE_ERROR = "timezone_error"
    AUTH_ERROR = "auth_error"

# Custom Exception Classes
class PriceFetchError(Exception):
    """Custom exception for errors during price fetching."""
    pass
