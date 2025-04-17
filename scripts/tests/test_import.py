#!/usr/bin/env python3
"""Test script for import validation in GE-Spot integration.

This script tests that all modules in the GE-Spot integration can be imported 
without errors. It serves as a basic validation that the module structure is correct.

Usage:
  python scripts/tests/test_import.py [options]
  
Options:
  --log-level LEVEL        Set logging level (DEBUG, INFO, WARNING, ERROR)
"""
import sys
import os
import logging
import argparse

# Add the parent directory to Python path so we can import the custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Import utility functions
from scripts.tests.utils.import_utils import run_all_import_tests


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Test all imports in the GE-Spot integration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all import tests with default logging
  python scripts/tests/test_import.py
  
  # Run with detailed debug logging
  python scripts/tests/test_import.py --log-level DEBUG
        """
    )
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                      default=os.environ.get('LOG_LEVEL', 'INFO'),
                      help='Set logging level (default: INFO)')
    return parser.parse_args()


if __name__ == "__main__":
    # Parse command line arguments
    args = parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(levelname)s - %(message)s'
    )
    
    # This will only run if the file is executed directly
    print("Testing all imports in the codebase...")
    result = run_all_import_tests()
    
    # Exit with appropriate code for CI/CD pipelines
    sys.exit(0 if result else 1)
