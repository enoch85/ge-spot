"""Test file for import validation.

This file is used to test imports and ensure that the module structure is correct.
It doesn't contain any actual functionality.
"""
import importlib
import os
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any

_LOGGER = logging.getLogger(__name__)

def test_utils_imports():
    """Test function to verify imports are working correctly."""
    try:
        # Test importing from utils.validation
        from .validation import validate_data, Schema, SchemaValidator, ValidationError

        # Test importing from api.base.error_handler
        from ..api.base.error_handler import retry_with_backoff, ErrorHandler, with_error_handling

        # Test importing from api.base.data_fetch
        from ..api.base.data_fetch import PriceDataFetcher

        return True
    except ImportError as e:
        _LOGGER.error(f"Import error: {e}")
        return False

def test_all_imports():
    """Test all imports in the codebase."""
    base_path = Path(__file__).parent.parent  # ge_spot directory
    success_count = 0
    error_count = 0
    errors = []

    # Get all Python files
    python_files = []
    for root, _, files in os.walk(base_path):
        for file in files:
            if file.endswith('.py') and file != '__pycache__':
                rel_path = os.path.relpath(os.path.join(root, file), base_path.parent.parent)
                module_path = rel_path.replace(os.sep, '.').replace('.py', '')
                python_files.append(module_path)

    # Try to import each module
    for module_path in sorted(python_files):
        try:
            importlib.import_module(module_path)
            success_count += 1
            _LOGGER.debug(f"Successfully imported {module_path}")
        except Exception as e:
            error_count += 1
            error_msg = f"Error importing {module_path}: {str(e)}"
            errors.append(error_msg)
            _LOGGER.error(error_msg)

    # Print summary
    print(f"\nImport Test Summary:")
    print(f"  Successful imports: {success_count}")
    print(f"  Failed imports: {error_count}")

    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"  - {error}")

    return error_count == 0

def test_imports() -> Dict[str, bool]:
    """Test importing component modules."""
    results = {}

    # Test importing from utils
    try:
        from ..utils import api_client, date_range
        results["utils_core"] = True
    except Exception as e:
        _LOGGER.error(f"Error importing utils core: {e}")
        results["utils_core"] = False

    # Test importing from api.base.error_handler
    try:
        from ..api.base.error_handler import ErrorHandler, retry_with_backoff
        results["api_base_error_handler"] = True
    except Exception as e:
        _LOGGER.error(f"Error importing api.base.error_handler: {e}")
        results["api_base_error_handler"] = False

    # Test importing from api.base.data_fetch
    try:
        from ..api.base.data_fetch import PriceDataFetcher
        results["api_base_data_fetch"] = True
    except Exception as e:
        _LOGGER.error(f"Error importing api.base.data_fetch: {e}")
        results["api_base_data_fetch"] = False

    # Test importing utils.validation
    try:
        from ..utils.validation import data_validator
        results["utils_validation"] = True
    except Exception as e:
        _LOGGER.error(f"Error importing utils.validation: {e}")
        results["utils_validation"] = False

    # Test importing timezone
    try:
        from ..timezone import TimezoneService
        results["timezone"] = True
    except Exception as e:
        _LOGGER.error(f"Error importing timezone: {e}")
        results["timezone"] = False

    # Test importing price
    try:
        from ..price import ElectricityPriceAdapter
        results["price"] = True
    except Exception as e:
        _LOGGER.error(f"Error importing price: {e}")
        results["price"] = False

    return results

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s - %(message)s'
    )

    # This will only run if the file is executed directly
    print("Testing all imports in the codebase...")
    result = test_all_imports()

    # Also run the utils-specific tests for backward compatibility
    utils_result = test_utils_imports()

    overall_result = result and utils_result
    print(f"\nOverall import test result: {'Success' if overall_result else 'Failed'}")

    # Exit with appropriate code for CI/CD pipelines
    sys.exit(0 if overall_result else 1)
