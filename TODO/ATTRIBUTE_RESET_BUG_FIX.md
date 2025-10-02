# Attribute Reset Bug - Root Cause Analysis and Fix Plan

**Date:** October 2, 2025  
**Issue:** Home Assistant attributes reset/reload every ~10 seconds  
**Severity:** High - Affects user experience  
**Status:** Identified, Fix Plan Created

---

## 🔍 Root Cause Analysis

### The Problem

Home Assistant attributes appear to "reset to the top" (similar to a reload) approximately every 10 seconds. This creates a poor user experience as users cannot review stable attribute data in the UI.

### The Root Cause

The issue is caused by **direct mutation of cached data dictionaries** combined with **shallow copying** in the cache retrieval mechanism. This creates a cascading effect where:

1. Cached data is retrieved as a reference (or shallow copy)
2. The code directly modifies this cached data
3. The modified data is then processed again
4. Each processing cycle changes the data object
5. Home Assistant's DataUpdateCoordinator detects changes and notifies all sensors
6. Sensors call `async_write_ha_state()` which regenerates all attributes
7. The UI refreshes, appearing to "reset"

### Technical Details

#### Issue #1: Direct Mutation of Cached Data

**Location 1:** `custom_components/ge_spot/coordinator/unified_price_manager.py` (around line 241)

```python
if cached_data_for_decision:
    _LOGGER.debug("Returning data based on initial cache check for decision making for %s", self.area)
    # Ensure the cached data is marked correctly if it's used
    cached_data_for_decision["using_cached_data"] = True  # ⚠️ PROBLEM: Mutating cached data directly!
    # Re-process if it wasn't fully processed or to update timestamps
    return await self._process_result(cached_data_for_decision, is_cached=True)
```

**Location 2:** `custom_components/ge_spot/coordinator/unified_price_manager.py` (around line 272)

```python
if cached_data_rate_limited:
    _LOGGER.debug("Returning rate-limited cached data for %s (after decision check)", self.area)
    cached_data_rate_limited["using_cached_data"] = True  # ⚠️ PROBLEM: Mutating cached data!
    cached_data_rate_limited["next_fetch_allowed_in_seconds"] = round(next_fetch_allowed_in_seconds, 1)  # ⚠️ PROBLEM!
    return await self._process_result(cached_data_rate_limited, is_cached=True)
```

**Why this is problematic:**
- `_cache_manager.get_data()` returns a reference to the cached dictionary
- Modifications to `cached_data_for_decision` **directly modify the cache**
- Subsequent retrievals get the already-modified (and possibly corrupted) data
- Each processing cycle adds/modifies metadata, creating instability

#### Issue #2: Shallow Copy in Cache Retrieval

**Location:** `custom_components/ge_spot/coordinator/cache_manager.py` (around line 189)

```python
data_copy = dict(entry_data)  # ⚠️ PROBLEM: Shallow copy only!
```

**Why this is problematic:**
- `dict()` creates a shallow copy
- Nested dictionaries (like `statistics`, `interval_prices`, etc.) remain as **references**
- Modifying nested structures still affects the cached data
- Example: `cached_data["statistics"]["complete_data"] = True` modifies the original cache

#### Issue #3: Repeated Processing with Timestamp Updates

**Location:** `custom_components/ge_spot/coordinator/unified_price_manager.py` (around line 461)

```python
processed_data = await self._data_processor.process(result)
processed_data["has_data"] = bool(processed_data.get("interval_prices"))
processed_data["last_update"] = dt_util.now().isoformat()  # ⚠️ Changes every call!
```

**Why this is problematic:**
- Even if the actual price data hasn't changed, `last_update` changes every time
- The coordinator sees this as a "data change" and notifies all listeners
- Sensors regenerate attributes and the UI refreshes

#### Issue #4: Coordinator Listener Mechanism

**Location:** `custom_components/ge_spot/sensor/base.py` (line 237)

```python
async def async_added_to_hass(self):
    """When entity is added to hass."""
    self.async_on_remove(
        self.coordinator.async_add_listener(self.async_write_ha_state)
    )
```

**Why this triggers frequently:**
- Every time `coordinator.data` is reassigned (even to the same modified object), listeners are notified
- Each sensor calls `async_write_ha_state()`
- Home Assistant regenerates the entity state and attributes
- UI receives update and re-renders the attribute display

---

## 📋 Impact Assessment

## 📋 Impact Assessment

