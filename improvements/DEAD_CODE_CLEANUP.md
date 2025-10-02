# Dead Code Cleanup - Post Data Validity Architecture

## Dead Code Identified

After implementing the Data Validity Architecture, the following code is no longer used:

### 1. ❌ `has_current_hour_price()` method in `cache_manager.py`
- **Status**: Dead code - not called anywhere
- **Reason**: Replaced by `DataValidity.has_current_interval`
- **Action**: Remove

### 2. ❌ `get_current_hour_price()` method in `cache_manager.py`  
- **Status**: Dead code - only called by `has_current_hour_price()`
- **Reason**: Fetch decision now uses DataValidity, not individual price checks
- **Action**: Remove

### 3. ⚠️ `complete_data` field in `PriceStatistics`
- **Status**: Legacy field - still set but not used for fetch decisions
- **Reason**: Replaced by DataValidity timestamps
- **Current usage**: 
  - Still calculated in `data_processor.py`
  - Serialized to sensor attributes
  - Visible in Home Assistant UI
- **Action**: Keep for now, document as deprecated

## Decision Rationale

### Safe to Remove (Dead Code)
The two cache methods are completely unused:
- No callers in application code
- No usage in tests
- Replaced by DataValidity architecture
- **Remove immediately** ✅

### Keep for Now (Legacy but Visible)
The `complete_data` field should be kept temporarily because:
- It's part of the serialized statistics dict
- Users might have automations reading sensor attributes
- It's in the data structure API
- Breaking change for users who expose sensor data to other systems

**Migration path:**
1. ✅ Phase 1 (current): Keep field, set it, but don't use for fetch logic
2. 🔄 Phase 2 (future): Mark as deprecated in documentation
3. 🔄 Phase 3 (v2.0): Remove field (breaking change)

## Cleanup Actions

### Immediate (This Commit)
- [x] Remove `has_current_hour_price()` from `cache_manager.py`
- [x] Remove `get_current_hour_price()` from `cache_manager.py`
- [x] Add deprecation comment to `complete_data` field

### Future (Next Version)
- [ ] Add deprecation warning log when `complete_data` is read
- [ ] Document `complete_data` as deprecated in README
- [ ] Add migration guide for users
- [ ] Add `data_valid_until` to sensor attributes (replacement)

### v2.0 (Breaking Change)
- [ ] Remove `complete_data` field completely
- [ ] Update all tests
- [ ] Update documentation

## Files Modified

1. `custom_components/ge_spot/coordinator/cache_manager.py`
   - Removed `get_current_hour_price()` method (lines 252-311)
   - Removed `has_current_hour_price()` method (lines 314-316)

2. `custom_components/ge_spot/api/base/data_structure.py`
   - Added deprecation comment to `complete_data` field

## Testing

- [x] Verified no callers exist for removed methods
- [x] Verified no tests use removed methods
- [x] Data validity tests pass
- [ ] Integration tests pass (run after commit)
- [ ] Manual test: sensor attributes still visible

## Related Issues

None - proactive cleanup after refactoring.
