"""Source health tracking for API sources."""
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum, auto

_LOGGER = logging.getLogger(__name__)

class SourceHealthStatus(Enum):
    """Status of a data source."""

    HEALTHY = auto()
    DEGRADED = auto()
    UNHEALTHY = auto()
    UNKNOWN = auto()

class SourceHealth:
    """Track health of a data source."""

    def __init__(self, source: str):
        """Initialize source health.

        Args:
            source: Source identifier
        """
        self.source = source
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.last_request_time = None
        self.last_success_time = None
        self.last_failure_time = None
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.error_types = {}
        self.average_response_time = 0
        self.total_response_time = 0

    def update(self, success: Optional[bool], response_time: Optional[float] = None, error_type: Optional[str] = None) -> None:
        """Update source health.

        Args:
            success: Whether the request was successful (None if skipped)
            response_time: Optional response time in seconds
            error_type: Optional error type if the request failed
        """
        now = datetime.now()

        # If the source was skipped (success is None), don't count it as a request
        if success is None:
            _LOGGER.debug(f"Source {self.source} skipped, not counting in health metrics")
            return

        self.total_requests += 1
        self.last_request_time = now

        if success:
            self.successful_requests += 1
            self.last_success_time = now
            self.consecutive_successes += 1
            self.consecutive_failures = 0
        else:
            self.failed_requests += 1
            self.last_failure_time = now
            self.consecutive_failures += 1
            self.consecutive_successes = 0

            if error_type:
                self.error_types[error_type] = self.error_types.get(error_type, 0) + 1

        if response_time is not None:
            self.total_response_time += response_time
            self.average_response_time = self.total_response_time / self.total_requests

    @property
    def success_rate(self) -> float:
        """Get success rate."""
        if self.total_requests == 0:
            return 1.0  # Optimistic default
        return self.successful_requests / self.total_requests

    @property
    def is_healthy(self) -> bool:
        """Check if source is healthy."""
        # Consider a source healthy if:
        # 1. It has a success rate of at least 70%
        # 2. It has not failed more than 3 times in a row
        return self.success_rate >= 0.7 and self.consecutive_failures < 3

    @property
    def status(self) -> SourceHealthStatus:
        """Get source health status."""
        if self.total_requests == 0:
            return SourceHealthStatus.UNKNOWN

        if self.is_healthy:
            return SourceHealthStatus.HEALTHY

        if self.success_rate >= 0.5:
            return SourceHealthStatus.DEGRADED

        return SourceHealthStatus.UNHEALTHY

    @property
    def metadata(self) -> Dict[str, Any]:
        """Get metadata about source health."""
        return {
            "source": self.source,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "last_request_time": self.last_request_time.isoformat() if self.last_request_time else None,
            "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "error_types": self.error_types,
            "average_response_time": self.average_response_time,
            "success_rate": self.success_rate,
            "is_healthy": self.is_healthy,
            "status": self.status.name
        }
