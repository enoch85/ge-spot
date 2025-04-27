"""
API-specific integration tests for GE Spot.

This directory contains integration tests that specifically test the API components
including real API calls marked with pytest.mark.liveapi.

These tests verify that:
1. API clients can connect to real services
2. Raw data can be fetched from the service
3. The raw data can be properly parsed
4. Currency conversions work as expected

To run only tests that don't make real API calls:
    pytest tests/integration/api/ -k "not liveapi"

To run only tests that do make real API calls:
    pytest tests/integration/api/ -m liveapi
"""