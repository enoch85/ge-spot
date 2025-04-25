import pytest
import sys
from pathlib import Path

# Add the project root to the Python path for all tests
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
