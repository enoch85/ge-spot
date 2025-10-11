# Cache Lifecycle: When Is Cache Cleared?

**Date:** October 11, 2025  
**Context:** Complete documentation of cache clearing behavior in GE-Spot

---

## Quick Answer

Cache is **RARELY** cleared automatically. It persists across most operations:

| Event | Cache Cleared? | Why |
|-------|---------------|-----|
| **Sensor update** | ❌ NO | Cache is the whole point! |
| **Home Assistant restart** | ❌ NO | Cache persists (if `persist_cache: true`) |
| **Config reload** | ❌ NO | Reprocesses from cached raw data |
| **VAT/currency change** | ❌ NO | Reprocesses from cached raw data |
| **Manual service call** | ✅ YES | User explicitly requests it |
| **TTL expiration** | ✅ YES | Default: 3 days (4320 minutes) |
| **Max entries exceeded** | ✅ YES (partial) | Evicts oldest entries |

---

## Automatic Cache Clearing

### 1. TTL Expiration (Time To Live)

**When:** Cache entries older than TTL are automatically deleted

**Default TTL:** 3 days (4320 minutes)

```python
# From const/defaults.py
CACHE_TTL = 60 * 24 * 3  # minutes (3 days)

# How it works:
Entry created: 2025-10-11 13:00
TTL expires:   2025-10-14 13:00  # 3 days later
```

**Configuration:**
```yaml
# Can be customized in config (not recommended)
cache_ttl: 4320  # minutes (3 days default)
```

**What happens:**
1. Entry is marked as `expired` after TTL
2. On next `get()`, expired entries are skipped
3. `_evict_if_needed()` periodically cleans up expired entries

**Code reference:**
```python
# utils/advanced_cache.py
class CacheEntry:
    def is_expired(self) -> bool:
        """Check if the cache entry is expired."""
        return self.age > self.ttl  # age = time.time() - created_at
```

### 2. Max Entries Exceeded

**When:** Cache has too many entries

**Default Max:** 3,500 entries

```python
# From const/defaults.py
CACHE_MAX_ENTRIES = 3500  # Max cache entries
# Calculation: 3 days × 24h × 4 intervals × ~12 areas × safety margin
```

**What happens when max reached:**
1. First: Remove all **expired** entries
2. If still too many: Remove **oldest accessed** entries (LRU eviction)

**Code reference:**
```python
# utils/advanced_cache.py
def _evict_if_needed(self) -> None:
    """Evict entries if the cache is full."""
    if len(self._cache) <= self.max_entries:
        return

    # First, remove expired entries
    expired_keys = [key for key, entry in self._cache.items() if entry.is_expired]
    for key in expired_keys:
        del self._cache[key]

    # If still too many, remove least recently used (LRU)
    if len(self._cache) > self.max_entries:
        sorted_keys = sorted(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_accessed
        )
        to_remove = len(self._cache) - self.max_entries
        for key in sorted_keys[:to_remove]:
            del self._cache[key]
```

---

## Manual Cache Clearing

### 1. Service Call: `ge_spot.clear_cache`

**How to use:**
```yaml
# Developer Tools → Services
service: ge_spot.clear_cache
target:
  entity_id: sensor.gespot_current_price_se3
```

**What happens:**
1. Cache cleared for specified area
2. **Immediate fresh fetch** from API (forced, ignores rate limiting)
3. **Health check scheduled** to validate all sources
4. New data cached

**Code reference:**
```python
# coordinator/unified_price_manager.py (line 884)
async def clear_cache(self, target_date: Optional[date] = None):
    """Clear the price cache and immediately fetch fresh data."""
    # Clear the cache first
    cleared = self._cache_manager.clear_cache(target_date=target_date)
    
    if cleared:
        _LOGGER.info("Cache cleared. Forcing fresh fetch for area %s.", self.area)
        
        # Force fetch (bypasses rate limiting)
        fresh_data = await self.fetch_data(force=True)
        
        # Schedule health check to validate all sources
        if not self._health_check_scheduled:
            asyncio.create_task(self._schedule_health_check(run_immediately=True))
            self._health_check_scheduled = True
```

### 2. Home Assistant Restart (If NOT Persisted)

**Default:** Cache persists across restarts

```python
# From const/defaults.py
PERSIST_CACHE = False  # Disabled by default to avoid blocking I/O
```

**If `persist_cache: false` (default):**
- Cache is **in-memory only**
- **Cleared on HA restart**
- First fetch after restart gets fresh data

**If `persist_cache: true`:**
- Cache saved to disk: `.storage/ge_spot_cache.json`
- **NOT cleared on restart**
- Loads from disk on startup

---

## When Cache Is NOT Cleared

### 1. Config Reload / Options Update

**What happens:**
```python
# __init__.py (line 104)
async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
    # ← Cache NOT cleared!
```

**Flow:**
1. User changes config (VAT, currency, display unit)
2. Integration reloads
3. New coordinator created with new config
4. **Cache retrieved with old processed data**
5. Config hash validation detects mismatch
6. **Reprocesses from cached raw data** (no API call!)
7. Saves new processed data with new hash

