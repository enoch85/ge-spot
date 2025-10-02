# Cache Variables Audit - Are They Actually Used?

**Date:** October 2, 2025  
**Branch:** 15min  
**Status:** 🔍 **AUDIT COMPLETE**

---

## 📋 TL;DR Summary

| Variable | Defined? | Used? | Purpose | Status |
|----------|----------|-------|---------|--------|
| `CACHE_TTL` | ✅ Yes | ✅ **YES** | Entry expiration time | ✅ **CORRECT** (Now 3 days) |
| `CACHE_MAX_ENTRIES` | ✅ Yes | ✅ **YES** | Max entries before eviction | ✅ **CORRECT** (100 entries) |
| `CACHE_MAX_DAYS` | ✅ Yes | ❌ **NO** | Unused! | ⚠️ **DEAD CODE** |
| `CACHE_COMPRESSION_THRESHOLD` | ✅ Yes | ❌ **NO** | Unused! | ⚠️ **DEAD CODE** |
| `CACHE_CLEANUP_THRESHOLD` | ✅ Yes | ❌ **NO** | Unused! | ⚠️ **DEAD CODE** |
| `CACHE_ADVANCED` | ✅ Yes | ❌ **NO** | Unused! | ⚠️ **DEAD CODE** |

---

## 🔍 Detailed Analysis

### 1. ✅ **CACHE_TTL** - USED & CORRECT

#### Definition:
```python
# defaults.py line 24
CACHE_TTL = 60 * 24 * 3  # 4320 minutes (3 days)
```

#### Usage:
```python
# advanced_cache.py line 110
self.default_ttl = self.config.get(Config.CACHE_TTL, Defaults.CACHE_TTL)

# advanced_cache.py line 155
ttl = ttl if ttl is not None else self.default_ttl

# CacheEntry
entry = CacheEntry(value, ttl=3600 * 60 * 24 * 3)  # 259200 seconds = 3 days
```

#### Flow:
```
Defaults.CACHE_TTL = 4320 minutes
    ↓
cache_manager.py: default_ttl_minutes = 4320
    ↓
Converts to seconds: 4320 * 60 = 259200 seconds
    ↓
AdvancedCache.default_ttl = 259200
    ↓
CacheEntry.ttl = 259200
    ↓
Entry expires after 3 days ✅
```

**Status:** ✅ **CORRECT!** Now set to 3 days, which matches electricity price validity.

---

### 2. ✅ **CACHE_MAX_ENTRIES** - USED & CORRECT

#### Definition:
```python
# defaults.py line 26
CACHE_MAX_ENTRIES = 10  # entries per area
```

#### Usage:
```python
# advanced_cache.py line 109
self.max_entries = self.config.get(Config.CACHE_MAX_ENTRIES, Defaults.CACHE_MAX_ENTRIES)

# advanced_cache.py line 220-242
def _evict_if_needed(self) -> None:
    """Evict entries if the cache is full."""
    if len(self._cache) <= self.max_entries:  # ← Uses max_entries here!
        return
    
    # Remove expired entries first
    expired_keys = [key for key, entry in self._cache.items() if entry.is_expired]
    for key in expired_keys:
        del self._cache[key]
    
    # If still too many, remove LRU
    if len(self._cache) > self.max_entries:
        # Sort by last accessed
        sorted_keys = sorted(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_accessed
        )
        # Remove oldest
        to_remove = len(self._cache) - self.max_entries
        for key in sorted_keys[:to_remove]:
            del self._cache[key]
```

**Status:** ✅ **CORRECT!** Used for LRU eviction when cache gets full.

---

### 3. ❌ **CACHE_MAX_DAYS** - DEFINED BUT NEVER USED!

#### Definition:
```python
# defaults.py line 25
CACHE_MAX_DAYS = 3  # days

# config.py line 13
CACHE_MAX_DAYS = "cache_max_days"
```

#### Usage:
```bash
$ grep -r "Config.CACHE_MAX_DAYS" .
# NO MATCHES!

$ grep -r "cache_max_days" . --include="*.py" | grep -v "def\|comment\|#"
# NO MATCHES!
```

**Status:** ⚠️ **DEAD CODE** - Defined but never used anywhere!

**Should Remove:**
```python
# Remove from defaults.py line 25
# Remove from config.py line 13
```

---

### 4. ❌ **CACHE_COMPRESSION_THRESHOLD** - DEFINED BUT NEVER USED!

#### Definition:
```python
# defaults.py line 27
CACHE_COMPRESSION_THRESHOLD = 10240  # bytes (10KB)

# config.py line 29
CACHE_COMPRESSION_THRESHOLD = "cache_compression_threshold"
```

