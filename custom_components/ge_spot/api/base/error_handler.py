"""Centralized error handling for API calls."""
import logging
import asyncio
import time
import functools
from datetime import datetime
from typing import Callable, Any, Dict, Optional, Union, List, Tuple

from ...const.network import NetworkErrorType, RetryStrategy

_LOGGER = logging.getLogger(__name__)

def with_error_handling(func=None, *, source_type: str = "unknown"):
    """Decorator to handle errors in API calls.

    Can be used as a decorator with or without arguments:

    @with_error_handling
    async def my_func():
        ...

    @with_error_handling(source_type="my_source")
    async def my_func():
        ...

    Args:
        func: The function to decorate
        source_type: The source type identifier

    Returns:
        Decorated function
    """
    # Used as a decorator with arguments @with_error_handling(...)
    if func is None:
        return functools.partial(
            with_error_handling,
            source_type=source_type
        )

    # For direct function calls or @with_error_handling without arguments
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        handler = ErrorHandler(source_type)
        try:
            return await func(*args, **kwargs)
        except Exception as error:
            error_type = handler.classify_error(error)
            _LOGGER.error(
                f"Error in {source_type} API call: {error}. "
                f"Classified as {error_type}."
            )
            raise error

    return wrapper

def retry_with_backoff(
    func=None,
    *,
    max_retries: int = 3,
    strategy: str = RetryStrategy.EXPONENTIAL_BACKOFF,
    source_type: str = "unknown",
    max_attempts=None,  # For backward compatibility
    base_delay=None     # For backward compatibility
):
    """Run a function with retry logic.

    Can be used as a decorator with or without arguments:

    @retry_with_backoff
    async def my_func():
        ...

    @retry_with_backoff(max_retries=5)
    async def my_func():
        ...

    Or as a function call:
    await retry_with_backoff(my_func, max_retries=5)

    Args:
        func: The function to decorate or call
        max_retries: Maximum number of retries
        strategy: Retry strategy to use
        source_type: The source type identifier
        max_attempts: Alias for max_retries for compatibility
        base_delay: Base delay for retries

    Returns:
        Decorated function or function result
    """
    # Handle compatibility parameters
    if max_attempts is not None:
        max_retries = max_attempts

    # Used as a decorator with arguments @retry_with_backoff(...)
    if func is None:
        return functools.partial(
            retry_with_backoff,
            max_retries=max_retries,
            strategy=strategy,
            source_type=source_type
        )

    # For direct function calls or @retry_with_backoff without arguments
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        handler = ErrorHandler(source_type)
        return await handler.run_with_retry(
            func, *args, max_retries=max_retries, strategy=strategy, **kwargs
        )

    return wrapper

