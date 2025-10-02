# Cache TTL Usage in GE-Spot Codebase

**Date:** October 2, 2025  
**Branch:** 15min  
**Status:** ✅ Documented

---

## 📋 Overview

The `cache_ttl` (Time To Live) is used **internally** for cache memory management and cleanup, **NOT** for determining when to fetch data. After our changes, cache retrieval no longer uses age-based filtering.

---

## 🎯 Where cache_ttl is Used

### 1. **Configuration Definition** 📝

#### File: `custom_components/ge_spot/const/config.py`
```python
# Line 16
CACHE_TTL = "cache_ttl"  # Config key name (string constant)
```

**Purpose:** Defines the config key name for user-configurable cache TTL.

**Usage:** Used to look up cache_ttl value from configuration dict.

---

#### File: `custom_components/ge_spot/const/defaults.py`
```python
# Line 24
CACHE_TTL = 60  # minutes (used for internal cleanup/eviction only)
```

**Purpose:** Default value if user doesn't configure cache_ttl.

**Value:** 60 minutes (1 hour)

**Note:** This is for internal cache management, not retrieval filtering.

---

#### File: `custom_components/ge_spot/const/network.py`
```python
# Line 11
CACHE_TTL = 21600  # 6 hours in seconds
```

**Purpose:** Network-specific cache TTL (not currently used by main cache system).

**Value:** 21600 seconds (6 hours)

**Status:** ⚠️ Separate from main cache system, appears unused.

---

### 2. **Cache Manager Initialization** 🔧

#### File: `custom_components/ge_spot/coordinator/cache_manager.py`

**Lines 36-38:**
```python
def __init__(self, hass: HomeAssistant, config: Dict[str, Any]):
    # Use default TTL from Defaults if not in config
    default_ttl_minutes = config.get("cache_ttl", Defaults.CACHE_TTL)  # Gets 60 minutes
    # Pass TTL in seconds to AdvancedCache
    config_with_ttl_seconds = {**config, "cache_ttl": default_ttl_minutes * 60}  # Converts to 3600 seconds
    self._price_cache = AdvancedCache(hass, config_with_ttl_seconds)
```

**What This Does:**
1. Looks for `"cache_ttl"` in config dict
2. Falls back to `Defaults.CACHE_TTL` (60 minutes) if not found
3. Converts minutes to seconds (60 min × 60 = 3600 seconds)
4. Passes to AdvancedCache

**Purpose:** Initialize cache with TTL for internal memory management.

---

### 3. **AdvancedCache Class** 🗄️

#### File: `custom_components/ge_spot/utils/advanced_cache.py`

**Line 110 - Initialization:**
```python
def __init__(self, hass: Optional[HomeAssistant] = None, config: Optional[Dict[str, Any]] = None):
    self.hass = hass
    self.config = config or {}
    
    # Configuration
    self.max_entries = self.config.get(Config.CACHE_MAX_ENTRIES, Defaults.CACHE_MAX_ENTRIES)
    self.default_ttl = self.config.get(Config.CACHE_TTL, Defaults.CACHE_TTL)  # ← Gets cache_ttl value
    self.persist_cache = self.config.get(Config.PERSIST_CACHE, Defaults.PERSIST_CACHE)
    self.cache_dir = self.config.get(Config.CACHE_DIR, Defaults.CACHE_DIR)
    
    self._cache: Dict[str, CacheEntry] = {}
```

**What This Does:**
- Stores `cache_ttl` as `self.default_ttl`
- Used when creating new CacheEntry objects

---

**Lines 121-148 - get() method:**
```python
def get(self, key: str, default: Any = None) -> Any:
    """Get a value from the cache."""
    if key not in self._cache:
        return default

    entry = self._cache[key]

    # ✅ Check if expired (uses TTL from CacheEntry)
    if entry.is_expired:
        # Remove expired entry
        del self._cache[key]
        return default

    # Update access stats
    entry.access()
    
    return entry.data
```

**What This Does:**
- Checks if cache entry is expired using `entry.is_expired`
- If expired, deletes the entry and returns `None`
- If not expired, returns the data

**KEY POINT:** This is **internal cleanup** only. The calling code doesn't pass `max_age_minutes` anymore, so age filtering only happens here during retrieval (expired entries are removed).

---

**Lines 150-167 - set() method:**
```python
def set(self, key: str, value: Any, ttl: Optional[int] = None,
       metadata: Optional[Dict[str, Any]] = None) -> None:
    """Set a value in the cache."""
    # ✅ Use default TTL if not specified
    ttl = ttl if ttl is not None else self.default_ttl  # ← Uses cache_ttl here
    
    # Create cache entry with TTL
    entry = CacheEntry(value, ttl, metadata)
    
    # Add to cache
    self._cache[key] = entry
    
    # Check if we need to evict entries
    self._evict_if_needed()
    
    # Persist cache if enabled
    if self.persist_cache and self.hass:
        self._save_cache()
```

