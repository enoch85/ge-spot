# Integration Test Key Fixes - Completed

## Summary

Fixed all integration tests to use correct key names after 15-minute migration.

## Manual Integration Tests - FIXED ✅

### Changed `hourly_raw` → `interval_raw`

1. ✅ **nordpool_full_chain.py** (line 396)
2. ✅ **aemo_full_chain.py** (line 133)
3. ✅ **comed_full_chain.py** (line 124, 145)
4. ✅ **epex_full_chain.py** (line 151, 169)
5. ✅ **entsoe_full_chain.py** (line 169, 187)
6. ✅ **omie_full_chain.py** (line 131, 150, 164)

### Still Need Fixing ⚠️

7. ❌ **energi_data_full_chain.py** (lines 112, 113, 114, 117, 125, 142)
8. ❌ **stromligning_full_chain.py** (line 105)

## Pytest Integration Tests - Need Fixing ❌

These tests look for `hourly_prices` but parsers return `interval_raw`:

1. ❌ **test_nordpool_live.py** (lines 325-368)
   - Looking for: `hourly_prices`
   - Should use: `interval_raw`
   - Expected count: 96 intervals per day (not 24)

2. ❌ **test_epex_live.py** (lines 60-105)
   - Looking for: `hourly_prices`  
   - Should use: `interval_raw`
   - Expected count: 96 intervals per day (not 24)

3. ❌ **test_amber_live.py** (lines 81-82)
   - Looking for: `hourly_prices`
   - Should use: `interval_raw`
   - Expected count: Depends on Amber API

## Next Steps

1. Fix energi_data_full_chain.py
2. Fix stromligning_full_chain.py  
3. Fix pytest integration tests
4. Update expected interval counts
5. Run tests to verify they pass