class ErrorHandler:
    """Centralized error handling for API calls."""

    def __init__(self, source_type: str):
        """Initialize the error handler.

        Args:
            source_type: The source type identifier
        """
        self.source_type = source_type
        self.error_counts: Dict[str, int] = {}
        self.last_error_time: Dict[str, datetime] = {}
        self.backoff_index: Dict[str, int] = {}

    def classify_error(self, error: Exception) -> str:
        """Classify an error into a standardized type.

        Args:
            error: The exception to classify

        Returns:
            Standardized error type
        """
        error_str = str(error).lower()
        error_type = error.__class__.__name__

        # Network connectivity issues
        if any(x in error_str for x in ["connection", "connect", "unreachable", "network"]):
            return NetworkErrorType.CONNECTIVITY

        # Rate limiting or throttling
        if any(x in error_str for x in ["rate limit", "throttle", "429", "too many requests"]):
            return NetworkErrorType.RATE_LIMIT

        # Authentication or authorization issues
        if any(x in error_str for x in ["auth", "token", "key", "credential", "permission", "access", "401", "403"]):
            return NetworkErrorType.AUTHENTICATION

        # Server-side errors
        if any(x in error_str for x in ["server", "500", "502", "503", "504", "internal"]):
            return NetworkErrorType.SERVER

        # Data parsing or format issues
        if any(x in error_str for x in ["parse", "format", "json", "xml", "data", "value", "type"]):
            return NetworkErrorType.DATA_FORMAT

        # Timeout issues
        if any(x in error_str for x in ["timeout", "timed out"]):
            return NetworkErrorType.TIMEOUT

        # DNS resolution issues
        if any(x in error_str for x in ["dns", "resolve", "host"]):
            return NetworkErrorType.DNS

        # SSL/TLS issues
        if any(x in error_str for x in ["ssl", "tls", "cert", "certificate"]):
            return NetworkErrorType.SSL

        # If we can't classify it, use the error type as a fallback
        return f"{NetworkErrorType.UNKNOWN}:{error_type}"

    def should_retry(self, error_type: str, retry_count: int, max_retries: int) -> bool:
        """Determine if a retry should be attempted for a given error.

        Args:
            error_type: The error type
            retry_count: Current retry count
            max_retries: Maximum number of retries

        Returns:
            Whether to retry
        """
        # If we've reached the maximum number of retries, don't retry
        if retry_count >= max_retries:
            return False

        # Different error types have different retry policies
        if error_type == NetworkErrorType.RATE_LIMIT:
            # Always retry rate limit errors, but with increased backoff
            return True

        if error_type == NetworkErrorType.AUTHENTICATION:
            # Don't retry authentication errors, they usually require user intervention
            return False

        if error_type == NetworkErrorType.DATA_FORMAT:
            # Don't retry data format errors, they usually indicate a change in the API
            return False

        # Default to retrying for other error types
        return True

    def get_retry_delay(self, error_type: str, retry_count: int, strategy: str = RetryStrategy.EXPONENTIAL_BACKOFF) -> float:
        """Calculate the delay before retrying.

        Args:
            error_type: The error type
            retry_count: Current retry count
            strategy: Retry strategy to use

        Returns:
            Delay in seconds before retrying
        """
        # Base delay in seconds
        base_delay = 2.0

        # Apply jitter to prevent thundering herd problem
        jitter = 0.2 * (1.0 - (2.0 * (time.time() * 1000) % 1000) / 1000)

        # Different error types might need different backoff strategies
        if error_type == NetworkErrorType.RATE_LIMIT:
            # Rate limit errors need longer backoff
            base_delay = 5.0

        # Apply the selected strategy
        if strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            # Exponential backoff with jitter: delay = base_delay * (2^retry_count) * (1±jitter)
            delay = base_delay * (2 ** retry_count) * (1.0 + jitter)
        elif strategy == RetryStrategy.LINEAR_BACKOFF:
            # Linear backoff with jitter: delay = base_delay * (retry_count + 1) * (1±jitter)
            delay = base_delay * (retry_count + 1) * (1.0 + jitter)
        elif strategy == RetryStrategy.CONSTANT_DELAY:
            # Constant delay with jitter: delay = base_delay * (1±jitter)
            delay = base_delay * (1.0 + jitter)
        elif strategy == RetryStrategy.FIBONACCI_BACKOFF:
            # Fibonacci backoff with jitter
            fib_n_minus_1 = 1
            fib_n_minus_2 = 1
            for _ in range(retry_count):
                fib_n = fib_n_minus_1 + fib_n_minus_2
                fib_n_minus_2 = fib_n_minus_1
                fib_n_minus_1 = fib_n
            delay = base_delay * fib_n_minus_1 * (1.0 + jitter)
        else:
            # Default to exponential backoff
            delay = base_delay * (2 ** retry_count) * (1.0 + jitter)

        # Cap the maximum delay
        max_delay = 60.0  # 60 seconds
        return min(delay, max_delay)

    async def run_with_retry(
        self,
        func: Callable,
        *args,
        max_retries: int = 3,
        strategy: str = RetryStrategy.EXPONENTIAL_BACKOFF,
        **kwargs
    ) -> Any:
        """Run a function with retry logic.

        Args:
            func: The function to call
            *args: Arguments to pass to the function
            max_retries: Maximum number of retries
            strategy: Retry strategy to use
            **kwargs: Keyword arguments to pass to the function

        Returns:
            The result of the function

        Raises:
            Exception: If all retries fail
        """
        retry_count = 0
        last_error = None

        while retry_count <= max_retries:
            try:
                return await func(*args, **kwargs)
            except Exception as error:
                error_type = self.classify_error(error)

                # Update error statistics
                self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
                self.last_error_time[error_type] = datetime.now()

                # Determine if we should retry
                if retry_count >= max_retries or not self.should_retry(error_type, retry_count, max_retries):
                    _LOGGER.error(
                        f"Error in {self.source_type} API call (attempt {retry_count + 1}/{max_retries + 1}): {error}. "
                        f"Classified as {error_type}. Not retrying."
                    )
                    raise error

                # Calculate retry delay
                delay = self.get_retry_delay(error_type, retry_count, strategy)

                _LOGGER.warning(
                    f"Error in {self.source_type} API call (attempt {retry_count + 1}/{max_retries + 1}): {error}. "
                    f"Classified as {error_type}. Retrying in {delay:.2f}s."
                )

                # Wait before retrying
                await asyncio.sleep(delay)

                retry_count += 1
                last_error = error

        # If we get here, all retries failed
        if last_error:
            raise last_error

        # This should never happen
        raise RuntimeError(f"Unexpected error in {self.source_type} API call: all retries failed but no error was captured.")

    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics.

        Returns:
            Dictionary with error statistics
        """
        return {
            "source_type": self.source_type,
            "error_counts": self.error_counts,
            "last_error_time": {k: v.isoformat() for k, v in self.last_error_time.items()},
            "backoff_index": self.backoff_index
        }
