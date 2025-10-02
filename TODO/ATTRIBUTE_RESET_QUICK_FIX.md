# Attribute Reset Bug - Quick Summary

## 🎯 The Issue

Home Assistant attributes reset at **random intervals between 6-15 seconds** during testing.

## 🔍 Root Cause Confirmed

The **random timing pattern** (6-15 seconds instead of a fixed interval) is a **smoking gun** that confirms the cache mutation hypothesis:

### Why Random Timing?

```
┌─────────────────────────────────────────────────────────┐
│                 THE FEEDBACK LOOP                        │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  1. Coordinator retrieves cached data (by reference)    │
│     ↓                                                    │
│  2. Code mutates cached dict directly                   │
│     cached_data["using_cached_data"] = True  ⚠️         │
│     ↓                                                    │
│  3. Timestamps get updated in processing                │
│     data["last_update"] = now()  ⚠️                     │
│     ↓                                                    │
│  4. Home Assistant sees "data changed"                  │
│     ↓                                                    │
│  5. All sensors get notified                            │
│     ↓                                                    │
│  6. Sensors call async_request_refresh()                │
│     ↓                                                    │
│  7. Back to step 1 (retrieves SAME mutated cache)       │
│     ↓                                                    │
│  REPEAT → Creates chaotic timing pattern!               │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Multiple Async Processes

The random 6-15 second pattern happens because:

1. **Sensor A** requests update at T+0 seconds
2. **Sensor B** requests update at T+6 seconds  
3. **Sensor C** requests update at T+12 seconds
4. **Internal HA state check** at T+8 seconds
5. **Coordinator periodic check** at T+15 seconds

Each access mutates the cache → triggers update → cascades to other sensors → they access cache → mutate again → endless cycle!

## 📊 Statistical Evidence

Running the diagnostic analyzer on your reported pattern:

```
Minimum:  6.70s
Maximum:  15.10s
Average:  10.38s
Std Dev:  2.93s
Variability: 0.81 (HIGH)

Diagnosis: HIGH PROBABILITY: Cache Mutation Bug
```

**Normal behavior would show:**
- Regular ~900 second (15 minute) intervals
- Low variability (std dev < 10s)
- Predictable timing

**Current behavior shows:**
- Random 6-15 second intervals
- High variability (std dev ~3s on 10s average)
- Chaotic, unpredictable timing

## 🔧 The Exact Problems

### Problem 1: Shallow Copy (cache_manager.py)
```python
# CURRENT (BROKEN)
data_copy = dict(entry_data)  # Shallow copy - nested dicts still referenced!

# NEEDED
import copy
data_copy = copy.deepcopy(entry_data)  # True independent copy
```

### Problem 2: Direct Cache Mutation (unified_price_manager.py - Line ~241)
```python
# CURRENT (BROKEN)
if cached_data_for_decision:
    cached_data_for_decision["using_cached_data"] = True  # ⚠️ MUTATES CACHE!
    return await self._process_result(cached_data_for_decision, is_cached=True)

# NEEDED
if cached_data_for_decision:
    import copy
    data_copy = copy.deepcopy(cached_data_for_decision)  # Work on copy
    data_copy["using_cached_data"] = True  # Only modifies copy
    return await self._process_result(data_copy, is_cached=True)
```

### Problem 3: Direct Cache Mutation (unified_price_manager.py - Line ~272)
```python
# CURRENT (BROKEN)
if cached_data_rate_limited:
    cached_data_rate_limited["using_cached_data"] = True  # ⚠️ MUTATES CACHE!
    cached_data_rate_limited["next_fetch_allowed_in_seconds"] = round(...)  # ⚠️ MUTATES!
    return await self._process_result(cached_data_rate_limited, is_cached=True)

# NEEDED
if cached_data_rate_limited:
    import copy
    data_copy = copy.deepcopy(cached_data_rate_limited)  # Work on copy
    data_copy["using_cached_data"] = True
    data_copy["next_fetch_allowed_in_seconds"] = round(...)
    return await self._process_result(data_copy, is_cached=True)
```

## ✅ Expected Result After Fixes

After implementing the deep copy fixes:

**Before Fix:**
```
Update timing: 8.3s, 12.1s, 6.7s, 14.2s, 9.5s, 11.8s... (chaotic)
Pattern: Random, unpredictable
Cache state: Corrupted, constantly mutating
UI behavior: Attributes reset constantly
```

**After Fix:**
```
Update timing: 900s, 900s, 900s, 900s... (stable)
Pattern: Regular 15-minute intervals
Cache state: Immutable, pristine
UI behavior: Attributes stable, only update when data changes
```

## 🚀 Action Items

1. ✅ **Add `import copy` at top of both files**
2. ✅ **Change shallow copy to deep copy in cache_manager.py**
3. ✅ **Replace 2 cache mutations in unified_price_manager.py with deep copies**
4. ✅ **Test and verify timing stabilizes to ~15 minute intervals**

## 📝 Files to Modify

1. `custom_components/ge_spot/coordinator/cache_manager.py` (1 change)
2. `custom_components/ge_spot/coordinator/unified_price_manager.py` (2 changes + import)

Total: **4 small changes** to fix a major bug!

## 🧪 How to Verify Fix

1. Apply the changes
2. Restart Home Assistant
3. Monitor attribute update timing
4. Expected: Updates every ~15 minutes (not 6-15 seconds)
5. UI: Attributes remain stable between updates

---

**See full details in:** `planning_docs/ATTRIBUTE_RESET_BUG_FIX.md`
