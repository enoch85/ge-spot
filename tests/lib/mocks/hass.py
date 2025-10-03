"""Mock Home Assistant for testing."""
from unittest.mock import MagicMock


class MockHass:
    """Simple mock for Home Assistant instance."""
    
    def __init__(self):
        """Initialize the mock."""
        self.data = {}
        self.config = MagicMock()
        self.config.time_zone = "UTC"
        self.states = MagicMock()
        self.bus = MagicMock()
        self.loop = None
