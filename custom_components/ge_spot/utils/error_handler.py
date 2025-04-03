"""Error handling utilities for GE-Spot integration."""
import logging
import functools
import asyncio
from typing import Any, Callable, TypeVar, cast

_LOGGER = logging.getLogger(__name__)

T = TypeVar('T')

def retry_async(max_attempts: int = 3, base_delay: float = 1.0):
    """Retry decorator for async functions with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts before giving up
        base_delay: Base delay for exponential backoff in seconds

    Returns:
        Decorator function
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_attempts - 1:
                        wait_time = base_delay * (2 ** attempt)  # Exponential backoff
                        _LOGGER.debug(
                            f"Retrying {func.__name__} after error: {str(e)}. "
                            f"Attempt {attempt+1}/{max_attempts}, waiting {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        _LOGGER.error(
                            f"Function {func.__name__} failed after {max_attempts} attempts: {str(e)}"
                        )

            # All attempts failed, re-raise the last error
            if last_error:
                raise last_error
            return None

        return cast(Callable[..., Any], wrapper)

    return decorator

class APIError(Exception):
    """Base class for API errors."""
    def __init__(self, message: str, status_code: int = None):
        self.status_code = status_code
        self.message = message
        super().__init__(message)

class RateLimitError(APIError):
    """Error raised when API rate limit is exceeded."""
    pass

class AuthenticationError(APIError):
    """Error raised for authentication issues."""
    pass

class DataParsingError(APIError):
    """Error raised when API data cannot be parsed."""
    pass

async def handle_api_errors(func: Callable, *args, **kwargs) -> Any:
    """Execute a function and handle API errors gracefully.

    Args:
        func: Async function to execute
        *args: Arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        Result of the function or None if an error occurred
    """
    try:
        return await func(*args, **kwargs)
    except RateLimitError as e:
        _LOGGER.warning(f"API rate limit exceeded: {e.message}")
        return None
    except AuthenticationError as e:
        _LOGGER.error(f"API authentication error: {e.message}")
        return None
    except DataParsingError as e:
        _LOGGER.error(f"Data parsing error: {e.message}")
        return None
    except APIError as e:
        _LOGGER.error(f"API error: {e.message}")
        return None
    except Exception as e:
        _LOGGER.error(f"Unexpected error: {str(e)}")
        return None
