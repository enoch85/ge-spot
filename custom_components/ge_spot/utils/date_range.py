"""Date range utilities for API data fetching."""

import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict, Any

from ..const.time import TimeInterval
from ..const.sources import Source

_LOGGER = logging.getLogger(__name__)


def generate_date_ranges(
    reference_time: datetime,
    source_type: str = None,
    interval: str = TimeInterval.HOURLY,
    include_historical: bool = True,
    include_future: bool = True,
    max_days_back: int = 2,
    max_days_forward: int = 2,
) -> List[Tuple[datetime, datetime]]:
    """Generate a list of date ranges to try when fetching API data.

    Note: This utility only generates date ranges for API requests. The actual
    filtering of data by date (e.g. extracting today's or tomorrow's prices)
    is handled by the individual API parsers after data is fetched.

    Args:
        reference_time: The reference time to base ranges on (usually now)
        source_type: Optional source type to customize ranges for specific APIs
        interval: Time interval (hourly, quarter-hourly, etc.)
        include_historical: Whether to include historical ranges
        include_future: Whether to include future ranges
        max_days_back: Maximum days to look back (used for specific sources and fallback)
        max_days_forward: Maximum days to look ahead (used for specific sources and fallback)

    Returns:
        List of (start_time, end_time) tuples to try in order
    """
    # Start with standard range (today to tomorrow)
    date_ranges = [(reference_time, reference_time + timedelta(days=1))]

    # Add historical ranges if requested
    if include_historical:
        # Yesterday to today
        date_ranges.append((reference_time - timedelta(days=1), reference_time))

        # Add more historical ranges if needed for specific sources
        if source_type in [Source.AEMO, Source.COMED]:
            # These sources sometimes need more historical data
            date_ranges.append((reference_time - timedelta(days=2), reference_time))

    # Add future ranges if requested
    if include_future:
        # Today to day after tomorrow
        date_ranges.append((reference_time, reference_time + timedelta(days=2)))

        # Add more future ranges for sources that provide forecasts
        if source_type in [Source.NORDPOOL, Source.ENTSOE]:
            date_ranges.append((reference_time, reference_time + timedelta(days=2)))

    # Add wider range as a fallback, using the function arguments
    date_ranges.append(
        (
            reference_time - timedelta(days=max_days_back),
            reference_time + timedelta(days=max_days_forward),
        )
    )

    # Remove duplicates while preserving order
    seen = set()
    unique_ranges = []
    for item in date_ranges:
        item_str = str(item)
        if item_str not in seen:
            unique_ranges.append(item)
            seen.add(item_str)
    date_ranges = unique_ranges

    # Handle special cases for specific APIs with non-hourly intervals
    if interval != TimeInterval.HOURLY or source_type in [Source.AEMO, Source.COMED]:
        adjusted_ranges = []
        for start, end in date_ranges:
            # For 5-minute intervals (AEMO, ComEd)
            if source_type in [Source.AEMO, Source.COMED]:
                # Round to nearest 5 minutes
                start_rounded = start.replace(
                    minute=start.minute - start.minute % 5, second=0, microsecond=0
                )
                end_rounded = end.replace(
                    minute=end.minute - end.minute % 5, second=0, microsecond=0
                )
                adjusted_ranges.append((start_rounded, end_rounded))
            # For quarter-hourly intervals
            elif interval == TimeInterval.QUARTER_HOURLY:
                # Round to nearest 15 minutes
                start_rounded = start.replace(
                    minute=start.minute - start.minute % 15, second=0, microsecond=0
                )
                end_rounded = end.replace(
                    minute=end.minute - end.minute % 15, second=0, microsecond=0
                )
                adjusted_ranges.append((start_rounded, end_rounded))
            else:
                adjusted_ranges.append((start, end))
        date_ranges = adjusted_ranges

    # Log the generated ranges
    _LOGGER.debug(
        f"Generated {len(date_ranges)} date ranges for {source_type or 'generic'} source"
    )
    for i, (start, end) in enumerate(date_ranges):
        _LOGGER.debug(f"Range {i+1}: {start.isoformat()} to {end.isoformat()}")

    return date_ranges
