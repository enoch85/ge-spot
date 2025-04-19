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
├── mocks/                 # Mock objects for testing
│   ├── __init__.py
│   └── hass.py            # Mock Home Assistant classes
├── utils/                 # Testing utilities
│   ├── __init__.py
│   ├── general.py         # General utility functions 
│   └── import_utils.py    # Utilities for import testing
├── __init__.py
├── README.md              # This file
├── test_all_apis.py       # Tests API functionality
├── test_date_range.py     # Tests date range functionality
├── test_import.py         # Tests module imports
├── test_summary.py        # Main entry point for all tests
├── test_today_data_manager.py  # Tests today's data manager
└── test_tomorrow_data_manager.py # Tests tomorrow's data manager
```

## Main Entry Point

The main entry point for running tests is `test_summary.py`. This script runs all core tests and presents a comprehensive summary of the results.

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

## Individual Test Scripts

While `test_summary.py` is the recommended way to run tests, you can also run individual test scripts directly:

### API Tests

```bash
# Test all APIs and regions
python scripts/tests/test_all_apis.py

# Test specific APIs
python scripts/tests/test_all_apis.py --apis nordpool entsoe comed

# Test specific regions
python scripts/tests/test_all_apis.py --regions SE1 SE2 DE-LU 5minutefeed
```

### Date Range Tests

```bash
# Test date range functionality
python scripts/tests/test_date_range.py

# Test with specific APIs
python scripts/tests/test_date_range.py --apis nordpool entsoe
```

### Today/Tomorrow Data Manager Tests

```bash
# Test today's data manager
python scripts/tests/test_today_data_manager.py

# Test tomorrow's data manager
python scripts/tests/test_tomorrow_data_manager.py
```

### Import Tests

```bash
# Test all imports
python scripts/tests/test_import.py
```

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

## Testing the ElectricityPriceAdapter

The ElectricityPriceAdapter is tested in the `test_tomorrow_data_manager.py` file, which includes tests for:

1. Handling ISO format dates in hourly_prices
2. Handling ISO format dates in tomorrow_hourly_prices
3. Extracting tomorrow's data from hourly_prices when it has dates
4. Validating tomorrow's data

These tests use sample data files from the `data/` directory to verify that the adapter correctly handles different data formats.