**What This Does:**
- When storing data, uses `self.default_ttl` (from cache_ttl config)
- Creates CacheEntry with this TTL
- Entry will expire after TTL seconds

---

### 4. **CacheEntry Class** 📦

#### File: `custom_components/ge_spot/utils/advanced_cache.py`

**Lines 19-45:**
```python
class CacheEntry:
    """Cache entry with TTL and metadata."""

    def __init__(self, data: Any, ttl: int = 3600, metadata: Optional[Dict[str, Any]] = None):
        """Initialize a cache entry.
        
        Args:
            ttl: Time to live in seconds
        """
        self.data = data
        self.created_at = datetime.now(timezone.utc)
        self.ttl = ttl  # ← Stores the TTL
        self.metadata = metadata or {}
        self.access_count = 0
        self.last_accessed = self.created_at

    @property
    def age(self) -> float:
        """Get the age of the cache entry in seconds."""
        return (datetime.now(timezone.utc) - self.created_at).total_seconds()

    @property
    def is_expired(self) -> bool:
        """Check if the cache entry is expired."""
        return self.age > self.ttl  # ← Compares age to TTL
```

**What This Does:**
- Each cache entry stores its own TTL
- `is_expired` property checks if `age > ttl`
- Used by `AdvancedCache.get()` to remove stale entries

---

## 🔄 Complete Flow

### Storing Data:

```
1. unified_price_manager.py calls:
   cache_manager.store(area, source, data, ...)

2. cache_manager.py:
   _price_cache.set(cache_key, data, metadata=...)
   
3. advanced_cache.py set():
   ttl = self.default_ttl  # ← Gets from cache_ttl config (3600 seconds)
   entry = CacheEntry(value, ttl, metadata)
   self._cache[key] = entry

4. Cache entry stored with:
   - data: The price data
   - created_at: Current timestamp
   - ttl: 3600 seconds (60 minutes)
   - metadata: Area, source, etc.
```

---

### Retrieving Data:

```
1. unified_price_manager.py calls:
   cache_manager.get_data(area, target_date)
   # ✅ NO max_age_minutes parameter!

2. cache_manager.py get_data():
   entry_data = self._price_cache.get(cache_key)
   
3. advanced_cache.py get():
   if entry.is_expired:  # ← Checks age > ttl internally
       del self._cache[key]
       return None
   else:
       return entry.data

4. If entry is < 60 minutes old:
   ✅ Return data (not expired)
   
5. If entry is > 60 minutes old:
   ❌ Delete entry, return None (expired)
```

---

## 💡 Key Insight: Two Different Concepts

### **Old System (Before Our Changes):** ❌

```python
# Retrieval filtering (REMOVED)
cached_data = cache.get_data(
    area="SE1",
    target_date=today,
    max_age_minutes=60  # ← External age check (REMOVED!)
)

# If cache age > 60 minutes → Return None (even if internally not expired)
```

**Problem:** Dual age checking:
1. External check via `max_age_minutes` parameter (60 min)
2. Internal check via `entry.is_expired` (60 min)

Both checked the same thing, caused unnecessary fetches.

---

### **New System (After Our Changes):** ✅

```python
# No external age filtering
cached_data = cache.get_data(
    area="SE1",
    target_date=today
    # ✅ No max_age_minutes!
)

# Internal TTL still works for cleanup
# Entry automatically removed if age > ttl (60 min)
```

**Improvement:** Single age checking:
1. ~~External check~~ (REMOVED)
2. Internal check via `entry.is_expired` (60 min) - **For cleanup only**

**Result:**
- Cache TTL (60 min) still prevents unbounded memory growth
- But retrieval doesn't filter by age anymore
- Content checks (`has_current_hour_price`) determine validity instead

---

## 📊 Current cache_ttl Values

| Location | Value | Purpose | Status |
|----------|-------|---------|--------|
| `Defaults.CACHE_TTL` | 60 minutes | Default TTL for cache entries | ✅ Active |
| `Network.Defaults.CACHE_TTL` | 21600 seconds (6 hours) | Network-specific (unused) | ⚠️ Separate system |
| `Config.CACHE_TTL` | "cache_ttl" | Config key name | ✅ Active |
| User config (optional) | Custom value | User override | ✅ Supported |

**Active Value:** 60 minutes (3600 seconds)

---