### Symptoms
- ✅ Attributes "jump to top" or appear to reload at **random intervals (6-15 seconds)**
- ✅ **Variable timing** indicates multiple async processes triggering updates
- ✅ User cannot read long attribute lists without interruption
- ✅ Cache data may become corrupted with duplicate or stale metadata
- ✅ Excessive state updates create unnecessary overhead
- ✅ **Feedback loop**: Cache mutation → Update → Sensor refresh → Cache access → Mutation → Repeat

### Affected Components
1. **CacheManager** - Returns mutable references instead of copies
2. **UnifiedPriceManager** - Mutates cached data directly
3. **DataProcessor** - May be called repeatedly on same data
4. **Sensors** - Receive unnecessary update notifications
5. **Home Assistant UI** - Refreshes attributes too frequently

### Data Flow

```
┌─────────────────┐
│  Coordinator    │
│  Update Timer   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│ fetch_data()            │
│ - Check cache           │◄────┐
│ - Get cached_data       │     │ Reference to
└────────┬────────────────┘     │ same object
         │                      │
         ▼                      │
┌─────────────────────────┐     │
│ Mutate cached_data      │─────┘ Modifies cache!
│ - using_cached_data=True│
│ - timestamps updated    │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ _process_result()       │
│ - Adds more metadata    │
│ - Updates timestamps    │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ coordinator.data = X    │ ◄── Object changed!
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Notify all listeners    │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Sensors update state    │
│ - Regenerate attributes │
│ - Call async_write...   │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Home Assistant UI       │
│ - Refresh display       │
│ - Attributes "reset"    │
└─────────────────────────┘
```

---

## 🔧 Fix Plan

### Fix #1: Deep Copy in Cache Retrieval (HIGH PRIORITY)

**File:** `custom_components/ge_spot/coordinator/cache_manager.py`

**Change:**
```python
# Before (shallow copy)
data_copy = dict(entry_data)

# After (deep copy)
import copy
data_copy = copy.deepcopy(entry_data)
```

**Benefit:**
- Ensures retrieved cache data is completely independent
- Prevents any modifications from affecting the original cache
- Protects nested dictionaries from mutation

### Fix #2: Never Mutate Retrieved Cache Data (HIGH PRIORITY)

**File:** `custom_components/ge_spot/coordinator/unified_price_manager.py`

**Change Location 1 (line ~241):**
```python
# Before
if cached_data_for_decision:
    cached_data_for_decision["using_cached_data"] = True
    return await self._process_result(cached_data_for_decision, is_cached=True)

# After
if cached_data_for_decision:
    # Work on a copy, not the cached data directly
    data_copy = copy.deepcopy(cached_data_for_decision)
    data_copy["using_cached_data"] = True
    return await self._process_result(data_copy, is_cached=True)
```

**Change Location 2 (line ~272):**
```python
# Before
if cached_data_rate_limited:
    cached_data_rate_limited["using_cached_data"] = True
    cached_data_rate_limited["next_fetch_allowed_in_seconds"] = round(next_fetch_allowed_in_seconds, 1)
    return await self._process_result(cached_data_rate_limited, is_cached=True)

# After
if cached_data_rate_limited:
    # Work on a copy, not the cached data directly
    data_copy = copy.deepcopy(cached_data_rate_limited)
    data_copy["using_cached_data"] = True
    data_copy["next_fetch_allowed_in_seconds"] = round(next_fetch_allowed_in_seconds, 1)
    return await self._process_result(data_copy, is_cached=True)
```

### Fix #3: Defensive Copying in _process_result (MEDIUM PRIORITY)

**File:** `custom_components/ge_spot/coordinator/unified_price_manager.py`

**Change (around line 440):**
```python
async def _process_result(self, result: Dict[str, Any], is_cached: bool = False) -> Dict[str, Any]:
    """Process raw result data (either fresh or cached)."""
    
    # ADDED: Work on a copy to prevent side effects
    result = copy.deepcopy(result)
    
    # Ensure exchange service is initialized before processing
    await self._ensure_exchange_service()
    # ... rest of method
```

### Fix #4: Add Data Change Detection (OPTIONAL - PERFORMANCE)

**File:** `custom_components/ge_spot/coordinator/unified_price_manager.py`

**Concept:**
```python
async def _async_update_data(self):
    """Fetch data from price manager."""
    try:
        data = await self.price_manager.fetch_data()
        
        # ADDED: Only return if data actually changed
        if self._has_data_changed(data):
            return data
        else:
            _LOGGER.debug("Data unchanged, skipping update notification")
            raise UpdateFailed("Data unchanged")  # Prevents listener notification
    except Exception as e:
        # ... error handling

def _has_data_changed(self, new_data: Dict[str, Any]) -> bool:
    """Check if data has meaningfully changed."""
    if not self.data:
        return True
    
    # Compare critical fields only (exclude timestamps)
    critical_fields = ["interval_prices", "tomorrow_interval_prices", "current_price", "data_source"]
    for field in critical_fields:
        if self.data.get(field) != new_data.get(field):
            return True
    
    return False
```

