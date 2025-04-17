"""Base data fetching utilities for API modules."""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from ...const.sources import Source

_LOGGER = logging.getLogger(__name__)

class BaseDataFetcher(ABC):
    """Base class for API data fetchers."""

    def __init__(self, source: str, session=None, config: Optional[Dict[str, Any]] = None):
        """Initialize the data fetcher.

        Args:
            source: Source identifier
            session: Optional session for API requests
            config: Optional configuration
        """
        self.source = source
        self.session = session
        self.config = config or {}
        self._owns_session = False

    @abstractmethod
    async def fetch_data(self, **kwargs) -> Dict[str, Any]:
        """Fetch data from API.

        Args:
            **kwargs: Additional keyword arguments

        Returns:
            Fetched data
        """
        pass

    async def process_response(self, response: Any) -> Dict[str, Any]:
        """Process API response.

        Args:
            response: Raw API response

        Returns:
            Processed data
        """
        # Default implementation returns the response as is
        return response

    async def handle_error(self, error: Exception) -> Dict[str, Any]:
        """Handle error during data fetching.

        Args:
            error: Exception that occurred

        Returns:
            Error response or None
        """
        _LOGGER.error(f"Error fetching data from {self.source}: {error}")
        return None

    async def validate_config(self) -> bool:
        """Validate configuration.

        Returns:
            True if configuration is valid, False otherwise
        """
        # Default implementation assumes valid config
        return True

    def create_skipped_response(self, reason: str = "missing_api_key") -> Dict[str, Any]:
        """Create a standardized response for when an API is skipped.

        Args:
            reason: The reason for skipping (default: "missing_api_key")

        Returns:
            A dictionary with standardized skipped response format
        """
        return create_skipped_response(self.source, reason)

def create_skipped_response(source: str, reason: str = "missing_api_key") -> Dict[str, Any]:
    """Create a standardized response for when an API is skipped.

    Args:
        source: The source identifier (e.g., Source.ENTSOE)
        reason: The reason for skipping (default: "missing_api_key")

    Returns:
        A dictionary with standardized skipped response format
    """
    _LOGGER.debug(f"Creating skipped response for {source}: {reason}")
    return {
        "skipped": True,
        "reason": reason,
        "source": source
    }

def is_skipped_response(data: Any) -> bool:
    """Check if a response is a skipped response.

    Args:
        data: The data to check

    Returns:
        True if the data is a skipped response, False otherwise
    """
    return (
        isinstance(data, dict) and
        data.get("skipped") is True and
        "reason" in data and
        "source" in data
    )