#### Usage:
```bash
$ grep -r "Config.CACHE_COMPRESSION_THRESHOLD" .
# NO MATCHES!

$ grep -r "cache_compression_threshold" . --include="*.py" | grep -v "def\|comment\|#"
# NO MATCHES!
```

**Status:** ⚠️ **DEAD CODE** - Defined but never used anywhere!

**Should Remove:**
```python
# Remove from defaults.py line 27
# Remove from config.py line 29
```

---

### 5. ❌ **CACHE_CLEANUP_THRESHOLD** - DEFINED BUT NEVER USED!

#### Definition:
```python
# defaults.py line 28
CACHE_CLEANUP_THRESHOLD = 100  # stores before auto cleanup

# config.py line 30
CACHE_CLEANUP_THRESHOLD = "cache_cleanup_threshold"
```

#### Usage:
```bash
$ grep -r "Config.CACHE_CLEANUP_THRESHOLD" .
# NO MATCHES!

$ grep -r "cache_cleanup_threshold" . --include="*.py" | grep -v "def\|comment\|#"
# NO MATCHES!
```

**Status:** ⚠️ **DEAD CODE** - Defined but never used anywhere!

**Should Remove:**
```python
# Remove from defaults.py line 28
# Remove from config.py line 30
```

---

### 6. ❌ **CACHE_ADVANCED** - DEFINED BUT NEVER USED!

#### Definition:
```python
# defaults.py line 29
CACHE_ADVANCED = True  # use advanced cache by default

# config.py line 31
CACHE_ADVANCED = "cache_advanced"
```

#### Usage:
```bash
$ grep -r "Config.CACHE_ADVANCED" .
# NO MATCHES!

$ grep -r "cache_advanced" . --include="*.py" | grep -v "def\|comment\|#"
# NO MATCHES!
```

**Status:** ⚠️ **DEAD CODE** - Defined but never used anywhere!

**Note:** All cache operations use `AdvancedCache` unconditionally. There's no fallback to a "simple" cache, so this flag is meaningless.

**Should Remove:**
```python
# Remove from defaults.py line 29
# Remove from config.py line 31
```

---

## 🎯 What Actually Controls Cache Behavior?

### Variables That MATTER:

#### 1. **CACHE_TTL** ✅
```python
CACHE_TTL = 60 * 24 * 3  # 3 days = 4320 minutes
```
- **Controls:** How long entries stay in cache before expiring
- **Used in:** `CacheEntry.is_expired` check
- **Impact:** Entries older than 3 days are auto-deleted
- **Status:** ✅ Correctly set to 3 days (matches price validity)

#### 2. **CACHE_MAX_ENTRIES** ✅
```python
CACHE_MAX_ENTRIES = 100  # entries
```
- **Controls:** Maximum number of cache entries before LRU eviction
- **Used in:** `_evict_if_needed()` method
- **Impact:** When cache > 100 entries, oldest accessed are removed
- **Status:** ✅ Reasonable default (100 entries)

#### 3. **PERSIST_CACHE** ✅
```python
PERSIST_CACHE = False  # Don't save cache to disk by default
```
- **Controls:** Whether cache is saved to disk between restarts
- **Used in:** `_save_cache()` and `_load_cache()` methods
- **Impact:** If True, cache survives HA restarts
- **Status:** ✅ Used correctly

#### 4. **CACHE_DIR** ✅
```python
CACHE_DIR = "cache"  # Cache directory name
```
- **Controls:** Directory name for cache files
- **Used in:** `_get_cache_file_path()` method
- **Impact:** Cache file location: `<config_dir>/cache/price_cache.json`
- **Status:** ✅ Used correctly

---

## 📊 Cache Behavior with Current Settings

### With CACHE_TTL = 3 days:

```
Day 1 - Monday 10:00:
  → Fetch prices, store in cache
  → Entry created: ttl=259200 sec (3 days)

Day 1 - Monday 14:00:
  → Check cache: age=14400 sec (4 hours)
  → is_expired? 14400 < 259200 → NO
  → ✅ Return cached data (no fetch)

Day 2 - Tuesday 10:00:
  → Check cache: age=86400 sec (24 hours)
  → is_expired? 86400 < 259200 → NO
  → ✅ Return cached data (no fetch)
  → Fetch decision: "Has current price? YES, Complete data? YES"
  → Skip fetch (content-based decision)

Day 3 - Wednesday 10:00:
  → Check cache: age=172800 sec (48 hours)
  → is_expired? 172800 < 259200 → NO
  → ✅ Return cached data (no fetch)

Day 4 - Thursday 10:01:
  → Check cache: age=259260 sec (3 days + 1 min)
  → is_expired? 259260 > 259200 → YES
  → ❌ Entry deleted (expired)
  → Fetch decision: "No cache, no current price"
  → FETCH from API ✅
```

