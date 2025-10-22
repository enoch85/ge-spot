"""Test file for import validation.

This file automatically discovers and tests all Python modules in the custom_components/ge_spot directory.
"""

import importlib
import os
import sys
import logging
import pytest
from pathlib import Path
from typing import List, Tuple

# Add workspace root to sys.path so we can import custom_components
_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

_LOGGER = logging.getLogger(__name__)


def discover_modules() -> List[Tuple[str, str]]:
    """Discover all Python modules in the ge_spot custom component.

    Returns:
        List of tuples (module_path, file_path) for all importable modules.
    """
    # Find the custom_components directory
    current_file = Path(__file__).resolve()
    # Go up to workspace root: tests/pytest/unit -> tests/pytest -> tests -> workspace
    workspace_root = current_file.parent.parent.parent.parent
    base_path = workspace_root / "custom_components" / "ge_spot"

    if not base_path.exists():
        _LOGGER.error(f"Base path does not exist: {base_path}")
        return []

    modules = []

    for root, dirs, files in os.walk(base_path):
        # Skip __pycache__ directories
        dirs[:] = [d for d in dirs if d != "__pycache__"]

        for file in files:
            if file.endswith(".py") and not file.startswith("_"):
                file_path = Path(root) / file
                # Convert file path to module path
                rel_path = file_path.relative_to(workspace_root)
                module_path = str(rel_path.with_suffix("")).replace(os.sep, ".")
                modules.append((module_path, str(file_path)))

    return sorted(modules)


def test_all_module_imports():
    """Test that all Python modules in ge_spot can be imported."""
    modules = discover_modules()

    failed_imports = []
    successful_imports = []

    for module_path, file_path in modules:
        try:
            importlib.import_module(module_path)
            successful_imports.append(module_path)
            _LOGGER.debug(f"✓ Successfully imported: {module_path}")
        except Exception as e:
            failed_imports.append((module_path, str(e)))
            _LOGGER.error(f"✗ Failed to import {module_path}: {e}")

    # Print summary
    print(f"\n{'='*70}")
    print(f"Import Test Results:")
    print(f"  Total modules: {len(modules)}")
    print(f"  Successful: {len(successful_imports)}")
    print(f"  Failed: {len(failed_imports)}")
    print(f"{'='*70}")

    if failed_imports:
        print("\nFailed imports:")
        for module_path, error in failed_imports:
            print(f"  ✗ {module_path}")
            print(f"    Error: {error}")

    # Assert all imports succeeded
    assert len(failed_imports) == 0, (
        f"\n{len(failed_imports)} module(s) failed to import. " f"See details above."
    )


def test_critical_imports():
    """Test that critical modules can be imported (fast smoke test)."""
    critical_modules = [
        "custom_components.ge_spot.coordinator.unified_price_manager",
        "custom_components.ge_spot.coordinator.cache_manager",
        "custom_components.ge_spot.api.nordpool",
        "custom_components.ge_spot.api.entsoe",
        "custom_components.ge_spot.sensor.base",
    ]

    for module_path in critical_modules:
        try:
            importlib.import_module(module_path)
        except Exception as e:
            pytest.fail(f"Critical module {module_path} failed to import: {e}")


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    print("Discovering modules...")
    modules = discover_modules()
    print(f"Found {len(modules)} modules to test\n")

    print("Testing all imports...")
    test_all_module_imports()

    print("\n✓ All import tests passed!")
    sys.exit(0)
