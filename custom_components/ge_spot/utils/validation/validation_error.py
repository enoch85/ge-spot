"""Validation error class."""

class ValidationError(Exception):
    """Validation error with path information."""

    def __init__(self, message: str, path: str = ""):
        """Initialize the error.

        Args:
            message: Error message
            path: Path to the error
        """
        self.message = message
        self.path = path
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format the error message.

        Returns:
            Formatted message
        """
        if self.path:
            return f"{self.message} at {self.path}"
        return self.message
