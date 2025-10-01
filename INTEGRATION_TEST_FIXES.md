# Integration Test Fixes Required

## Problem

The integration tests are **not testing production code**. They are reimplementing the production logic and testing their own code instead.

### Current (Wrong) Flow:
```
Integration Test
├── Manually fetches data from API
├── Manually calls parser
├── Manually calls timezone converter (normalize_hourly_prices ❌)
├── Manually converts currency
├── Manually builds data structures
└── Validates output
```

### Correct Flow:
```
Integration Test
├── Fetches data from API (or uses test fixtures)
├── Calls DataProcessor.process() ✅ (production code)
└── Validates output
```

## Current Issues

### 1. **Using Wrong Method**
All integration tests use `normalize_hourly_prices()` which aggregates 15-minute intervals to hourly:

- ❌ `tests/manual/integration/aemo_full_chain.py` line 152
- ❌ `tests/manual/integration/comed_full_chain.py` line 143
- ❌ `tests/manual/integration/epex_full_chain.py` line 167
- ❌ `tests/manual/integration/amber_full_chain.py` line 171
- ❌ `tests/manual/integration/entsoe_full_chain.py` line 184
- ❌ `tests/manual/integration/omie_full_chain.py` line 161
- ✅ `tests/manual/integration/nordpool_full_chain.py` line 464 (FIXED - now uses `normalize_interval_prices()`)

### 2. **Not Testing Production Code**
The tests manually reimplement all the logic that **DataProcessor** already does:
- Timezone normalization
- Currency conversion
- Data structure building
- Statistics calculation

This means:
- ✅ Tests pass → The test code works
- ❓ Tests pass → We don't know if production code works

## Solution

### Option 1: Use DataProcessor (Recommended)
Refactor integration tests to use the **DataProcessor** which is the actual production code:

```python
# Instead of:
api = NordpoolAPI(session)
raw_data = await api.fetch(area, date)
parsed_data = parser.parse(raw_data)
normalized = tz_converter.normalize_hourly_prices(parsed_data['interval_raw'])  # Wrong!

# Do this:
from custom_components.ge_spot.coordinator.data_processor import DataProcessor

api = NordpoolAPI(session)
raw_data = await api.fetch(area, date)
parsed_data = parser.parse(raw_data)

# Use production code
processor = DataProcessor(hass, area, target_currency, config, tz_service, manager)
processed_data = await processor.process(parsed_data)

# Validate the processed data
assert len(processed_data['interval_prices']) == 96  # 15-minute intervals
```

### Option 2: Quick Fix (Not Recommended)
Just change `normalize_hourly_prices()` to `normalize_interval_prices()` in all tests.

**Problem with Option 2:**
- Still not testing production code
- Duplicates production logic in tests
- Tests can pass while production code is broken

## Verification Plan

After fixing, the integration tests should verify:

1. **API Fetch Works**
   - Can connect to API
   - Gets valid response

2. **Parser Works** 
   - Extracts correct number of intervals
   - For 15-minute APIs: 96 intervals per day
   - For 5-minute APIs: 288 intervals per day (aggregated to 96)

3. **DataProcessor Works (Production Code!)**
   - Normalizes timezones correctly
   - Preserves 15-minute granularity
   - Converts currencies
   - Calculates statistics
   - Handles today/tomorrow split

4. **Cache Works**
   - Stores processed data
   - Retrieves cached data
   - Respects TTL

## Next Steps

1. ✅ Fixed `nordpool_full_chain.py` to use `normalize_interval_prices()` 
2. ⏳ Decide: Refactor to use DataProcessor OR just fix the method calls?
3. ⏳ Apply fix to all 6 remaining integration tests
4. ⏳ Run all integration tests to verify 15-minute support
5. ⏳ Document expected interval counts per API

## Expected Intervals by Source

| Source | Raw Interval | After Processing | Notes |
|--------|--------------|------------------|-------|
| NordPool | 96 (15-min) | 96 (15-min) | Native 15-min support |
| AEMO | 288 (5-min) | 96 (15-min) | Aggregated 5→15 min |
| ComEd | 288 (5-min) | 96 (15-min) | Aggregated 5→15 min |
| ENTSOE | 96 (15-min) | 96 (15-min) | Native 15-min support |
| EPEX | 96 (15-min) | 96 (15-min) | Native 15-min support |
| Amber | ? | 96 (15-min) | TBD |
| OMIE | 24 (hourly) | 24 (hourly) | Hourly only |

## Key Principle

> **Integration tests must test PRODUCTION code paths, not reimplement the logic**

If we change how DataProcessor works, the tests should immediately reflect that change without needing to be updated.
