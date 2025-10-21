"""Timestamp parsing with proper timezone handling."""

import logging
import re
from datetime import datetime
from typing import Optional, Union

from homeassistant.util import dt as dt_util

from .source_tz import get_timezone_object, get_source_timezone, get_source_format
from ..const.time import TimezoneConstants
from ..const.sources import Source
from ..const.api import SourceTimezone

_LOGGER = logging.getLogger(__name__)


class TimestampParser:
    """Parser for timestamps with timezone handling."""

    def parse(self, timestamp_str: Union[str, datetime], source_timezone: str) -> datetime:
        """Parse timestamp with explicit source timezone."""
        # Validate source_timezone
        if not source_timezone or source_timezone == TimezoneConstants.DEFAULT_FALLBACK:
            error_msg = f"Invalid source timezone provided: {source_timezone}"
            _LOGGER.error(error_msg)
            raise ValueError(error_msg)

        # Get timezone object
        source_tz = get_timezone_object(source_timezone)
        if not source_tz:
            # Try to get timezone from source type identifier
            source_tz_str = get_source_timezone(source_timezone)
            source_tz = get_timezone_object(source_tz_str)

            if not source_tz:
                error_msg = (
                    f"Invalid source timezone: {source_timezone}, cannot find timezone object"
                )
                _LOGGER.error(error_msg)
                raise ValueError(error_msg)

        # Handle datetime objects
        if isinstance(timestamp_str, datetime):
            dt = timestamp_str
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=source_tz)
                _LOGGER.debug(f"Attached source timezone {source_timezone} to naive datetime {dt}")
            return dt

        # Ensure timestamp_str is actually a string
        if not isinstance(timestamp_str, str):
            error_msg = f"Expected string or datetime, got {type(timestamp_str)}: {timestamp_str}"
            _LOGGER.error(error_msg)
            raise ValueError(error_msg)

        # Skip empty strings
        if not timestamp_str:
            error_msg = "Empty timestamp string provided"
            _LOGGER.error(error_msg)
            raise ValueError(error_msg)

        # Handle source-specific formats first
        try:
            # Handle ENTSO-E specific format (typically UTC/Z timestamps or numeric format)
            if source_timezone == Source.ENTSOE:
                # Handle ENTSOE numeric format like "202504121000"
                if re.match(r"^\d{12}$", timestamp_str):
                    format_str = SourceTimezone.API_FORMATS.get(Source.ENTSOE)
                    if format_str:
                        dt = datetime.strptime(timestamp_str, format_str)
                        dt = dt.replace(tzinfo=source_tz)
                        return dt

                # Handle ISO with Z suffix (UTC)
                if "T" in timestamp_str and timestamp_str.endswith("Z"):
                    dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    # If source timezone is not UTC, convert to it
                    if str(source_tz) != "UTC":
                        dt = dt.astimezone(source_tz)
                    return dt

            # Handle AEMO specific format (often includes milliseconds)
            if source_timezone == Source.AEMO:
                if "." in timestamp_str:
                    # Strip milliseconds for consistent parsing
                    parts = timestamp_str.split(".")
                    timestamp_str = parts[0] + ("Z" if timestamp_str.endswith("Z") else "")

            # Handle Energi Data specific format (often uses local Danish time)
            if source_timezone == Source.ENERGI_DATA_SERVICE:
                if "T" in timestamp_str:
                    # Try as ISO format first
                    try:
                        dt = datetime.fromisoformat(
                            timestamp_str.replace("Z", "+00:00")
                            if timestamp_str.endswith("Z")
                            else timestamp_str
                        )
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=source_tz)
                        return dt
                    except ValueError:
                        # Continue to general parsing
                        pass

            # Handle Stromligning specific format (typically Danish time with ISO format)
            if source_timezone == Source.STROMLIGNING:
                if timestamp_str.endswith("Z"):
                    dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    # Convert to source timezone if it's not UTC
                    if str(source_tz) != "UTC":
                        dt = dt.astimezone(source_tz)
                    return dt

            # Handle Nordpool format (typically ISO with explicit timezone or Z)
            if source_timezone == Source.NORDPOOL:
                if "T" in timestamp_str:
                    if timestamp_str.endswith("Z"):
                        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        # Convert to source timezone if it's not UTC
                        if str(source_tz) != "UTC":
                            dt = dt.astimezone(source_tz)
                        return dt

            # Try format from API_FORMATS dictionary
            format_str = SourceTimezone.API_FORMATS.get(source_timezone)
            if format_str:
                try:
                    dt = datetime.strptime(timestamp_str, format_str)
                    dt = dt.replace(tzinfo=source_tz)
                    return dt
                except ValueError:
                    # Continue to general parsing
                    pass

            # General ISO format handling
            if "T" in timestamp_str:
                if timestamp_str.endswith("Z"):
                    # UTC timestamp with Z suffix
                    dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    # Convert to source timezone if needed
                    if str(source_tz) != "UTC":
                        dt = dt.astimezone(source_tz)
                    return dt
                elif "+" in timestamp_str or "-" in timestamp_str and "T" in timestamp_str:
                    # ISO with timezone offset
                    dt = datetime.fromisoformat(timestamp_str)
                    # Convert to source timezone if needed
                    if dt.tzinfo and dt.tzinfo != source_tz:
                        dt = dt.astimezone(source_tz)
                    return dt
                else:
                    # Naive ISO format, add source timezone
                    dt = datetime.fromisoformat(timestamp_str)
                    dt = dt.replace(tzinfo=source_tz)
                    _LOGGER.debug(
                        f"Attached source timezone {source_timezone} to ISO timestamp {dt}"
                    )
                    return dt

        except ValueError as e:
            _LOGGER.debug(f"Source-specific parsing failed for {timestamp_str}: {e}")

        # Fall back to general parsing with HA's parse_datetime
        dt = dt_util.parse_datetime(timestamp_str)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=source_tz)
                _LOGGER.debug(f"Attached source timezone {source_timezone} to parsed datetime {dt}")
            elif dt.tzinfo != source_tz:
                # Convert to the expected source timezone
                dt = dt.astimezone(source_tz)
                _LOGGER.debug(
                    f"Converted datetime from {dt.tzinfo} to source timezone {source_timezone}"
                )
            return dt

        # Last resort: try custom parsing patterns
        for fmt in [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%d.%m.%Y %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d.%m.%Y",
            "%H:%M:%S",
        ]:
            try:
                dt = datetime.strptime(timestamp_str, fmt)
                dt = dt.replace(tzinfo=source_tz)
                _LOGGER.debug(
                    f"Parsed timestamp {timestamp_str} with format {fmt} and timezone {source_timezone}"
                )
                return dt
            except ValueError:
                continue

        error_msg = f"Failed to parse timestamp: {timestamp_str} with timezone {source_timezone}"
        _LOGGER.error(error_msg)
        raise ValueError(error_msg)

    def parse_safely(
        self, timestamp_str: Union[str, datetime], source_timezone: str
    ) -> Optional[datetime]:
        """Parse timestamp with error handling."""
        try:
            return self.parse(timestamp_str, source_timezone)
        except Exception as e:
            _LOGGER.error(f"Failed to parse timestamp {timestamp_str} with {source_timezone}: {e}")
            return None
