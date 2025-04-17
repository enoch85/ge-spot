"""Mock Home Assistant classes for testing."""
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class MockConfig:
    """Mock Home Assistant config for testing."""
    def __init__(self):
        """Initialize with default timezone UTC."""
        self.time_zone = "UTC"


class MockHass:
    """Mock Home Assistant instance for testing."""
    def __init__(self):
        """Initialize with default config and empty data."""
        self.config = MockConfig()
        self.data = {}
        
    async def async_add_executor_job(self, func: Callable, *args) -> Any:
        """Mock the async_add_executor_job method.
        
        Args:
            func: Function to execute
            *args: Arguments to pass to the function
            
        Returns:
            Result of the function call
        """
        try:
            return func(*args)
        except Exception as e:
            logger.error(f"Error in executor job: {e}")
            raise
