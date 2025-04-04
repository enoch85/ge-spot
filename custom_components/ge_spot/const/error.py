"""Error message constants for GE-Spot integration."""

# Error message constants
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
    ErrorMessages.INVALID_API_KEY: "API key validation failed. Please check your key and try again.",
    ErrorMessages.API_KEY_REQUIRED: "API key is required for this source.",
    ErrorMessages.API_CREATION_FAILED: "Failed to create API instance. Please try again.",
    ErrorMessages.NO_SOURCES_FOR_REGION: "No data sources available for this region.",
    ErrorMessages.ERROR_SOURCES_FOR_REGION: "Error retrieving sources for region.",
    ErrorMessages.UNKNOWN: "An unexpected error occurred.",
}