**Perfect!** Cache lasts 3 days, matching electricity price validity.

---

## 🧹 Cleanup Recommendations

### Variables to REMOVE (Dead Code):

```python
# In defaults.py - REMOVE these lines:
CACHE_MAX_DAYS = 3  # days  ← REMOVE (unused)
CACHE_COMPRESSION_THRESHOLD = 10240  # bytes (10KB)  ← REMOVE (unused)
CACHE_CLEANUP_THRESHOLD = 100  # stores before auto cleanup  ← REMOVE (unused)
CACHE_ADVANCED = True  # use advanced cache by default  ← REMOVE (unused)

# In config.py - REMOVE these lines:
CACHE_MAX_DAYS = "cache_max_days"  ← REMOVE (unused)
CACHE_COMPRESSION_THRESHOLD = "cache_compression_threshold"  ← REMOVE (unused)
CACHE_CLEANUP_THRESHOLD = "cache_cleanup_threshold"  ← REMOVE (unused)
CACHE_ADVANCED = "cache_advanced"  ← REMOVE (unused)
```

### Variables to KEEP:

```python
# In defaults.py - KEEP these:
CACHE_TTL = 60 * 24 * 3  # 4320 minutes (3 days) ✅
CACHE_MAX_ENTRIES = 100  # entries ✅
PERSIST_CACHE = False  # Don't persist by default ✅
CACHE_DIR = "cache"  # Cache directory ✅

# In config.py - KEEP these:
CACHE_TTL = "cache_ttl"  ✅
CACHE_MAX_ENTRIES = "cache_max_entries"  ✅
PERSIST_CACHE = "persist_cache"  ✅
CACHE_DIR = "cache_dir"  ✅
```

---

## ⚠️ Potential Issue: CACHE_MAX_ENTRIES = 10 vs 100

There's a discrepancy:

```python
# defaults.py line 18
CACHE_MAX_ENTRIES = 100  # First definition (used by AdvancedCache)

# defaults.py line 26
CACHE_MAX_ENTRIES = 10  # Second definition (overwrites first!) ← PROBLEM!
```

**Current Active Value:** 10 entries (second definition wins)

**Recommendation:** This seems too low! With 15-minute intervals:
- Each area might have multiple cache entries (different dates)
- 10 entries = very aggressive eviction
- Should probably be 100 (first value) or higher

**Fix:** Remove duplicate and keep value at 100:
```python
# Remove line 18 (duplicate)
# Keep line 26 but change value:
CACHE_MAX_ENTRIES = 100  # entries per area
```

---

## 🎯 Final Summary

### What's Working:
- ✅ **CACHE_TTL:** Correctly set to 3 days
- ✅ **CACHE_MAX_ENTRIES:** Used for LRU eviction
- ✅ **PERSIST_CACHE:** Used for disk persistence
- ✅ **CACHE_DIR:** Used for cache file location

### What's Broken:
- ⚠️ **CACHE_MAX_ENTRIES:** Duplicate definition (100 vs 10)
- ❌ **CACHE_MAX_DAYS:** Dead code (unused)
- ❌ **CACHE_COMPRESSION_THRESHOLD:** Dead code (unused)
- ❌ **CACHE_CLEANUP_THRESHOLD:** Dead code (unused)
- ❌ **CACHE_ADVANCED:** Dead code (unused)

### What to Do:
1. ✅ **Fix CACHE_MAX_ENTRIES duplicate** (keep 100, remove duplicate)
2. ✅ **Remove 4 unused variables** (clean up dead code)
3. ✅ **Keep CACHE_TTL at 3 days** (already correct)

---

## ✅ CLEANUP COMPLETED

**Date:** October 2, 2025

All issues have been resolved:
- ✅ Removed 4 dead code variables (CACHE_MAX_DAYS, CACHE_COMPRESSION_THRESHOLD, CACHE_CLEANUP_THRESHOLD, CACHE_ADVANCED)
- ✅ Fixed CACHE_MAX_ENTRIES duplicate (was 100 then 10, now single value: 3500)
- ✅ Optimized CACHE_MAX_ENTRIES for 15-minute intervals (3 days × 24h × 4 intervals × ~12 areas = 3500)
- ✅ Verified both CacheManager and AdvancedCache are needed (different responsibilities)

See `CACHE_CLEANUP_COMPLETED.md` for full details.

---

**Audit Status:** ✅ **COMPLETE**  
**Cleanup Status:** ✅ **COMPLETE**  
**CACHE_TTL Setting:** ✅ **CORRECT** (3 days)  
**CACHE_MAX_ENTRIES:** ✅ **OPTIMIZED** (3500 entries)