### Fix #5: Update Timestamps Only on Real Data Changes (OPTIONAL)

**File:** `custom_components/ge_spot/coordinator/unified_price_manager.py`

**Concept:**
```python
# Only update last_update when actual price data changes
if not is_cached or self._should_update_timestamp(processed_data):
    processed_data["last_update"] = dt_util.now().isoformat()
```

---

## 🎯 Implementation Priority

### Phase 1: Critical Fixes (Implement Immediately)
1. ✅ **Fix #1**: Add deep copy to `cache_manager.py`
2. ✅ **Fix #2**: Remove direct mutations in `unified_price_manager.py`

**Expected Result:** Attributes stop resetting, cache integrity maintained

### Phase 2: Defensive Programming (Implement Soon)
3. ⚠️ **Fix #3**: Add defensive copying in `_process_result()`

**Expected Result:** Additional safety layer, prevents future mutation bugs

### Phase 3: Performance Optimization (Optional - Future)
4. 🔄 **Fix #4**: Add data change detection
5. 🔄 **Fix #5**: Smart timestamp updates

**Expected Result:** Reduced unnecessary updates, better performance

---

## 🧪 Testing Plan

### Manual Testing
1. **Before Fix:**
   - Open Home Assistant Developer Tools > States
   - Navigate to a GE-Spot sensor entity
   - Observe attributes section
   - Confirm attributes "jump to top" every ~10 seconds

2. **After Fix:**
   - Repeat above steps
   - Attributes should remain stable
   - Scroll position should not reset
   - Values should update only when data actually changes

### Automated Testing
```python
# Test cache isolation
def test_cache_returns_independent_copies():
    """Ensure cache.get_data() returns independent copies."""
    cache = CacheManager(area="SE3")
    
    # Store data
    original = {"price": 100, "nested": {"value": 50}}
    cache.store(area="SE3", source="test", data=original)
    
    # Retrieve and modify
    retrieved1 = cache.get_data(area="SE3")
    retrieved1["price"] = 200
    retrieved1["nested"]["value"] = 75
    
    # Retrieve again - should be unchanged
    retrieved2 = cache.get_data(area="SE3")
    assert retrieved2["price"] == 100
    assert retrieved2["nested"]["value"] == 50
```

### Verification Checklist
- [ ] Attributes no longer reset in UI
- [ ] Cache data remains consistent across retrievals
- [ ] No performance degradation
- [ ] Logs show fewer unnecessary updates
- [ ] Memory usage remains acceptable (deep copy overhead)

---

## 📊 Expected Impact

### Positive Outcomes
- ✅ Stable attribute display in Home Assistant UI
- ✅ Reduced unnecessary state updates
- ✅ Protected cache integrity
- ✅ Better code safety and maintainability
- ✅ Reduced CPU/memory overhead from excessive updates

### Potential Concerns
- ⚠️ Deep copy has memory overhead (minimal for this use case)
- ⚠️ Deep copy takes more CPU time (microseconds, negligible)
- ℹ️ Performance impact is **acceptable** given the fix benefits

### Performance Analysis
```
Cache retrieval: ~1-5 times per minute (rate limited)
Deep copy overhead: ~1-5ms per operation
Total added overhead: ~5-25ms per minute
Impact: Negligible (<0.1% CPU time)
```

---

## 🚀 Implementation Notes

### Code Review Checklist
- [ ] All cache retrievals use deep copy
- [ ] No direct mutations of cached data
- [ ] Defensive copying in processing methods
- [ ] Proper error handling maintained
- [ ] Logging statements preserved
- [ ] Comments explain the copy operations

### Rollback Plan
If issues arise:
1. Revert the deepcopy changes
2. Add shallow copy back temporarily
3. Investigate specific edge cases
4. Apply targeted fixes

---

## 📝 Conclusion

This bug is caused by **violating the principle of immutability** for cached data. The fix is straightforward:

1. **Never mutate cached data directly**
2. **Always work on copies**
3. **Use deep copy to protect nested structures**

The fixes are low-risk, high-benefit changes that will significantly improve user experience with minimal performance impact.

**Next Step:** Implement Phase 1 fixes immediately.