**Result:** 
- ✅ No API call needed
- ✅ Correct data shown immediately
- ✅ Cache still valid for raw data

### 2. Sensor Updates

**Every ~10 seconds:**
```python
# Sensor update cycle
1. Retrieve cache
2. Check config hash
3. If hash matches → Fast path (update current/next only)
4. If hash differs → Reprocess from raw
5. No cache clearing!
```

### 3. Source Failures

**When API source fails:**
```python
# coordinator/unified_price_manager.py
1. Primary source fails
2. Fallback to next source
3. All sources fail
4. **Fall back to cache** (no clearing!)
5. Use cached data until next fetch
```

**Result:** Resilience - cache provides data when APIs are down

---

## Cache Invalidation Strategy

### Current Strategy: TTL-Based + Config Hash

```
┌─────────────────────────────────────────────────────────┐
│ Entry Created                                           │
│ - TTL: 3 days from now                                  │
│ - Config hash: "abc123" (VAT=25%, EUR→SEK)              │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ Retrieval Checks                                        │
│ 1. Is expired (age > TTL)? → Skip if YES               │
│ 2. Config hash matches? → Reprocess if NO              │
│ 3. Both pass? → Use processed data (fast path)         │
└─────────────────────────────────────────────────────────┘
```

### What Gets Invalidated vs Cleared

| Scenario | Raw Data | Processed Data | Entry |
|----------|----------|----------------|-------|
| **TTL expired** | ✅ Cleared | ✅ Cleared | ✅ Deleted |
| **Config changed** | ✅ Kept | ⚠️ Invalidated | ✅ Kept |
| **Max entries** | ✅ Cleared (LRU) | ✅ Cleared (LRU) | ✅ Deleted |
| **Manual clear** | ✅ Cleared | ✅ Cleared | ✅ Deleted |

**Key distinction:**
- **Cleared** = Deleted from cache, must fetch from API
- **Invalidated** = Marked stale, reprocessed from cached raw data (no API call)

---

## Cache Persistence

### Default: In-Memory Only

```python
# const/defaults.py
PERSIST_CACHE = False  # Default: disabled

# Why disabled?
# Home Assistant warns about blocking I/O in event loop
# See: https://developers.home-assistant.io/docs/asyncio_blocking_operations/#open
```

**Behavior:**
- Cache exists only in RAM
- **Cleared on HA restart**
- No disk I/O overhead
- Faster performance

### Optional: Disk Persistence

**Enable in config:**
```yaml
persist_cache: true
cache_dir: "cache"  # Optional, default location
```

**Behavior:**
- Cache saved to: `<HA_config>/.storage/ge_spot_cache.json`
- **Persists across HA restarts**
- Slight disk I/O overhead
- Useful for frequent restarts during development

**Code reference:**
```python
# utils/advanced_cache.py
def _save_cache(self) -> None:
    """Save cache to disk."""
    if not self.hass or not self.persist_cache:
        return
    
    try:
        cache_file = self._get_cache_file_path()
        serialized = {
            key: entry.to_dict() 
            for key, entry in self._cache.items()
        }
        
        with open(cache_file, 'w') as f:
            json.dump(serialized, f, indent=2)
            
    except Exception as e:
        _LOGGER.error(f"Failed to save cache: {e}")
```

---

## Cache Clearing Decision Tree

```
┌─────────────────────────────────────────┐
│ Should I clear cache?                   │
└─────────────────────────────────────────┘
                 ↓
         ┌───────────────┐
         │ What changed? │
         └───────────────┘
                 ↓
    ┌────────────┴────────────┐
    │                         │
    ↓                         ↓
┌─────────────┐      ┌──────────────┐
│ Config      │      │ Suspected    │
│ (VAT/curr)  │      │ bad data     │
└─────────────┘      └──────────────┘
    ↓                         ↓
    │                         │
❌ NO CLEAR              ✅ CLEAR
Reprocesses             Use service:
from raw data           ge_spot.clear_cache
    
    
┌─────────────────────────────────────────┐
│ Other scenarios                         │
├─────────────────────────────────────────┤
│ • Normal sensor updates → ❌ NO CLEAR   │
│ • Source failures → ❌ NO CLEAR         │
│ • HA restart → ❌ NO (if persisted)     │
│ • TTL expired → ✅ AUTO CLEAR           │
│ • Max entries → ✅ AUTO CLEAR (oldest)  │
└─────────────────────────────────────────┘
```

---

## Real-World Examples

### Example 1: User Changes VAT

```
Timeline:
13:00 - API fetch with VAT=25%
      - Cache: raw + processed (VAT=25%)
      
13:05 - User changes VAT to 0% in HA
      - Config reload (NO cache clear)
      
13:06 - Sensor update
      - Retrieve cache
      - Config hash mismatch detected
      - Reprocess from raw_interval_prices_original
      - New processed data with VAT=0%
      - Save to cache
      
13:07 - Sensor update
      - Config hash matches
      - Fast path (no reprocessing)
      
Result: No cache clear, no API call, correct data immediately
```

