"""Error management for API requests."""
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Callable, Awaitable, Union
from functools import wraps

from homeassistant.core import HomeAssistant

from ...const.network import NetworkErrorType
from .retry_handler import RetryHandler

_LOGGER = logging.getLogger(__name__)

class ErrorManager:
    """Manage error handling and recovery for the integration."""

    def __init__(self, hass: Optional[HomeAssistant] = None, config: Optional[Dict[str, Any]] = None):
        """Initialize the error manager.

        Args:
            hass: Optional Home Assistant instance
            config: Optional configuration
        """
        self.hass = hass
        self.config = config or {}
        self.retry_handler = RetryHandler(config)
        self.error_tracker = self.retry_handler.error_tracker

        # Track API health
        self._api_health: Dict[str, Dict[str, Any]] = {}

    def classify_error(self, error: Exception) -> str:
        """Classify an error into a general category.

        Args:
            error: The exception to classify

        Returns:
            The error category
        """
        error_type = type(error).__name__
        error_str = str(error).lower()

        # Network connectivity errors
        if any(net_err in error_type for net_err in [
            "ConnectionError", "ConnectTimeout", "ClientConnectorError",
            "ServerDisconnectedError", "TimeoutError"
        ]):
            return NetworkErrorType.CONNECTIVITY

        # Rate limiting errors
        if error_type == "ClientResponseError" and hasattr(error, "status") and error.status == 429:
            return NetworkErrorType.RATE_LIMIT

        if "rate limit" in error_str or "too many requests" in error_str:
            return NetworkErrorType.RATE_LIMIT

        # Authentication errors
        if error_type == "ClientResponseError" and hasattr(error, "status") and error.status in [401, 403]:
            return NetworkErrorType.AUTHENTICATION

        if "unauthorized" in error_str or "forbidden" in error_str or "authentication" in error_str:
            return NetworkErrorType.AUTHENTICATION

        # Server errors
        if error_type == "ClientResponseError" and hasattr(error, "status") and 500 <= error.status < 600:
            return NetworkErrorType.SERVER

        if "server error" in error_str or "internal error" in error_str:
            return NetworkErrorType.SERVER

        # Data format errors
        if any(fmt_err in error_type for fmt_err in [
            "JSONDecodeError", "ContentTypeError", "XMLSyntaxError", "ParseError"
        ]):
            return NetworkErrorType.DATA_FORMAT

        # Default to unknown
        return NetworkErrorType.UNKNOWN

    def update_api_health(self, source: str, success: bool, error: Optional[Exception] = None) -> None:
        """Update the health status of an API.

        Args:
            source: The API source identifier
            success: Whether the API call was successful
            error: Optional exception if the call failed
        """
        now = datetime.now()

        # Initialize health record if needed
        if source not in self._api_health:
            self._api_health[source] = {
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "last_call": now,
                "last_success": None,
                "last_failure": None,
                "last_error": None,
                "error_categories": {},
                "success_rate": 1.0,  # Start optimistic
                "consecutive_failures": 0,
                "consecutive_successes": 0
            }

        health = self._api_health[source]

        # Update counters
        health["total_calls"] += 1
        health["last_call"] = now

        if success:
            health["successful_calls"] += 1
            health["last_success"] = now
            health["consecutive_successes"] += 1
            health["consecutive_failures"] = 0
        else:
            health["failed_calls"] += 1
            health["last_failure"] = now
            health["consecutive_failures"] += 1
            health["consecutive_successes"] = 0

            if error:
                health["last_error"] = {
                    "type": type(error).__name__,
                    "message": str(error),
                    "timestamp": now.isoformat()
                }

                # Classify error
                category = self.classify_error(error)
                health["error_categories"][category] = health["error_categories"].get(category, 0) + 1

        # Calculate success rate
        health["success_rate"] = health["successful_calls"] / health["total_calls"]

    def is_api_healthy(self, source: str, threshold: float = 0.7) -> bool:
        """Check if an API is considered healthy.

        Args:
            source: The API source identifier
            threshold: Success rate threshold (default: 0.7)

        Returns:
            True if the API is healthy, False otherwise
        """
        if source not in self._api_health:
            # No data yet, assume healthy
            return True

        health = self._api_health[source]

        # Check success rate
        if health["success_rate"] < threshold:
            return False

        # Check consecutive failures
        if health["consecutive_failures"] >= 3:
            return False

        return True

    def get_api_health(self, source: Optional[str] = None) -> Dict[str, Any]:
        """Get health information for APIs.

        Args:
            source: Optional source to get health for

        Returns:
            Health information
        """
        if source:
            return self._api_health.get(source, {})

        return {
            "apis": self._api_health,
            "overall_health": {
                "total_apis": len(self._api_health),
                "healthy_apis": sum(1 for s in self._api_health if self.is_api_healthy(s)),
                "unhealthy_apis": sum(1 for s in self._api_health if not self.is_api_healthy(s)),
                "total_calls": sum(h["total_calls"] for h in self._api_health.values()),
                "success_rate": sum(h["successful_calls"] for h in self._api_health.values()) /
                               max(1, sum(h["total_calls"] for h in self._api_health.values()))
            }
        }

    async def execute_with_error_handling(self, func: Callable[..., Awaitable[Any]],
                                        *args,
                                        source: str = "unknown",
                                        retry_config: Optional[Dict[str, Any]] = None,
                                        **kwargs) -> Any:
        """Execute a function with comprehensive error handling.

        Args:
            func: The async function to execute
            *args: Positional arguments to pass to the function
            source: The source identifier for error tracking
            retry_config: Optional retry configuration
            **kwargs: Keyword arguments to pass to the function

        Returns:
            The result of the function

        Raises:
            The last exception that occurred if all retries fail
        """
        try:
            # Execute with retry
            result = await self.retry_handler.execute_with_retry(
                func, *args, source=source, retry_config=retry_config, **kwargs
            )

            # Update API health
            self.update_api_health(source, True)

            return result

        except Exception as e:
            # Update API health
            self.update_api_health(source, False, e)

            # Re-raise the exception
            raise


# Create a decorator for easy use
def with_error_handling(source: str = "unknown", retry_config: Optional[Dict[str, Any]] = None):
    """Decorator to add error handling to an async function.

    Args:
        source: The source identifier for error tracking
        retry_config: Optional retry configuration

    Returns:
        Decorated function
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Get or create error manager
            if hasattr(self, "error_manager"):
                error_manager = self.error_manager
            else:
                config = getattr(self, "config", {})
                hass = getattr(self, "hass", None)
                error_manager = ErrorManager(hass, config)

            # Execute with error handling
            return await error_manager.execute_with_error_handling(
                func, self, *args, source=source, retry_config=retry_config, **kwargs
            )
        return wrapper
    return decorator
