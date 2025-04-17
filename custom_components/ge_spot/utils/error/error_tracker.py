"""Error tracking for API errors."""
import logging
from typing import Dict, Any, Optional, List

from .error_record import ErrorRecord

_LOGGER = logging.getLogger(__name__)

class ErrorTracker:
    """Track and analyze errors for better recovery strategies."""

    def __init__(self, max_history: int = 100):
        """Initialize the error tracker.

        Args:
            max_history: Maximum number of errors to keep in history
        """
        self._errors: List[ErrorRecord] = []
        self._max_history = max_history
        self._error_counts: Dict[str, int] = {}  # Count by error type
        self._source_counts: Dict[str, int] = {}  # Count by source

    def add_error(self, error: Exception, source: str, context: Optional[Dict[str, Any]] = None) -> ErrorRecord:
        """Add an error to the tracker.

        Args:
            error: The exception that occurred
            source: The source of the error (e.g., API name)
            context: Optional context information

        Returns:
            The created error record
        """
        record = ErrorRecord(error, source, context)

        # Add to history
        self._errors.append(record)

        # Trim history if needed
        if len(self._errors) > self._max_history:
            self._errors = self._errors[-self._max_history:]

        # Update counts
        self._error_counts[record.error_type] = self._error_counts.get(record.error_type, 0) + 1
        self._source_counts[source] = self._source_counts.get(source, 0) + 1

        return record

    def get_recent_errors(self, source: Optional[str] = None,
                         error_type: Optional[str] = None,
                         max_age: Optional[float] = None,
                         limit: Optional[int] = None) -> List[ErrorRecord]:
        """Get recent errors matching criteria.

        Args:
            source: Optional source filter
            error_type: Optional error type filter
            max_age: Optional maximum age in seconds
            limit: Optional limit on number of errors to return

        Returns:
            List of matching error records
        """
        result = []

        for record in reversed(self._errors):  # Most recent first
            # Apply filters
            if source and record.source != source:
                continue

            if error_type and record.error_type != error_type:
                continue

            if max_age is not None and record.age > max_age:
                continue

            result.append(record)

            # Apply limit
            if limit is not None and len(result) >= limit:
                break

        return result

    def get_error_frequency(self, source: Optional[str] = None,
                           error_type: Optional[str] = None,
                           time_window: Optional[float] = None) -> float:
        """Get the frequency of errors matching criteria.

        Args:
            source: Optional source filter
            error_type: Optional error type filter
            time_window: Optional time window in seconds

        Returns:
            Frequency of errors per minute
        """
        matching_errors = self.get_recent_errors(source, error_type, time_window)

        if not matching_errors:
            return 0.0

        if time_window is None:
            # Use the age of the oldest error as the time window
            oldest = matching_errors[-1]
            time_window = oldest.age

        # Avoid division by zero
        if time_window <= 0:
            time_window = 1.0

        # Convert to errors per minute
        return len(matching_errors) / (time_window / 60.0)

    def is_source_failing(self, source: str, threshold: int = 3,
                         time_window: Optional[float] = 300) -> bool:
        """Check if a source is consistently failing.

        Args:
            source: The source to check
            threshold: Number of errors to consider a source failing
            time_window: Optional time window in seconds (default: 5 minutes)

        Returns:
            True if the source is failing, False otherwise
        """
        recent_errors = self.get_recent_errors(source=source, max_age=time_window)
        return len(recent_errors) >= threshold

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about tracked errors."""
        return {
            "total_errors": len(self._errors),
            "unique_error_types": len(self._error_counts),
            "unique_sources": len(self._source_counts),
            "error_counts": dict(self._error_counts),
            "source_counts": dict(self._source_counts),
            "recent_errors": [e.metadata for e in self.get_recent_errors(limit=10)]
        }

    def clear(self) -> None:
        """Clear all tracked errors."""
        self._errors = []
        self._error_counts = {}
        self._source_counts = {}
