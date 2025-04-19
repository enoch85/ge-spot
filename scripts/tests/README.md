# GE-Spot Testing Framework

This directory contains comprehensive testing tools for the GE-Spot integration, including API tests, adapter tests, and data manager tests.

## Directory Structure

```
scripts/tests/
├── api/                   # API testing functionality
│   ├── __init__.py
│   ├── api_testing.py     # API-specific testing logic
│   ├── date_range_testing.py # Date range testing functionality
│   └── tomorrow_api_testing.py # Tomorrow data API testing
├── core/                  # Core testing components
│   ├── __init__.py
│   ├── adapter_testing.py # Adapter testing utilities
│   ├── reporting.py       # Test result reporting
│   └── runner.py          # Test runner and session management
├── data/                  # Sample data for testing
│   ├── sample_data_with_dates.json        # Sample data with ISO format dates
│   └── sample_data_with_separate_tomorrow.json # Sample data with separate tomorrow data
├── debug/                 # Debug utilities
│   ├── __init__.py
│   └── debug_*.py         # Various debug scripts
├── mocks/                 # Mock objects for testing
│   ├── __init__.py
│   └── hass.py            # Mock Home Assistant classes
├── parsers/               # Parser-specific tests
│   ├── __init__.py
│   └── test_*_parser.py   # Parser-specific tests
├── utils/                 # Testing utilities
│   ├── __init__.py
│   ├── general.py         # General utility functions 
│   └── import_utils.py    # Utilities for import testing
├── __init__.py
├── README.md              # This file
├── test_adapters.py       # Tests for ElectricityPriceAdapter implementations
├── test_all_apis.py       # Tests API functionality for parsers
├── test_date_range.py     # Tests date range functionality
├── test_import.py         # Tests module imports
├── test_summary.py        # Main entry point for all tests
├── test_todays_data.py    # Comprehensive tests for today's data functionality
└── test_tomorrows_data.py # Comprehensive tests for tomorrow's data functionality
```

## Main Test Scripts

The GE-Spot testing framework has four main test scripts for the core functionality:

1. `test_todays_data.py`: Comprehensive tests for today's data functionality
2. `test_tomorrows_data.py`: Comprehensive tests for tomorrow's data functionality
3. `test_adapters.py`: Tests for ElectricityPriceAdapter implementations
4. `test_all_apis.py`: Tests API functionality for all parsers

These scripts are designed to be easy to use and cover all the core functionality of the integration. They use a smart caching approach, trying to use cached data first, then falling back to live API calls if necessary.

## Running the Main Tests

### Today's Data Tests

```bash
# Test all parsers
python scripts/tests/test_todays_data.py

# Test specific parser
python scripts/tests/test_todays_data.py --parser nordpool --area SE3

# Test TodayDataManager
python scripts/tests/test_todays_data.py --test-tdm --api-key YOUR_API_KEY

# Enable debug logging
python scripts/tests/test_todays_data.py --debug
```

### Tomorrow's Data Tests

```bash
# Test all parsers
python scripts/tests/test_tomorrows_data.py

# Test with API key for services requiring authentication (like ENTSOE)
python scripts/tests/test_tomorrows_data.py --api-key YOUR_API_KEY

# Test specific parser
python scripts/tests/test_tomorrows_data.py --parser entsoe --area SE4

# Test direct Nordpool API
python scripts/tests/test_tomorrows_data.py --test-direct-nordpool

# Test TomorrowDataManager
python scripts/tests/test_tomorrows_data.py --test-tdm --api-key YOUR_API_KEY

# Enable debug logging
python scripts/tests/test_tomorrows_data.py --debug
```

### Adapter Tests

```bash
# Run all adapter tests
python scripts/tests/test_adapters.py

# Test with synthetic data
python scripts/tests/test_adapters.py --test-synthetic

# Test with ENTSOE data
python scripts/tests/test_adapters.py --test-entsoe

# Test with live API data
python scripts/tests/test_adapters.py --test-live --parser nordpool --area SE3

# Enable debug logging
python scripts/tests/test_adapters.py --debug
```

### API Tests

```bash
# Test all APIs and regions
python scripts/tests/test_all_apis.py

# Test specific APIs
python scripts/tests/test_all_apis.py --apis nordpool entsoe comed

# Test specific regions
python scripts/tests/test_all_apis.py --regions SE1 SE2 DE-LU 5minutefeed
```

## Summary Test

The `test_summary.py` script is a meta-test that runs all core tests and presents a comprehensive summary of the results.

```bash
# Run all tests
python scripts/tests/test_summary.py

# Run specific test categories
python scripts/tests/test_summary.py --tests today tomorrow adapter api import date_range

# Run tests for specific APIs
python scripts/tests/test_summary.py --apis nordpool entsoe comed

# Run tests for specific regions
python scripts/tests/test_summary.py --regions SE1 SE2 DE-LU 5minutefeed

# Set log level
python scripts/tests/test_summary.py --log-level DEBUG
```

### Options for Summary Tests

- `--tests TEST1 TEST2 ...`: Specific test categories to run (choices: today, tomorrow, adapter, api, import, date_range, all)
- `--apis API1 API2 ...`: Specific APIs to test (default: all)
- `--regions REGION1 ...`: Specific regions to test (default: all)
- `--log-level LEVEL`: Set logging level (DEBUG, INFO, WARNING, ERROR)

## Environment Variables

Some APIs require API keys, which can be provided via environment variables:

```bash
# For ENTSO-E
export API_KEY=your_entsoe_api_key

# For EPEX France
export RTE_CLIENT_ID=your_rte_client_id
export RTE_CLIENT_SECRET=your_rte_client_secret

# Run tests with environment variables
python scripts/tests/test_summary.py
```

## Adding New Tests

When adding a new API to the GE-Spot integration, ensure it is properly registered in:

1. `custom_components/ge_spot/const/sources.py` - Add to Source class
2. `custom_components/ge_spot/const/areas.py` - Add areas to AreaMapping
3. `custom_components/ge_spot/api/__init__.py` - Register in SOURCE_REGION_SUPPORT and SOURCE_RELIABILITY

The test framework will automatically discover your new API and test it with all its supported regions.

## Understanding the Results

The tests will check if each API is returning the expected data, and if the integration is correctly extracting that data. The results will show:

- Which APIs are returning data
- How many hours of data are available
- Whether the ElectricityPriceAdapter can correctly extract data
- Whether the ImprovedElectricityPriceAdapter can extract data when the original adapter cannot

Results are saved as JSON files in the test_results directory, with a timestamp in the filename.

## Recent Fixes and Improvements

Recent improvements to the integration include:

1. **Consolidated Testing Framework**: Combined separate test scripts into comprehensive test files for better organization and ease of use.
2. **ElectricityPriceAdapter Improvements**: Added ImprovedElectricityPriceAdapter to extract tomorrow's data from hourly_prices when it has ISO format dates.
3. **Smart Caching Approach**: All tests now use a smart caching approach, trying to use cached data first, then falling back to live API calls if necessary.
4. **Enhanced API Client**: Updated the ApiClient.fetch method to handle 204 status codes as successful responses.
5. **Enhanced Nordpool Parser**: Updated the NordpoolPriceParser to handle edge cases like empty dictionaries.
