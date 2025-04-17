# GE-Spot API Testing

This directory contains testing tools for the GE-Spot integration APIs.

## Directory Structure

```
scripts/tests/
├── api/                   # API testing functionality
│   ├── __init__.py
│   ├── api_testing.py     # API-specific testing logic
│   └── date_range_testing.py # Date range testing functionality
├── core/                  # Core testing components
│   ├── __init__.py
│   ├── reporting.py       # Test result reporting
│   └── runner.py          # Test runner and session management
├── mocks/                 # Mock objects for testing
│   ├── __init__.py
│   └── hass.py            # Mock Home Assistant classes
├── utils/                 # Testing utilities
│   ├── __init__.py
│   ├── general.py         # General utility functions 
│   └── import_utils.py    # Utilities for import testing
├── __init__.py
├── README.md              # This file
├── test_all_apis.py       # Entry point for API testing
├── test_date_range_apis.py # Entry point for date range testing
├── test_date_range_unit.py # Unit tests for date range utility
└── test_import.py         # Entry point for import testing
```

## Main Entry Points

There are several main test scripts:

1. **test_all_apis.py** - Tests API functionality by fetching price data from all supported APIs
2. **test_date_range_apis.py** - Tests the date range utility with all APIs
3. **test_date_range_unit.py** - Unit tests for the date range utility
4. **test_import.py** - Tests that all modules can be imported without errors

## Usage: API Tests

```bash
# Test all APIs and regions
python scripts/tests/test_all_apis.py

# Test specific APIs
python scripts/tests/test_all_apis.py --apis nordpool entsoe comed

# Test specific regions
python scripts/tests/test_all_apis.py --regions SE1 SE2 DE-LU 5minutefeed

# Set log level
python scripts/tests/test_all_apis.py --log-level DEBUG

# Set request timeout
python scripts/tests/test_all_apis.py --timeout 60
```

### Options for API Tests

- `--apis API1 API2 ...`: Specific APIs to test (default: all)
- `--regions REGION1 ...`: Specific regions to test (default: all)
- `--log-level LEVEL`: Set logging level (DEBUG, INFO, WARNING, ERROR)
- `--timeout SECONDS`: Set request timeout in seconds

## Usage: Date Range Tests

The date range tests verify that the date range utility works correctly with all APIs.
This is particularly important for ensuring that APIs can handle different time ranges
and timezone conversions correctly.

```bash
# Test all APIs with date range utility
python scripts/tests/test_date_range_apis.py

# Test specific APIs
python scripts/tests/test_date_range_apis.py --apis nordpool entsoe comed

# Test specific regions
python scripts/tests/test_date_range_apis.py --regions SE1 SE2 DE-LU 5minutefeed

# Set log level
python scripts/tests/test_date_range_apis.py --log-level DEBUG

# Set request timeout
python scripts/tests/test_date_range_apis.py --timeout 60

# Test with a specific reference time
python scripts/tests/test_date_range_apis.py --reference-time "2023-01-01T12:00:00Z"

# Test specifically for tomorrow's data
python scripts/tests/test_date_range_apis.py --test-tomorrow
```

### Options for Date Range Tests

- `--apis API1 API2 ...`: Specific APIs to test (default: all)
- `--regions REGION1 ...`: Specific regions to test (default: all)
- `--log-level LEVEL`: Set logging level (DEBUG, INFO, WARNING, ERROR)
- `--timeout SECONDS`: Set request timeout in seconds
- `--reference-time TIME`: Set reference time for testing (ISO format)
- `--test-tomorrow`: Test specifically for tomorrow's data

## Usage: Import Tests

```bash
# Test all imports
python scripts/tests/test_import.py

# Set log level
python scripts/tests/test_import.py --log-level DEBUG
```

### Options for Import Tests

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
python scripts/tests/test_all_apis.py
```

## Adding New Tests

When adding a new API to the GE-Spot integration, ensure it is properly registered in:

1. `custom_components/ge_spot/const/sources.py` - Add to Source class
2. `custom_components/ge_spot/const/areas.py` - Add areas to AreaMapping
3. `custom_components/ge_spot/api/__init__.py` - Register in SOURCE_REGION_SUPPORT and SOURCE_RELIABILITY

The test framework will automatically discover your new API and test it with all its supported regions.
