#!/usr/bin/env python3
"""Test script for GE-Spot integration APIs and regions.

This script tests all defined APIs and regions in the GE-Spot integration by
attempting to fetch price data for each region using its supported APIs.

Usage:
  python scripts/tests/test_all_apis.py [options]

Options:
  --apis API1 API2 ...     Specific APIs to test (default: all)
  --regions REGION1 ...    Specific regions to test (default: all)
  --log-level LEVEL        Set logging level (DEBUG, INFO, WARNING, ERROR)
  --timeout SECONDS        Set request timeout in seconds
"""
import asyncio
import sys
import os

# Add the parent directory to Python path so we can import the custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Import testing modules
from scripts.tests.utils.general import parse_args
from scripts.tests.core.runner import run_with_session_cleanup

if __name__ == "__main__":
    # Parse command-line arguments
    args = parse_args()
    
    # Run the tests
    asyncio.run(run_with_session_cleanup(args))
