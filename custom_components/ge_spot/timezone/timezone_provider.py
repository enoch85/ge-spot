"""Enhanced timezone handling for price data."""

import logging
import re
from datetime import datetime, timedelta, tzinfo
from typing import Dict, Any, Optional, List, Tuple, Union
import zoneinfo

from ..const.config import Config
from ..const.defaults import Defaults
from .timezone_utils import get_source_timezone, convert_datetime, get_timezone_object

_LOGGER = logging.getLogger(__name__)


class TimezoneProvider:
    """Provider for timezone handling and conversion."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the timezone provider.

        Args:
            config: Optional configuration
        """
        self.config = config or {}

        # Configuration
        self.local_timezone = self.config.get(Config.LOCAL_TIMEZONE, Defaults.LOCAL_TIMEZONE)

        # Cache for timezone objects
        self._timezone_cache: Dict[str, tzinfo] = {}

    def get_timezone(self, timezone_id: str) -> Optional[tzinfo]:
        """Get a timezone object.

        Args:
            timezone_id: Timezone identifier

        Returns:
            Timezone object or None if not found
        """
        # Check cache
        if timezone_id in self._timezone_cache:
            return self._timezone_cache[timezone_id]

        try:
            # Get timezone from zoneinfo
            tz = zoneinfo.ZoneInfo(timezone_id)

            # Cache timezone
            self._timezone_cache[timezone_id] = tz

            return tz
        except Exception as e:
            _LOGGER.error(f"Failed to get timezone {timezone_id}: {e}")
            return None

    def get_local_timezone(self) -> tzinfo:
        """Get the local timezone.

        Returns:
            Local timezone object
        """
        return self.get_timezone(self.local_timezone) or zoneinfo.ZoneInfo("UTC")

    def get_source_timezone(self, source: str, area: Optional[str] = None) -> tzinfo:
        """Get the timezone for a source.

        Args:
            source: Source identifier
            area: Optional area code

        Returns:
            Source timezone object
        """
        # Get timezone ID from source_tz module
        timezone_id = get_source_timezone(source, area)

        # Get timezone object
        return self.get_timezone(timezone_id) or zoneinfo.ZoneInfo("UTC")

    def localize_datetime(self, dt: datetime, timezone_id: Optional[str] = None) -> datetime:
        """Localize a datetime to a timezone.

        Args:
            dt: Datetime to localize
            timezone_id: Optional timezone identifier

        Returns:
            Localized datetime
        """
        # Get timezone
        tz = self.get_timezone(timezone_id) if timezone_id else self.get_local_timezone()

        # Check if datetime is already localized
        if dt.tzinfo is not None:
            # Convert to target timezone
            return dt.astimezone(tz)

        # Localize naive datetime
        return dt.replace(tzinfo=tz)

    def convert_to_local(self, dt: datetime) -> datetime:
        """Convert a datetime to local timezone.

        Args:
            dt: Datetime to convert

        Returns:
            Datetime in local timezone
        """
        # Get local timezone
        local_tz = self.get_local_timezone()

        # Check if datetime is already localized
        if dt.tzinfo is not None:
            # Convert to local timezone
            return dt.astimezone(local_tz)

        # Assume UTC if not localized
        utc_dt = dt.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
        return utc_dt.astimezone(local_tz)

    def convert_from_source(
        self, dt: datetime, source: str, area: Optional[str] = None
    ) -> datetime:
        """Convert a datetime from source timezone to local timezone.

        Args:
            dt: Datetime to convert
            source: Source identifier
            area: Optional area code

        Returns:
            Datetime in local timezone
        """
        # Get source timezone
        source_tz = self.get_source_timezone(source, area)

        # Get local timezone
        local_tz = self.get_local_timezone()

        # Check if datetime is already localized
        if dt.tzinfo is not None:
            # Convert to local timezone
            return dt.astimezone(local_tz)

        # Localize to source timezone
        source_dt = dt.replace(tzinfo=source_tz)

        # Convert to local timezone
        return source_dt.astimezone(local_tz)

    def format_datetime(self, dt: datetime, format_str: Optional[str] = None) -> str:
        """Format a datetime.

        Args:
            dt: Datetime to format
            format_str: Optional format string

        Returns:
            Formatted datetime string
        """
        # Default format
        if format_str is None:
            format_str = "%Y-%m-%d %H:%M:%S %Z"

        # Convert to local timezone if not localized
        if dt.tzinfo is None:
            dt = self.convert_to_local(dt)

        return dt.strftime(format_str)

    def parse_datetime(
        self, datetime_str: str, timezone_id: Optional[str] = None
    ) -> Optional[datetime]:
        """Parse a datetime string.

        Args:
            datetime_str: Datetime string to parse
            timezone_id: Optional timezone identifier

        Returns:
            Parsed datetime or None if parsing fails
        """
        # Try ISO format
        try:
            dt = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))

            # Convert to specified timezone if needed
            if timezone_id:
                tz = self.get_timezone(timezone_id)
                if tz:
                    dt = dt.astimezone(tz)

            return dt
        except ValueError:
            pass

        # Try common formats
        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(datetime_str, fmt)

                # Localize to specified timezone or local timezone
                tz = self.get_timezone(timezone_id) if timezone_id else self.get_local_timezone()
                dt = dt.replace(tzinfo=tz)

                return dt
            except ValueError:
                continue

        # Try to extract date and time with regex
        date_pattern = r"(\d{4})-(\d{1,2})-(\d{1,2})"
        time_pattern = r"(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?"

        date_match = re.search(date_pattern, datetime_str)
        time_match = re.search(time_pattern, datetime_str)

        if date_match:
            year, month, day = map(int, date_match.groups())

            hour, minute, second = 0, 0, 0
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))
                second = int(time_match.group(3) or 0)

            try:
                dt = datetime(year, month, day, hour, minute, second)

                # Localize to specified timezone or local timezone
                tz = self.get_timezone(timezone_id) if timezone_id else self.get_local_timezone()
                dt = dt.replace(tzinfo=tz)

                return dt
            except ValueError:
                pass

        _LOGGER.warning(f"Failed to parse datetime: {datetime_str}")
        return None

    def get_current_hour_start(self, timezone_id: Optional[str] = None) -> datetime:
        """Get the start of the current hour.

        Args:
            timezone_id: Optional timezone identifier

        Returns:
            Start of current hour
        """
        # Get timezone
        tz = self.get_timezone(timezone_id) if timezone_id else self.get_local_timezone()

        # Get current time in timezone
        now = datetime.now(tz)

        # Get start of current hour
        return now.replace(minute=0, second=0, microsecond=0)

    def get_day_start(self, dt: datetime) -> datetime:
        """Get the start of the day for a datetime.

        Args:
            dt: Datetime

        Returns:
            Start of day
        """
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    def get_day_end(self, dt: datetime) -> datetime:
        """Get the end of the day for a datetime.

        Args:
            dt: Datetime

        Returns:
            End of day
        """
        return dt.replace(hour=23, minute=59, second=59, microsecond=999999)

    def get_hour_range(self, dt: datetime) -> Tuple[datetime, datetime]:
        """Get the start and end of the hour for a datetime.

        Args:
            dt: Datetime

        Returns:
            Tuple of (start, end) of hour
        """
        start = dt.replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1) - timedelta(microseconds=1)
        return start, end

    def get_day_hours(self, dt: datetime) -> List[datetime]:
        """Get all interval start times for a day.

        Args:
            dt: Datetime

        Returns:
            List of interval start datetimes
        """
        from ..const.time import TimeInterval

        # Get start of day
        day_start = self.get_day_start(dt)

        # Get all intervals for the day
        interval_minutes = TimeInterval.get_interval_minutes()
        intervals_per_day = TimeInterval.get_intervals_per_day()
        return [
            day_start + timedelta(minutes=i * interval_minutes) for i in range(intervals_per_day)
        ]

    def is_dst_transition_day(self, dt: datetime) -> bool:
        """Check if a day is a DST transition day.

        Args:
            dt: Datetime

        Returns:
            True if the day is a DST transition day, False otherwise
        """
        # Get timezone
        tz = dt.tzinfo or self.get_local_timezone()

        # Get start of day
        day_start = self.get_day_start(dt)

        # Check if any hour has a different DST offset
        hours = self.get_day_hours(day_start)

        # Get DST offset for each hour
        offsets = [h.astimezone(tz).dst() for h in hours]

        # Check if there are different offsets
        return len(set(offsets)) > 1

    def handle_dst_transition(self, dt: datetime, is_start: bool = True) -> datetime:
        """Handle DST transition.

        Args:
            dt: Datetime
            is_start: Whether this is the start of DST

        Returns:
            Adjusted datetime
        """
        # Get timezone
        tz = dt.tzinfo or self.get_local_timezone()

        # Check if this is a DST transition day
        if not self.is_dst_transition_day(dt):
            return dt

        # Get all hours in the day
        day_start = self.get_day_start(dt)
        hours = self.get_day_hours(day_start)

        # Get DST offset for each hour
        offsets = [h.astimezone(tz).dst() for h in hours]

        # Find transition hour
        for i in range(1, len(hours)):
            if offsets[i] != offsets[i - 1]:
                transition_hour = hours[i]

                # Adjust datetime based on transition
                if is_start and dt.hour == transition_hour.hour:
                    # Skip the missing hour
                    return dt + timedelta(hours=1)
                elif not is_start and dt.hour == transition_hour.hour:
                    # Handle the repeated hour
                    return dt - timedelta(hours=1)

        return dt
