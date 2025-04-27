"""
Manual API tests for GE Spot.

This directory contains manual test scripts for testing the full chain of each API,
from fetching data to parsing and converting currencies. These tests make real
API calls and can be used to verify that the APIs are working correctly.

Each script is designed to be run manually from the command line to verify
that a specific API is working as expected. Most scripts accept an area code
as a command-line argument.

Examples:
    # Test ENTSOE API for the SE3 area
    python -m tests.python3.api.entsoe_test SE3
    
    # Test Nordpool API for the FI area
    python -m tests.python3.api.nordpool_test FI

All tests can also be run using the master script:
    ./scripts/run_manual_tests.sh
"""