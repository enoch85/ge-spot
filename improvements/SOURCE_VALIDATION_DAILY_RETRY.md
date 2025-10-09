# Source Validation & Daily Retry - Complete Implementation

**Date**: October 9, 2025  
**Feature**: Smart source validation with disabled source tracking and daily retry  
**Philosophy**: Validation results matter - don't keep trying sources that failed

## The Problem We Solved

**Before**: Validation was pointless
```
1. Validation runs → Energy Charts fails ✗
2. FallbackManager tries Energy Charts anyway → Wastes 30s
3. EVERY fetch tries Energy Charts → Wastes 30s each time
4. No retry logic → Source stays broken until HA restart
```

**Result**: Wasted time on every fetch, no automatic recovery

---

## The Solution: Option A (Disable Failed Sources)

### Core Principle
> **Respect validation results** - If a source fails validation, don't keep trying it

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     VALIDATION PHASE                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Reliable Sources (Nordpool, OMIE, etc.)                    │
│  ├─ Blocking validation (30s timeout) - BLOCKS STARTUP      │
│  ├─ ✓ Success → Enabled + Cached                            │
│  ├─ ✗ Failure → DISABLED + Schedule daily retry             │
│  └─ Typically completes in <1s                              │
│                                                               │
│  Slow Sources (Energy Charts, etc.)                         │
│  ├─ Background validation (120s timeout, async)             │
│  ├─ ✓ Success → Enabled + Cached                            │
│  ├─ ✗ Failure → DISABLED + Schedule daily retry             │
│  └─ Doesn't block startup (runs in background)              │
│                                                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     NORMAL FETCHES                           │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Build API instance list                                 │
│  2. Filter out DISABLED sources                             │
│  3. FallbackManager tries ONLY enabled sources              │
│  4. Fast fetches (no waiting for known-broken sources)      │
│                                                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     DAILY RETRY (ALL SOURCES)                │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Runs: Once per 24h during special hours (0-1, 13-15)       │
│  Who: ALL disabled sources (slow + reliable)                │
│  How: Async background (doesn't block anything)             │
│                                                               │
│  Reliable Sources (e.g., Nordpool)                          │
│  ├─ Retry timeout: 30s                                      │
│  ├─ ✓ Success → Re-enabled, used in next fetch              │
│  └─ ✗ Failure → Stays disabled, retry tomorrow              │
│                                                               │
│  Slow Sources (e.g., Energy Charts)                         │
│  ├─ Retry timeout: 120s                                     │
│  ├─ ✓ Success → Re-enabled, used in next fetch              │
│  └─ ✗ Failure → Stays disabled, retry tomorrow              │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Details

### 1. Disabled Sources Tracking

**Added**: `self._disabled_sources` set

```python
class UnifiedPriceManager:
    def __init__(self, ...):
        self._validated_sources = set()  # Successfully validated
        self._disabled_sources = set()    # Failed validation (new!)
```

**Helper Methods**:
```python
def get_validated_sources() -> List[str]  # Sources that passed validation
def get_disabled_sources() -> List[str]   # Sources that failed validation  
def get_enabled_sources() -> List[str]    # Currently active sources
```

---

### 2. Validation Updates Source State

```python
async def validate_single_source(api_class, timeout=None):
    # ... fetch and validate ...
    
    if is_valid:
        self._validated_sources.add(source_name)
        self._disabled_sources.discard(source_name)  # Re-enable if was disabled
        # Cache data immediately
    else:
        self._disabled_sources.add(source_name)  # Disable on failure
        _LOGGER.warning(f"'{source_name}' validation failed - source disabled (will retry daily)")
```

**Automatic re-enabling**: If a previously disabled source validates successfully (e.g., during daily retry), it's immediately removed from `_disabled_sources`.

---

### 3. Filter Disabled Sources in Fetches

**Before** (tried all configured sources):
```python
api_instances = [
    cls(...) for cls in self._api_classes  # Includes failed sources!
]
```

**After** (skips disabled sources):
```python
enabled_api_classes = [
    cls for cls in self._api_classes
    if cls(config={}).source_type not in self._disabled_sources
]

api_instances = [cls(...) for cls in enabled_api_classes]
```

**Logging**:
```
[ES] Skipping 1 disabled source(s): energy_charts (failed validation)
```

---

### 4. Daily Retry for ALL Failed Sources

#### Reliable Sources (Nordpool, OMIE, etc.)

After validation, track failed sources:
```python
failed_reliable_sources = []
for source_name, is_valid, data in results:
    if not is_valid:
        failed_reliable_sources.append(api_class)

# Schedule async background retry
asyncio.create_task(
    self._validate_failed_sources_background(
        failed_reliable_sources, 
        validate_func, 
        is_slow=False  # 30s timeout
    )
)
```

#### Slow Sources (Energy Charts, etc.)

Already run in background, schedule retry on failure:
```python
asyncio.create_task(
    self._validate_failed_sources_background(
        slow_source_apis,
        validate_func,
        is_slow=True  # 120s timeout
    )
)
```

---

### 5. Unified Daily Retry Logic

```python
async def _schedule_daily_source_retry(api_class, validate_func, source_name, is_slow):
    """Daily retry for ANY failed source (slow or reliable).
    
    Note: This runs async in background (never blocks).
    """
    
    # Use appropriate timeout
    timeout = Network.Defaults.SLOW_SOURCE_TIMEOUT if is_slow else Network.Defaults.TIMEOUT
    
    while True:
        # Check if in special hours (13-15 or 0-1)
        in_special_hours = any(
            start <= current_hour < end 
            for start, end in Network.Defaults.SPECIAL_HOUR_WINDOWS
        )
        
        # Retry once per day
        if in_special_hours and (last_retry is None or last_retry.date() < today):
            # Random delay to spread load
            delay = random.randint(0, 3600)
            await asyncio.sleep(delay)
            
            # Retry validation
            result = await validate_func(api_class, timeout=timeout)
            source_name, is_valid, data = result
            
            if is_valid:
                # validate_func already re-enabled the source
                _LOGGER.info(f"✓ '{source_name}' daily retry successful - source re-enabled")
                return  # Stop retrying
            else:
                _LOGGER.warning(f"✗ '{source_name}' daily retry failed - will try tomorrow")
            
            last_retry = now
        
        # Check every 30 minutes
        await asyncio.sleep(1800)
```

---

## Timeout Summary

| Operation | Slow Sources | Reliable Sources | Blocks Startup? |
|-----------|--------------|------------------|-----------------|
| **Initial Validation** | 120s (background) | 30s (blocking) | **No** / **Yes** |
| **Normal Fetch** | Skipped if disabled | Skipped if disabled | N/A |
| **Daily Retry** | 120s (background) | 30s (background) | **No** |
| **Wait for validation** | 5s max | N/A | Yes (5s max) |

**Important**: Only slow sources run background validation. Reliable sources block startup (but typically complete in <1s).

---

## Configuration

### Slow Sources List

**File**: `const/sources.py`

```python
class Source:
    SLOW_SOURCES = [
        ENERGY_CHARTS,  # Free API, no SLA, 30s+ response times common
        # Add future slow sources here
    ]
```

**Easy to extend**: Just add source name to list, all logic automatically applies.

### Timeout Constants

**File**: `const/network.py`

```python
class Network:
    class Defaults:
        TIMEOUT = 30  # Reliable sources
        SLOW_SOURCE_TIMEOUT = 120  # Slow sources
        SLOW_SOURCE_VALIDATION_WAIT = 5  # Wait for slow validation before first fetch
```

### Retry Timing

**File**: `const/time.py`

```python
class ValidationRetry:
    MAX_RANDOM_DELAY_SECONDS = 3600  # Random delay up to 1 hour
    RETRY_CHECK_INTERVAL_SECONDS = 1800  # Check every 30 minutes
```

**File**: `const/network.py`

```python
class Network:
    class Defaults:
        SPECIAL_HOUR_WINDOWS = [
            (0, 1),   # 00:00-01:00 - New day prices
            (13, 15), # 13:00-15:00 - Tomorrow data publication
        ]
```

---

## Example Scenarios

### Scenario 1: Nordpool Fails Validation (Reliable Source)

```
Startup:
├─ 00:00:00.000  Validation: Nordpool (30s timeout)
├─ 00:00:15.000  ✗ Nordpool timeout (15s, network issue)
├─ 00:00:15.001  Nordpool DISABLED
├─ 00:00:15.002  Schedule daily retry (async background)
└─ 00:00:15.003  Continue startup (OMIE validates successfully)

First Fetch:
├─ 00:00:16.000  Build API list
├─ 00:00:16.001  Filter: Skipping 1 disabled source (nordpool)
├─ 00:00:16.002  FallbackManager: Try OMIE only
└─ 00:00:16.050  ✓ Success with OMIE (0.05s)

Daily Retry (Next Day):
├─ 13:42:17.000  Random time in 13-15 window
├─ 13:42:17.001  Retry Nordpool (30s timeout)
├─ 13:42:17.150  ✓ Success! (0.15s)
├─ 13:42:17.151  Nordpool RE-ENABLED
└─ 13:42:17.152  Stop retry loop

Next Fetch:
├─ 13:45:00.000  FallbackManager: Try Nordpool (now enabled)
└─ 13:45:00.150  ✓ Success with Nordpool
```

**Result**: Automatic recovery without user intervention!

---

### Scenario 2: Energy Charts Fails (Slow Source)

```
Startup:
├─ 00:00:00.000  Validation: Start Energy Charts background (120s timeout)
├─ 00:00:00.001  ✓ Validation returns immediately (doesn't block)
├─ 00:00:00.002  Continue startup (OMIE validates in 0.05s)
└─ 00:00:00.050  ✓ Startup complete in 0.05s

Background (parallel):
├─ 00:00:00.000  Energy Charts validating...
├─ 00:02:00.000  ✗ Energy Charts timeout (120s)
├─ 00:02:00.001  Energy Charts DISABLED
└─ 00:02:00.002  Schedule daily retry

First Fetch (00:00:00.100):
├─ Wait 5s for validation? (validation task still running)
├─ 00:00:05.100  Timeout waiting, proceed
├─ 00:00:05.101  Check cache: No data (validation didn't finish)
├─ 00:00:05.102  Build API list
├─ 00:00:05.103  Filter: Energy Charts not yet disabled (still validating)
├─ 00:00:05.104  FallbackManager: Try Energy Charts
├─ 00:00:35.104  ✗ Energy Charts timeout (30s)
├─ 00:00:35.105  Try OMIE
└─ 00:00:35.150  ✓ Success with OMIE

Second Fetch (00:15:00.000):
├─ 00:15:00.000  Build API list
├─ 00:15:00.001  Filter: Skipping 1 disabled source (energy_charts)
├─ 00:15:00.002  FallbackManager: Try OMIE only
└─ 00:15:00.050  ✓ Success with OMIE (0.05s - fast!)

Daily Retry (13:27:42):
├─ 13:27:42.000  Random time in 13-15 window
├─ 13:27:42.001  Retry Energy Charts (120s timeout)
├─ 13:27:43.000  ✓ Success! (1s)
├─ 13:27:43.001  Energy Charts RE-ENABLED
└─ Stop retry

Next Fetch (13:30:00):
├─ FallbackManager: Try Energy Charts first (priority #1, now enabled)
└─ ✓ Success with Energy Charts
```

**Result**: First fetch takes 35s (validation + fallback), all subsequent fetches <1s until daily retry succeeds!

---

## Benefits

### 1. Faster Fetches
- **Before**: Try failed source every time (30s wasted per fetch)
- **After**: Skip disabled sources (0s wasted)

### 2. Automatic Recovery
- **Before**: Manual HA restart needed
- **After**: Daily retry automatically re-enables working sources

### 3. Respects Validation
- **Before**: Validation results ignored
- **After**: Disabled sources aren't tried until they work

### 4. Consistent for All Sources
- Slow sources: 120s timeout
- Reliable sources: 30s timeout
- Both: Daily retry, same logic

### 5. Configuration-Driven
- Add new slow source: Just add to `Source.SLOW_SOURCES` list
- Change timeouts: Update constants, applies everywhere
- Adjust retry windows: Modify `SPECIAL_HOUR_WINDOWS`

---

## Monitoring

### Check Disabled Sources

```python
manager.get_disabled_sources()
# Returns: ['energy_charts', 'nordpool']
```

### Check Enabled Sources

```python
manager.get_enabled_sources()
# Returns: ['omie', 'entsoe']
```

### Log Messages

**Validation failure**:
```
[ES] ✗ 'energy_charts' validation timeout after 120s - source disabled (will retry daily during special hours)
```

**Fetch filtering**:
```
[ES] Skipping 2 disabled source(s): energy_charts, nordpool (failed validation)
```

**Daily retry success**:
```
[ES] ✓ 'energy_charts' (slow) daily retry successful - source re-enabled and will be used in next fetch
```

**Daily retry failure**:
```
[ES] ✗ 'nordpool' (reliable) daily retry failed - source remains disabled, will try tomorrow
```

---

## Future Enhancements

1. **Circuit breaker**: Disable after N consecutive failures, even if not during validation
2. **Health metrics**: Track success/failure rates per source
3. **Smart retry timing**: Retry more frequently if all sources disabled
4. **User notifications**: Alert when sources auto-disabled/re-enabled
5. **Manual re-enable**: Service call to force retry disabled source

---

## Summary

### What Changed

1. ✅ Added `_disabled_sources` tracking
2. ✅ Validation marks sources as enabled/disabled
3. ✅ Fetches skip disabled sources (saves time)
4. ✅ Daily retry for ALL failed sources (slow + reliable)
5. ✅ Appropriate timeouts (120s slow, 30s reliable)
6. ✅ Daily retry async background (never blocks)
7. ✅ Configuration-driven (no hardcoding)

**Note**: Initial validation is **blocking for reliable sources** (typically <1s), **non-blocking for slow sources** (background with 120s timeout).

### Key Principle

> **Validation results have consequences** - Failed sources are disabled until proven working again

This prevents wasted API calls, speeds up fetches, and enables automatic recovery!
