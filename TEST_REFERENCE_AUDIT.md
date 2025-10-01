# Test Reference Audit - Wrong Key Names

## Summary

Found multiple integration tests still using old key names (`hourly_raw`, `hourly_prices`) that should be `interval_raw` and `interval_prices`.

## Issues Found

### 1. Unit Tests - Using Old Method (Low Priority)
These tests are specifically testing the old `normalize_hourly_prices()` method, which may be kept for backward compatibility:

- `tests/pytest/unit/test_service.py` - Multiple tests for `normalize_hourly_prices()`
  - Lines: 79, 98, 103, 118, 123, 144, 150, 169, 197
  - **Status**: May be OK - these are unit tests for the legacy method
  - **Action**: Consider if we want to keep these tests or migrate them

- `tests/pytest/unit/test_data_processor.py` - Line 368
  - Mock using `normalize_hourly_prices`
  - **Status**: Needs review - should production code use `normalize_interval_prices`?

### 2. Manual Integration Tests - Using Old Keys (HIGH PRIORITY) ❌

These tests are fetching data from parsers but looking for wrong keys:

#### AEMO Full Chain
- **File**: `tests/manual/integration/aemo_full_chain.py`
- **Line 133**: `raw_prices = parsed_data.get("hourly_raw", {})`
- **Should be**: `raw_prices = parsed_data.get("interval_raw", {})`

#### ComEd Full Chain
- **File**: `tests/manual/integration/comed_full_chain.py`
- **Lines**: 124, 125, 134, 138, 144
- **Problem**: Looking for `"hourly_raw"` key
- **Should be**: Looking for `"interval_raw"` key

#### EPEX Full Chain
- **File**: `tests/manual/integration/epex_full_chain.py`
- **Lines**: 151, 152, 161, 162, 168
- **Problem**: Looking for `"hourly_raw"` key
- **Should be**: Looking for `"interval_raw"` key

#### ENTSOE Full Chain
- **File**: `tests/manual/integration/entsoe_full_chain.py`
- **Lines**: 169, 170, 179, 180, 186
- **Problem**: Looking for `"hourly_raw"` key
- **Should be**: Looking for `"interval_raw"` key

#### OMIE Full Chain
- **File**: `tests/manual/integration/omie_full_chain.py`
- **Lines**: 131, 132, 149, 151, 155, 156, 163
- **Problem**: Looking for `"hourly_raw"` key
- **Should be**: Looking for `"interval_raw"` key

### 3. Pytest Integration Tests - Using Old Keys (HIGH PRIORITY) ❌

#### NordPool Live Test
- **File**: `tests/pytest/integration/test_nordpool_live.py`
- **Lines**: 325, 326, 327, 331, 334, 355, 367, 368
- **Problem**: Looking for `"hourly_prices"` key
- **Should be**: Looking for `"interval_raw"` key from parser
- **Impact**: Test will FAIL or show wrong interval count

#### EPEX Live Test
- **File**: `tests/pytest/integration/test_epex_live.py`
- **Lines**: 60, 61, 64, 65, 69, 72, 93, 104, 105
- **Problem**: Looking for `"hourly_prices"` key
- **Should be**: Looking for `"interval_raw"` key from parser
- **Impact**: Test will FAIL or show wrong interval count

#### Amber Live Test
- **File**: `tests/pytest/integration/test_amber_live.py`
- **Lines**: 81, 82
- **Problem**: Looking for `"hourly_prices"` key
- **Should be**: Looking for `"interval_raw"` key from parser
- **Impact**: Test will FAIL or show wrong interval count

### 4. Validation Tests - Correct ✅

These tests are CORRECT - they check that parsers do NOT return old keys:
- `tests/test_15min_migration.py` - Validates parsers return `interval_raw`, not `hourly_raw` ✅
- `tests/test_parser_validation.py` - Validates parsers return `interval_raw`, not `hourly_raw` ✅

## Impact Analysis

### Current Situation
These integration tests are likely **FAILING or BROKEN** because:
1. Parsers now return `interval_raw` key (after migration)
2. Tests look for `hourly_raw` key
3. Tests get empty data `{}`
4. Tests fail or show 0 intervals

### Example of Broken Test Flow
```python
# Parser returns (correct):
{"interval_raw": {96 15-minute intervals}, "timezone": "UTC", ...}

# Test tries to fetch (wrong):
raw_prices = parsed_data.get("hourly_raw", {})  # Returns {} because key doesn't exist!

# Test fails with:
"No prices found" or "0 intervals"
```

## Fix Priority

### Critical (Fix Immediately) 🔴
1. **Manual integration tests** - Change `hourly_raw` → `interval_raw`
   - aemo_full_chain.py
   - comed_full_chain.py
   - epex_full_chain.py
   - entsoe_full_chain.py
   - omie_full_chain.py

2. **Pytest integration tests** - Change `hourly_prices` → `interval_raw`
   - test_nordpool_live.py
   - test_epex_live.py
   - test_amber_live.py

### Medium (Review & Decide) 🟡
3. **Unit tests** - Decide if we keep `normalize_hourly_prices()` for backward compatibility
   - If keeping: Tests are OK
   - If removing: Update tests to use `normalize_interval_prices()`

## Next Steps

1. Fix all manual integration tests to use `interval_raw`
2. Fix all pytest integration tests to use `interval_raw`
3. Update expected interval counts (24 → 96 for 15-min APIs)
4. Run all tests to verify they pass
5. Decide on unit test strategy for legacy methods

## Expected Interval Counts After Fix

| Source | Key | Expected Count (per day) |
|--------|-----|-------------------------|
| NordPool | interval_raw | 96 (15-min) |
| AEMO | interval_raw | 96 (5-min aggregated to 15-min) |
| ComEd | interval_raw | 96 (5-min aggregated to 15-min) |
| ENTSOE | interval_raw | 96 (15-min) |
| EPEX | interval_raw | 96 (15-min) |
| Amber | interval_raw | TBD (30-min or hourly) |
| OMIE | interval_raw | 24 (hourly only) |