## 🔧 What cache_ttl Controls

### ✅ What It DOES Control (Internal):

1. **Entry Expiration:**
   - Entries older than 60 minutes are automatically removed on access
   - Prevents serving truly stale data

2. **Memory Management:**
   - Old entries are cleaned up
   - Prevents unbounded cache growth

3. **Persistence:**
   - When cache is persisted to disk, TTL determines validity on reload

### ❌ What It DOESN'T Control (After Our Changes):

1. **Retrieval Filtering:**
   - NO external `max_age_minutes` check during `get_data()` calls
   - Calling code doesn't filter by age

2. **Fetch Decisions:**
   - Fetch decisions based on **content** (has current price?)
   - NOT based on cache age

3. **API Fetch Timing:**
   - Rate limiter controls timing
   - NOT cache TTL

---

## 📝 Example Timeline

### Scenario: Cache Entry Lifecycle

```
Time: 10:00:00
Action: API fetch returns data
Result: CacheEntry created
  - created_at: 10:00:00
  - ttl: 3600 seconds (60 min)
  - data: Prices for 10:00-23:45

Time: 10:15:00 (15 min later)
Action: User requests data
Check: entry.age = 900 seconds (15 min)
Check: entry.is_expired? 900 < 3600 → NO
Result: ✅ Return data (cache hit)

Time: 10:30:00 (30 min later)
Action: User requests data
Check: entry.age = 1800 seconds (30 min)
Check: entry.is_expired? 1800 < 3600 → NO
Result: ✅ Return data (cache hit)

Time: 10:45:00 (45 min later)
Action: User requests data
Check: entry.age = 2700 seconds (45 min)
Check: entry.is_expired? 2700 < 3600 → NO
Result: ✅ Return data (cache hit)

Time: 11:00:00 (60 min later)
Action: User requests data
Check: entry.age = 3600 seconds (60 min)
Check: entry.is_expired? 3600 >= 3600 → YES
Result: ❌ Entry deleted, return None (expired)

Time: 11:00:01 (60+ min later)
Action: Fetch decision evaluates
Check: has_current_hour_price? NO (cache was None)
Decision: FETCH from API (critical need)
Result: ✅ New cache entry created at 11:00:01
```

---

## 🎯 Why Keep cache_ttl at 60 Minutes?

### Reasons to Keep It:

1. **Prevents Unbounded Growth:**
   - Without TTL, cache would grow forever
   - Memory would fill with old entries

2. **Removes Truly Stale Data:**
   - Data older than 60 minutes is unlikely to be requested
   - Automatic cleanup on next access

3. **Coordinates with Fetch Logic:**
   - Most intervals are 15 minutes
   - 60 minutes = 4 intervals of safety margin
   - Fetch logic will request updates before 60 min anyway

4. **Disk Persistence:**
   - If cache is persisted, TTL prevents loading ancient data on restart

### Could We Increase It?

**YES!** You could increase to 7 days (or any value) since:
- ✅ Fetch decisions are content-based now
- ✅ TTL only affects internal cleanup
- ✅ Rate limiter prevents over-fetching

**To change:**
```python
# In defaults.py
CACHE_TTL = 60 * 24 * 7  # 7 days in minutes

# OR in config
config = {
    "cache_ttl": 10080  # 7 days in minutes
}
```

**Trade-off:**
- Longer TTL = More memory usage
- Shorter TTL = More cleanup overhead
- 60 minutes is reasonable default

---

## 📚 Summary

### Where cache_ttl is Defined:
1. ✅ `const/defaults.py` - Default value (60 minutes)
2. ✅ `const/config.py` - Config key name
3. ⚠️ `const/network.py` - Separate system (21600 seconds)

### Where cache_ttl is Used:
1. ✅ `cache_manager.py` - Gets from config, passes to AdvancedCache
2. ✅ `advanced_cache.py` - Stores as `default_ttl`, uses for new entries
3. ✅ `CacheEntry` class - Stores per-entry TTL, checks `is_expired`

### What cache_ttl Controls:
- ✅ **Internal:** Entry expiration and cleanup
- ✅ **Internal:** Memory management
- ❌ **NOT External:** Retrieval filtering (removed)
- ❌ **NOT External:** Fetch decisions (content-based)

### Key Changes We Made:
1. ✅ **Removed:** `max_age_minutes` parameter from all `get_data()` calls
2. ✅ **Kept:** Internal TTL for cache entry cleanup
3. ✅ **Result:** Cache validity is content-based, not age-based

---

**Current Status:** ✅ **Working as Designed**  
**cache_ttl Purpose:** Internal memory management only  
**Fetch Logic:** Content-based (has current price?)
