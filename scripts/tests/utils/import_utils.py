"""Utilities for import testing."""
import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Tuple, List

logger = logging.getLogger(__name__)


def get_all_python_files(base_path: Path) -> List[str]:
    """Get all Python files in the given directory and subdirectories.
    
    Args:
        base_path: Base directory to search for Python files
        
    Returns:
        List of module paths relative to the parent directory
    """
    python_files = []
    for root, _, files in os.walk(base_path):
        for file in files:
            if file.endswith('.py') and file != '__pycache__':
                rel_path = os.path.relpath(os.path.join(root, file), base_path.parent.parent)
                module_path = rel_path.replace(os.sep, '.').replace('.py', '')
                python_files.append(module_path)
    
    return sorted(python_files)


def test_utils_imports() -> bool:
    """Test function to verify utils imports are working correctly.
    
    Returns:
        True if all imports succeeded, False otherwise
    """
    try:
        # Import from custom_components.ge_spot.utils.validation
        from custom_components.ge_spot.utils.validation import validate_data, Schema, SchemaValidator, ValidationError

        # Import from custom_components.ge_spot.utils.error
        from custom_components.ge_spot.utils.error import retry_with_backoff, ErrorManager, with_error_handling

        # Import from custom_components.ge_spot.utils.fallback
        from custom_components.ge_spot.utils.fallback import FallbackManager

        logger.debug("Utils imports successful")
        return True
    except ImportError as e:
        logger.error(f"Utils import error: {e}")
        return False


def test_specific_module(module_path: str) -> bool:
    """Test importing a specific module.
    
    Args:
        module_path: Dot-separated module path to import
        
    Returns:
        True if import succeeded, False otherwise
    """
    try:
        importlib.import_module(module_path)
        logger.debug(f"Successfully imported {module_path}")
        return True
    except Exception as e:
        logger.error(f"Error importing {module_path}: {str(e)}")
        return False


def test_all_module_imports(base_path: Path) -> Tuple[int, int, List[str]]:
    """Test all imports in the codebase.
    
    Args:
        base_path: Base directory containing modules to test
        
    Returns:
        Tuple of (success count, error count, list of error messages)
    """
    success_count = 0
    error_count = 0
    errors = []

    # Get all Python files
    python_files = get_all_python_files(base_path)

    # Try to import each module
    for module_path in python_files:
        try:
            importlib.import_module(module_path)
            success_count += 1
            logger.debug(f"Successfully imported {module_path}")
        except Exception as e:
            error_count += 1
            error_msg = f"Error importing {module_path}: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg)

    return success_count, error_count, errors


def run_all_import_tests(print_summary: bool = True) -> bool:
    """Run all import tests.
    
    Args:
        print_summary: Whether to print a summary of the results
        
    Returns:
        True if all tests passed, False otherwise
    """
    # Find the ge_spot directory
    base_path = Path(__file__).parent.parent.parent.parent / "custom_components" / "ge_spot"
    
    if not base_path.exists():
        logger.error(f"GE-Spot directory not found at {base_path}")
        return False

    # Run all import tests
    success_count, error_count, errors = test_all_module_imports(base_path)
    
    # Also run the utils-specific tests for backward compatibility
    utils_result = test_utils_imports()
    
    overall_result = error_count == 0 and utils_result
    
    # Print summary
    if print_summary:
        print(f"\nImport Test Summary:")
        print(f"  Successful imports: {success_count}")
        print(f"  Failed imports: {error_count}")

        if errors:
            print("\nErrors:")
            for error in errors:
                print(f"  - {error}")
        
        print(f"\nOverall import test result: {'Success' if overall_result else 'Failed'}")
    
    return overall_result
