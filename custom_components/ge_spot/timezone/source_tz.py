"""API source timezone definitions."""

import logging
from typing import Optional
from datetime import tzinfo

from .timezone_utils import get_source_timezone, get_source_format, get_timezone_object

_LOGGER = logging.getLogger(__name__)


class SourceTimezone:
    """Class to handle source-specific timezone operations."""

    @staticmethod
    def get_timezone_for_source(source: str, area: Optional[str] = None) -> tzinfo:
        """Get the timezone for a specific data source.

        Args:
            source: The API source identifier
            area: Optional area code to further refine timezone selection

        Returns:
            The timezone object for the source/area combination
        """
        tz_name = get_source_timezone(source, area)
        return get_timezone_object(tz_name)

    @staticmethod
    def get_format_for_source(source: str) -> Optional[str]:
        """Get the datetime format string used by a specific source API.

        Args:
            source: The API source identifier

        Returns:
            Format string or None if not defined
        """
        return get_source_format(source)
