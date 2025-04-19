#!/usr/bin/env python3
"""Test summary script for the GE-Spot integration.

This script runs all core tests for the GE-Spot integration and presents a comprehensive
summary of the results. It serves as the main entry point for testing the integration.
"""
import sys
import os
import argparse
import unittest
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path so we can import the custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run GE-Spot integration tests")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], 
                        default="INFO", help="Set logging level")
    parser.add_argument("--tests", nargs="+", 
                        choices=["today", "tomorrow", "adapter", "api", "import", "date_range", "all"],
                        default=["all"], help="Specific tests to run")
    parser.add_argument("--apis", nargs="+", help="Specific APIs to test")
    parser.add_argument("--regions", nargs="+", help="Specific regions to test")
    return parser.parse_args()

def setup_logging(level):
    """Set up logging with the specified level."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level}")
    logging.getLogger().setLevel(numeric_level)

def run_test(test_script, description):
    """Run a test script and return the result."""
    print(f"\nRunning {description}...")
    result = os.system(f"python {test_script}")
    return result == 0  # True if test passed (exit code 0)

def run_adapter_tests():
    """Run adapter tests by importing test cases from test_tomorrow_data_manager."""
    from scripts.tests.test_tomorrow_data_manager import TestAdapterDateHandling
    
    # Create a test suite with the adapter tests
    suite = unittest.TestSuite()
    for test_method in [method for method in dir(TestAdapterDateHandling) if method.startswith('test_')]:
        suite.addTest(TestAdapterDateHandling(test_method))
    
    # Run the tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()

def run_tests(args):
    """Run all specified tests and print a summary."""
    start_time = datetime.now()
    
    # Print header
    print("\n" + "=" * 80)
    print("GE-SPOT INTEGRATION TEST SUMMARY")
    print("=" * 80)
    
    print(f"\nTest Date: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Track test results
    results = {}
    
    # Determine which tests to run
    run_all = "all" in args.tests
    
    # Run today data manager tests
    if run_all or "today" in args.tests:
        results["Today Data Manager"] = run_test(
            "scripts/tests/test_today_data_manager.py", 
            "Today Data Manager tests"
        )
    
    # Run tomorrow data manager tests
    if run_all or "tomorrow" in args.tests:
        results["Tomorrow Data Manager"] = run_test(
            "scripts/tests/test_tomorrow_data_manager.py", 
            "Tomorrow Data Manager tests"
        )
    
    # Run adapter tests
    if run_all or "adapter" in args.tests:
        results["Adapter"] = run_adapter_tests()
    
    # Run API tests
    if run_all or "api" in args.tests:
        api_cmd = "scripts/tests/test_all_apis.py"
        if args.apis:
            api_cmd += f" --apis {' '.join(args.apis)}"
        if args.regions:
            api_cmd += f" --regions {' '.join(args.regions)}"
        results["API"] = run_test(api_cmd, "API tests")
    
    # Run import tests
    if run_all or "import" in args.tests:
        results["Import"] = run_test(
            "scripts/tests/test_import.py", 
            "Import tests"
        )
    
    # Run date range tests
    if run_all or "date_range" in args.tests:
        date_range_cmd = "scripts/tests/test_date_range.py"
        if args.apis:
            date_range_cmd += f" --apis {' '.join(args.apis)}"
        if args.regions:
            date_range_cmd += f" --regions {' '.join(args.regions)}"
        results["Date Range"] = run_test(date_range_cmd, "Date Range tests")
    
    # Calculate test duration
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    print(f"\nTest completed in {duration:.2f} seconds")
    
    # Print individual test results
    for test_name, passed in results.items():
        status = "PASSED" if passed else "FAILED"
        print(f"{test_name} tests: {status}")
    
    # Print overall status
    overall_status = "PASSED" if all(results.values()) else "FAILED"
    print(f"\nOverall status: {overall_status}")
    
    # Print implemented fixes
    print("\n" + "=" * 80)
    print("IMPLEMENTED FIXES")
    print("=" * 80)
    
    print("""
1. ElectricityPriceAdapter Fix:
   - Added support for parsing ISO format dates in hourly_prices and tomorrow_hourly_prices
   - Added ability to extract tomorrow's data from hourly_prices when it has dates
   - Improved error handling for invalid hour formats

2. Testing Infrastructure:
   - Created core testing modules for adapter and API testing
   - Added sample data files with ISO format dates
   - Created comprehensive tests for verifying the fixes
   - Organized test files into appropriate directories
    """)
    
    # Return overall status
    return all(results.values())

if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.log_level)
    success = run_tests(args)
    sys.exit(0 if success else 1)
