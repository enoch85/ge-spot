"""Shared utility functions for API implementations."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

_LOGGER = logging.getLogger(__name__)


async def fetch_optional_data(
    fetch_func: Callable[..., Awaitable[Any]],
    is_data_available: Callable[[Any], bool],
) -> Any:
    """Fetch optional prices once; the coordinator schedules subsequent attempts."""
    result = await fetch_func()
    if is_data_available(result):
        return result
    _LOGGER.debug("Optional prices not yet available; retry on a later refresh")
    return None
