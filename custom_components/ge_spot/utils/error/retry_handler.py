"""Retry handler for API requests."""
import logging
import asyncio
import random
import functools
from typing import Dict, Any, Optional, List, Callable, Awaitable

from ...const.config import Config
from ...const.defaults import Defaults
from .error_tracker import ErrorTracker

_LOGGER = logging.getLogger(__name__)

# Global retry handler instance for standalone functions
_GLOBAL_RETRY_HANDLER = None

def get_global_retry_handler():
    """Get or create the global retry handler instance."""
    global _GLOBAL_RETRY_HANDLER
    if _GLOBAL_RETRY_HANDLER is None:
        _GLOBAL_RETRY_HANDLER = RetryHandler()
    return _GLOBAL_RETRY_HANDLER

async def retry_with_backoff(func, *args, max_attempts=None, base_delay=None,
                           backoff_factor=None, source="unknown", **kwargs):
    """Standalone function to retry an async function with exponential backoff.

    This is a convenience wrapper around RetryHandler.execute_with_retry.

    Args:
        func: The async function to execute
        *args: Positional arguments to pass to the function
        max_attempts: Maximum number of attempts (including the initial one)
        base_delay: Base delay between retries in seconds
        backoff_factor: Exponential backoff factor
        source: Source identifier for error tracking
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The result of the function

    Raises:
        The last exception that occurred if all retries fail
    """
    retry_config = {}
    if max_attempts is not None:
        retry_config["retry_count"] = max_attempts - 1  # Convert to retry count
    if base_delay is not None:
        retry_config["retry_delay"] = base_delay
    if backoff_factor is not None:
        retry_config["backoff_factor"] = backoff_factor

    handler = get_global_retry_handler()
    return await handler.execute_with_retry(func, *args, source=source,
                                         retry_config=retry_config, **kwargs)

class RetryHandler:
    """Handle retries with exponential backoff."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the retry handler.

        Args:
            config: Optional configuration
        """
        self.config = config or {}
        self.error_tracker = ErrorTracker()

    def _get_retry_config(self, retry_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get retry configuration, combining defaults, instance config, and per-call config."""
        result = {
            "retry_count": Defaults.ERROR_RETRY_COUNT,
            "retry_delay": Defaults.ERROR_RETRY_DELAY,
            "backoff_factor": Defaults.ERROR_BACKOFF_FACTOR,
            "max_delay": 60,  # Maximum delay in seconds
            "jitter": 0.1,  # Random jitter factor
            "retry_on_status": [408, 429, 500, 502, 503, 504],  # HTTP status codes to retry on
            "retry_on_exceptions": [  # Exception types to retry on
                "ClientConnectorError",
                "ServerDisconnectedError",
                "TimeoutError",
                "ContentTypeError",
                "ClientOSError",
                "TooManyRedirects"
            ]
        }

        # Apply instance config
        if self.config:
            result.update({
                "retry_count": self.config.get(Config.ERROR_RETRY_COUNT, result["retry_count"]),
                "retry_delay": self.config.get(Config.ERROR_RETRY_DELAY, result["retry_delay"]),
                "backoff_factor": self.config.get(Config.ERROR_BACKOFF_FACTOR, result["backoff_factor"])
            })

        # Apply per-call config
        if retry_config:
            result.update(retry_config)

        return result

    def _should_retry(self, error: Exception, attempt: int, max_attempts: int,
                     retry_on_exceptions: List[str], retry_on_status: List[int]) -> bool:
        """Determine if a retry should be attempted.

        Args:
            error: The exception that occurred
            attempt: The current attempt number (0-based)
            max_attempts: The maximum number of attempts
            retry_on_exceptions: List of exception type names to retry on
            retry_on_status: List of HTTP status codes to retry on

        Returns:
            True if a retry should be attempted, False otherwise
        """
        # Check if we've reached the maximum number of attempts
        if attempt >= max_attempts:
            return False

        # Check if the error type is in the retry list
        error_type = type(error).__name__
        if error_type in retry_on_exceptions:
            return True

        # Check for HTTP status codes
        if hasattr(error, "status") and error.status in retry_on_status:
            return True

        # Special case for aiohttp ClientResponseError
        if error_type == "ClientResponseError" and hasattr(error, "status") and error.status in retry_on_status:
            return True

        return False

    def _calculate_delay(self, attempt: int, base_delay: float,
                        backoff_factor: float, max_delay: float, jitter: float) -> float:
        """Calculate the delay before the next retry.

        Args:
            attempt: The current attempt number (0-based)
            base_delay: The base delay in seconds
            backoff_factor: The exponential backoff factor
            max_delay: The maximum delay in seconds
            jitter: Random jitter factor

        Returns:
            The delay in seconds
        """
        # Calculate exponential backoff
        delay = base_delay * (backoff_factor ** attempt)

        # Apply maximum delay
        delay = min(delay, max_delay)

        # Apply jitter
        if jitter > 0:
            jitter_amount = delay * jitter
            delay = delay + random.uniform(-jitter_amount, jitter_amount)

        return max(0, delay)  # Ensure non-negative

    async def execute_with_retry(self, func: Callable[..., Awaitable[Any]],
                               *args,
                               source: str = "unknown",
                               retry_config: Optional[Dict[str, Any]] = None,
                               **kwargs) -> Any:
        """Execute a function with retry logic.

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
        config = self._get_retry_config(retry_config)
        max_attempts = config["retry_count"] + 1  # +1 for the initial attempt

        last_error = None

        for attempt in range(max_attempts):
            try:
                # Execute the function
                return await func(*args, **kwargs)

            except Exception as e:
                last_error = e

                # Track the error
                context = {
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "args": str(args),
                    "kwargs": str(kwargs)
                }
                self.error_tracker.add_error(e, source, context)

                # Determine if we should retry
                if not self._should_retry(e, attempt, max_attempts,
                                        config["retry_on_exceptions"],
                                        config["retry_on_status"]):
                    _LOGGER.warning(f"Not retrying {source} after error: {e}")
                    break

                # Calculate delay
                delay = self._calculate_delay(attempt, config["retry_delay"],
                                           config["backoff_factor"],
                                           config["max_delay"],
                                           config["jitter"])

                _LOGGER.info(f"Retrying {source} in {delay:.2f}s after error: {e} (attempt {attempt+1}/{max_attempts})")

                # Wait before retrying
                await asyncio.sleep(delay)

        # If we get here, all retries failed
        if last_error:
            _LOGGER.error(f"All {max_attempts} attempts failed for {source}: {last_error}")
            raise last_error

        # This should never happen, but just in case
        raise RuntimeError(f"Unexpected error in retry logic for {source}")
