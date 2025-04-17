"""Error record for tracking API errors."""
import logging
import traceback
from datetime import datetime
from typing import Dict, Any, Optional

_LOGGER = logging.getLogger(__name__)

class ErrorRecord:
    """Record of an error occurrence."""

    def __init__(self, error: Exception, source: str, context: Optional[Dict[str, Any]] = None):
        """Initialize an error record.

        Args:
            error: The exception that occurred
            source: The source of the error (e.g., API name)
            context: Optional context information
        """
        self.error = error
        self.error_type = type(error).__name__
        self.error_message = str(error)
        self.timestamp = datetime.now()
        self.source = source
        self.context = context or {}
        self.traceback = traceback.format_exc()

    @property
    def age(self) -> float:
        """Get the age of the error record in seconds."""
        return (datetime.now() - self.timestamp).total_seconds()

    @property
    def metadata(self) -> Dict[str, Any]:
        """Get metadata about the error record."""
        return {
            "error_type": self.error_type,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "context": self.context,
            "age": self.age
        }
