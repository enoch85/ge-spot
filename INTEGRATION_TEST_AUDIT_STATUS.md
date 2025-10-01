# Integration Test Audit - Complete Status

## ✅ COMPLETED FIXES

### 1. Method Name Fixes (normalize_hourly_prices → normalize_interval_prices)
All 7 manual integration tests now use the correct method:
- ✅ nordpool_full_chain.py
- ✅ aemo_full_chain.py  
- ✅ comed_full_chain.py
- ✅ epex_full_chain.py
- ✅ amber_full_chain.py
- ✅ entsoe_full_chain.py
- ✅ omie_full_chain.py

### 2. Key Name Fixes (hourly_raw → interval_raw)
Fixed 6 of 8 manual integration tests:
- ✅ nordpool_full_chain.py
- ✅ aemo_full_chain.py
- ✅ comed_full_chain.py
- ✅ epex_full_chain.py
- ✅ entsoe_full_chain.py
- ✅ omie_full_chain.py

## ❌ REMAINING ISSUES

### Manual Integration Tests (2 remaining)
1. **energi_data_full_chain.py**
   - Lines: 112, 113, 114, 117, 125, 142
   - Issue: Uses `hourly_raw` key
   - Fix: Change to `interval_raw`
   - Impact: Test will get empty dict and fail

2. **stromligning_full_chain.py**
   - Line: 105
   - Issue: Uses `hourly_raw` key
   - Fix: Change to `interval_raw`
   - Impact: Test will get empty dict and fail

### Pytest Integration Tests (3 tests)
3. **test_nordpool_live.py**
   - Lines: 325-368
   - Issue: Expects `hourly_prices` key from parser
   - Fix: Change to `interval_raw`
   - Fix: Update expected count from 24-48 to 96-192
   - Impact: TEST IS CURRENTLY BROKEN

4. **test_epex_live.py**
   - Lines: 60-105
   - Issue: Expects `hourly_prices` key from parser
   - Fix: Change to `interval_raw`
   - Fix: Update expected count from 24-48 to 96-192
   - Impact: TEST IS CURRENTLY BROKEN

5. **test_amber_live.py**
   - Lines: 81-82
   - Issue: Expects `hourly_prices` key from parser
   - Fix: Change to `interval_raw`
   - Fix: Update expected count based on Amber's actual interval
   - Impact: TEST IS CURRENTLY BROKEN

## Quick Fix Commands

### For Energi Data:
```bash
# Find all occurrences
grep -n "hourly_raw" tests/manual/integration/energi_data_full_chain.py

# Replace in file (manual)
# Line 112: hourly_raw_prices = parsed_data.get("interval_raw", {})
# Update all references to use interval_raw_prices
```

### For Stromligning:
```bash
# Find occurrence
grep -n "hourly_raw" tests/manual/integration/stromligning_full_chain.py

# Replace in file (manual)
# Line 105: hourly_prices = parsed_data.get("interval_raw", {})
```

### For Pytest Tests:
```bash
# Find all occurrences in pytest tests
grep -rn "hourly_prices" tests/pytest/integration/

# Each test needs:
# 1. Change key from "hourly_prices" to "interval_raw"
# 2. Update expected interval counts (24→96, 48→192, etc.)
# 3. Update validation logic for 15-minute intervals
```

## Verification Plan

After fixing remaining tests:

1. **Run Manual Integration Tests**:
   ```bash
   python tests/manual/integration/energi_data_full_chain.py
   python tests/manual/integration/stromlinging_full_chain.py
   ```

2. **Run Pytest Integration Tests**:
   ```bash
   pytest tests/pytest/integration/test_nordpool_live.py -v
   pytest tests/pytest/integration/test_epex_live.py -v
   pytest tests/pytest/integration/test_amber_live.py -v
   ```

3. **Verify Output Shows**:
   - ✅ 96+ intervals for 15-minute APIs
   - ✅ 24+ intervals for hourly APIs (OMIE)
   - ✅ No "key not found" errors
   - ✅ Tests pass

## Impact of Not Fixing

If these tests are not fixed:
- ❌ Tests will look for `hourly_raw` or `hourly_prices` keys
- ❌ Parsers return `interval_raw` key
- ❌ Tests get empty dict `{}`
- ❌ Tests fail with "No prices found"
- ❌ False impression that parsers are broken
- ❌ False impression that APIs don't provide 15-minute data

## Priority

**HIGH** - These tests are currently broken and need immediate fixing to validate that the 15-minute migration works correctly.

## Estimated Time

- Energi Data: 5 minutes
- Stromligning: 2 minutes  
- test_nordpool_live.py: 10 minutes
- test_epex_live.py: 10 minutes
- test_amber_live.py: 5 minutes
- **Total: ~30 minutes**

Would you like me to complete these remaining fixes?
