"""
Shared test fixtures and configurations for all tests.

This file contains fixtures that can be used across all test files,
making it easier to maintain consistent test environments.
"""

import sys
import pytest
from unittest.mock import MagicMock
from pathlib import Path

# Add the project root to the Python path to make imports work consistently
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Add test library to the path for easier imports
test_lib_path = Path(__file__).parent / "lib"
sys.path.insert(0, str(test_lib_path))


# Common fixtures used across multiple test files
@pytest.fixture
def mock_hass():
    """Provide a mock Home Assistant instance."""
    hass = MagicMock()
    hass.config.time_zone = "UTC"
    return hass


@pytest.fixture
def mock_config_entry():
    """Provide a mock config entry."""
    return MagicMock()


# Import fixtures from specialized modules if needed
# Try to import but don't fail if they don't exist yet
try:
    from .lib.fixtures.api_fixtures import *  # noqa
except (ImportError, ModuleNotFoundError):
    pass

try:
    from .lib.fixtures.data_fixtures import *  # noqa
except (ImportError, ModuleNotFoundError):
    pass