### Example 2: All APIs Down

```
Timeline:
13:00 - API fetch succeeds
      - Cache: raw + processed
      
13:15 - Next fetch interval
      - Primary API (nordpool): FAIL
      - Fallback API (entsoe): FAIL
      - Fallback API (energy_charts): FAIL
      - Fall back to CACHE (no clear!)
      
13:16-14:00 - Sensor updates every 10s
      - Use cached data (fast path)
      - No API calls
      - Users see last known good data
      
14:15 - Next fetch interval
      - API recovered
      - Fresh fetch succeeds
      - Update cache
      
Result: Cache provides resilience, no clearing during outage
```

### Example 3: Manual Clear (Debugging)

```
Timeline:
13:00 - API fetch returns bad data
      - Cache stores it
      - Users see wrong prices
      
13:05 - User calls service
      service: ge_spot.clear_cache
      
      - Cache CLEARED
      - Immediate forced fetch (bypasses rate limit)
      - Health check scheduled
      - Fresh data (hopefully correct) cached
      
13:06 - Sensor update
      - Uses new fresh cache
      
Result: Manual intervention clears bad data
```

### Example 4: Three Days Later

```
Timeline:
Oct 11 13:00 - API fetch
      - Cache entry created
      - TTL: 3 days (expires Oct 14 13:00)
      
Oct 12 13:00 - Sensor updates
      - Cache valid (age: 1 day)
      - Fast path
      
Oct 13 13:00 - Sensor updates
      - Cache valid (age: 2 days)
      - Fast path
      
Oct 14 13:00 - Sensor update
      - Cache expired (age: 3 days)
      - Entry skipped/deleted
      - Fresh API fetch
      - New cache entry created
      
Result: Automatic TTL expiration after 3 days
```

---

## v1.4.0 Implementation: Cache Clearing Changes

### What Changes in v1.4.0?

**Cache structure changes, but clearing logic stays the same:**

```python
# BEFORE v1.4.0
cache_entry = {
    "raw_interval_prices_original": {...},  # Only raw data
    # Processed data NOT cached
}

# AFTER v1.4.0
cache_entry = {
    # Raw data (unchanged)
    "raw_interval_prices_original": {...},
    
    # NEW: Processed data (added)
    "interval_prices": {...},
    "statistics": {...},
    
    # NEW: Config validation (added)
    "processing_config_hash": "abc123"
}
```

**Clearing behavior UNCHANGED:**
- Still clears on TTL expiration
- Still clears on max entries
- Still clears on manual service call
- Still NOT cleared on config reload

**New behavior:**
- Config hash validation prevents stale processed data
- Reprocessing from cached raw data when config changes
- No need to clear cache on config changes

---

## Summary Table

| Trigger | Frequency | What's Cleared | API Call Needed? |
|---------|-----------|----------------|------------------|
| **TTL expiration** | Every 3 days | Entire entry | ✅ Yes |
| **Max entries** | When > 3500 | Oldest entries | ✅ Yes (for cleared) |
| **Manual clear** | On demand | Specified area | ✅ Yes (forced) |
| **Config change** | Rare | ❌ Nothing | ❌ No (reprocess raw) |
| **HA restart** | On restart | ❌ Nothing (if persisted) | ❌ No |
| **Source failure** | Variable | ❌ Nothing | ❌ No (uses cache) |
| **Sensor update** | Every 10s | ❌ Nothing | ❌ No (uses cache) |

---

## Best Practices

### When to Clear Cache Manually

✅ **DO clear when:**
- Debugging data issues
- API returned obviously wrong data
- Testing after code changes
- Forcing immediate data refresh

❌ **DON'T clear when:**
- Changing VAT/currency/display unit (automatic reprocessing)
- API is temporarily down (cache provides resilience)
- Normal operation (TTL handles expiration)

### Monitoring Cache Health

**Check cache stats:**
```python
# In code or service
stats = coordinator.price_manager._cache_manager.get_cache_stats()

# Returns:
{
    "total_entries": 150,
    "expired_entries": 5,
    "max_entries": 3500,
    "default_ttl": 259200,  # 3 days in seconds
    "persist_cache": false,
    "entries": {...}  # Full entry details
}
```

**What to look for:**
- High `expired_entries` → Cleanup running normally
- `total_entries` near `max_entries` → May need larger cache
- Frequent manual clears → Investigate data quality issues

---

## Conclusion

**Cache is designed to persist and avoid unnecessary API calls.**

**Clear only when:**
1. TTL expires (automatic, every 3 days)
2. Max entries exceeded (automatic, LRU eviction)
3. Manual debugging (service call)

**Don't clear for:**
- Config changes (reprocesses from cached raw data)
- Sensor updates (uses cache)
- Source failures (cache provides resilience)
- HA restarts (if persisted)

**Result:** Efficient, resilient system that respects API rate limits while providing fresh data when needed.
