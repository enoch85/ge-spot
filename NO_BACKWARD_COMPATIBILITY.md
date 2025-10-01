# No Backward Compatibility Policy

**Date:** October 1, 2025  
**Applied to:** Phases 1-8 of 15-minute interval migration

## Policy

**Rule 7: No Backward Compatibility - Clean Renames Only**

All functions and variables must be renamed completely:
- ❌ **NEVER** keep old function names as aliases
- ❌ **NEVER** create wrapper functions for backward compatibility
- ✅ **ALWAYS** rename the function/class directly
- ✅ **ALWAYS** update ALL callers to use the new name
- ✅ **ALWAYS** update ALL tests to use the new name

## Example: WRONG Approach (Backward Compatibility)

```python
# ❌ DON'T DO THIS:
def normalize_hourly_prices(self, *args, **kwargs):
    """Backward compatibility alias."""
    return self.normalize_interval_prices(*args, **kwargs)

def normalize_interval_prices(self, interval_prices, ...):
    """Normalizes timestamps in interval price dictionary."""
    # ... implementation
```

## Example: CORRECT Approach (Clean Rename)

```python
# ✅ DO THIS:
def normalize_interval_prices(self, interval_prices, ...):
    """Normalizes timestamps in interval price dictionary."""
    # ... implementation

# Note: normalize_hourly_prices() doesn't exist anymore!
```

## Functions Renamed (No Aliases)

### timezone/timezone_converter.py
- ❌ Removed: `normalize_hourly_prices()`
- ✅ Exists: `normalize_interval_prices()`

### timezone/service.py
- ❌ Removed: `get_current_hour_key()`
- ✅ Exists: `get_current_interval_key()`
- ❌ Removed: `get_next_hour_key()`
- ✅ Exists: `get_next_interval_key()`

### utils/timezone_converter.py
- ❌ Removed: `normalize_hourly_prices()`
- ✅ Exists: `normalize_interval_prices()`

## Tests Updated

All test functions and calls have been updated to use new names:

### Test Function Names
- `test_normalize_hourly_prices_basic` → `test_normalize_interval_prices_basic`
- `test_normalize_hourly_prices_dst_fallback` → `test_normalize_interval_prices_dst_fallback`
- `test_normalize_hourly_prices_dst_springforward` → `test_normalize_interval_prices_dst_springforward`
- `test_normalize_hourly_prices_midnight_cross` → `test_normalize_interval_prices_midnight_cross`
- `test_get_current_hour_key_ha_mode` → `test_get_current_interval_key_ha_mode`
- `test_get_current_hour_key_area_mode` → `test_get_current_interval_key_area_mode`
- `test_get_current_hour_key_dst_fallback_second` → `test_get_current_interval_key_dst_fallback_second`
- `test_get_next_hour_key_normal` → `test_get_next_interval_key_normal`
- `test_get_next_hour_key_dst_springforward` → `test_get_next_interval_key_dst_springforward`
- `test_get_next_hour_key_dst_fallback_first` → `test_get_next_interval_key_dst_fallback_first`

### Test Calls
- `.normalize_hourly_prices()` → `.normalize_interval_prices()`
- `.get_current_hour_key()` → `.get_current_interval_key()`
- `.get_next_hour_key()` → `.get_next_interval_key()`
- `mock_tz_converter.normalize_hourly_prices` → `mock_tz_converter.normalize_interval_prices`
- `mock_tz_service.get_current_hour_key` → `mock_tz_service.get_current_interval_key`

## Benefits

1. **Cleaner Code**: No duplicate function names or aliases
2. **Less Confusion**: Only one way to call each function
3. **Easier Maintenance**: No need to maintain multiple function signatures
4. **Clear Migration**: Forces complete migration, no half-done states
5. **Better Documentation**: Code is self-documenting with correct names

## Migration Complete

All phases 1-8 have been updated with this policy:
- ✅ Phase 1: Core Constants & Time Handling
- ✅ Phase 2: Time Calculator Refactoring  
- ✅ Phase 3: Data Structures
- ✅ Phase 4: API Base & Expansion
- ✅ Phase 5: Parser Updates
- ✅ Phase 6: API Implementations
- ✅ Phase 7: Coordinator & Processing
- ✅ Phase 8: Sensors

**No backward compatibility functions exist in the codebase.**

## Verification

Run these commands to verify no old names exist:

```bash
# Should return ZERO matches in production code:
grep -r "normalize_hourly_prices" custom_components/ge_spot/
grep -r "get_current_hour_key" custom_components/ge_spot/
grep -r "get_next_hour_key" custom_components/ge_spot/
grep -r "HourlyPrice" custom_components/ge_spot/
grep -r "HourCalculator" custom_components/ge_spot/

# Tests should only use new names:
grep -r "normalize_interval_prices" tests/
grep -r "get_current_interval_key" tests/
grep -r "get_next_interval_key" tests/
```

## Documentation Updated

- `planning_docs/IMPLEMENTATION_INSTRUCTIONS.md` - Added Rule 7: No Backward Compatibility
- All code comments updated to use interval terminology
- All docstrings updated to use interval terminology
- All test documentation updated

---

**Status:** ✅ Complete  
**Policy Applied:** 100% of phases 1-8  
**Backward Compatibility Functions:** 0 (None exist)
