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


class ErrorDetails:
    """Detailed error messages for specific error codes."""

    @staticmethod
    def get_message(error_code: str, **kwargs) -> str:
        """Get formatted error message for an error code.

        Args:
            error_code: Error code from Errors class
            **kwargs: Format parameters for the message

        Returns:
            Formatted error message
        """
        messages = {
            Errors.NO_SOURCES_CONFIGURED: "No API sources configured for area {area}. Check that the area code is valid and supported.",
            Errors.ALL_SOURCES_DISABLED: "All {count} API source(s) temporarily disabled due to recent failures. Will retry during next health check window (00:00-01:00 or 13:00-15:00). Next check: {next_check}.",
            Errors.INVALID_AREA_CODE: "Area code '{area}' is not valid. Please select a supported area from the configuration.",
            Errors.VALIDATION_FAILED: "Data validation failed: {reason}",
            Errors.INCOMPLETE_DATA: "Parser returned incomplete data: {details}",
            Errors.NO_DATA: "No price data available",
            Errors.RATE_LIMITED: "Rate limited, using cached data",
        }

        template = messages.get(error_code, "Error: {error_code}")
        try:
            return template.format(error_code=error_code, **kwargs)
        except KeyError as e:
            # Missing format parameter, return with available params
            return f"{error_code}: {kwargs}"


class Errors:
    """Error code constants."""

    API_ERROR = "api_error"
    NO_DATA = "no_data"
    INVALID_DATA = "invalid_data"
    RATE_LIMITED = "rate_limited"
    NETWORK_ERROR = "network_error"
    TIMEZONE_ERROR = "timezone_error"
    AUTH_ERROR = "auth_error"

    # Source availability errors (v1.4.0+)
    NO_SOURCES_CONFIGURED = "no_sources_configured"  # Permanent: area not supported
    ALL_SOURCES_DISABLED = "all_sources_disabled"  # Temporary: all failed, waiting health check
    INVALID_AREA_CODE = "invalid_area_code"  # Permanent: invalid area in config

    # Validation errors (v1.4.0+)
    VALIDATION_FAILED = "validation_failed"  # Data validation failed
    INCOMPLETE_DATA = "incomplete_data"  # Parser returned incomplete data


# Custom Exception Classes
class PriceFetchError(Exception):
    """Custom exception for errors during price fetching."""

    pass
