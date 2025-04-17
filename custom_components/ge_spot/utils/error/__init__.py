"""Error handling utilities for GE Spot integration."""
from .error_record import ErrorRecord
from .error_tracker import ErrorTracker
from .retry_handler import RetryHandler
from .error_manager import ErrorManager, with_error_handling

# Define retry_with_backoff here to avoid circular imports
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
    # Create a retry handler
    handler = RetryHandler()

    # Convert parameters to retry_config format
    retry_config = {}
    if max_attempts is not None:
        retry_config["retry_count"] = max_attempts - 1  # Convert to retry count
    if base_delay is not None:
        retry_config["retry_delay"] = base_delay
    if backoff_factor is not None:
        retry_config["backoff_factor"] = backoff_factor

    # Execute with retry
    return await handler.execute_with_retry(func, *args, source=source,
                                         retry_config=retry_config, **kwargs)

# Decorator version of retry_with_backoff
def with_retry(max_attempts=None, base_delay=None, backoff_factor=None, source="unknown"):
    """Decorator to retry an async function with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (including the initial one)
        base_delay: Base delay between retries in seconds
        backoff_factor: Exponential backoff factor
        source: Source identifier for error tracking

    Returns:
        Decorated function
    """
    def decorator(func):
        import functools

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_with_backoff(
                func, *args,
                max_attempts=max_attempts,
                base_delay=base_delay,
                backoff_factor=backoff_factor,
                source=source or func.__name__,
                **kwargs
            )
        return wrapper
    return decorator

__all__ = [
    "ErrorRecord",
    "ErrorTracker",
    "RetryHandler",
    "retry_with_backoff",
    "with_retry",
    "ErrorManager",
    "with_error_handling"
]
