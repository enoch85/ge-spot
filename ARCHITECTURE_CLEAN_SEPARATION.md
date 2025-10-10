# Architecture: Clean Separation of Concerns

## Before (PR #17) - Mixed Responsibilities ❌

```
__init__.py
├─ validate_configured_sources_once()  ← Validation logic here
├─ Skip first_refresh logic             ← Decision logic here
└─ Create sensors (maybe no data!)      ← Race condition!

session_manager.py
├─ HTTP request
├─ Retry logic (3 attempts)
└─ Fixed 30s timeout                    ← Timeout logic here

unified_price_manager.py
├─ Background validation tasks          ← Validation logic here too
├─ Daily retry scheduling               ← Retry logic here too
├─ _disabled_sources tracking           ← State tracking here
└─ fetch_data() eventually called
```

**Problems:**
- 🔴 Validation logic scattered (init.py + manager.py)
- 🔴 Timeout logic in wrong layer (session_manager)
- 🔴 Skip first_refresh creates race condition
- 🔴 Multiple sources of truth for source status
- 🔴 Mixed concerns everywhere

---

## After (This Plan) - Clean Layers ✅

```
┌─────────────────────────────────────────────────────┐
│ __init__.py                                         │
│ Responsibility: Integration entry point            │
│                                                     │
│ await coordinator.async_config_entry_first_refresh()│
│ ↓                                                   │
│ SIMPLE - just call first_refresh, nothing else     │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ coordinator/fetch_data()                            │
│ Responsibility: Orchestration & decisions          │
│                                                     │
│ • Should we fetch? (decision maker)                │
│ • Rate limiting                                    │
│ • Call FallbackManager                             │
│ • Handle result (cache, process, return)           │
│ • Schedule daily retry if all failed               │
│ • Track failed sources (Dict[str, datetime])       │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ coordinator/fallback_manager.py                     │
│ Responsibility: Source retry logic & timeout       │
│                                                     │
│ for source in sources:                             │
│   for attempt in range(3):                         │
│     timeout = 2 * (3 ** attempt)  # 2s, 6s, 18s   │
│     data = await asyncio.wait_for(                 │
│       source.fetch(), timeout=timeout              │
│     )                                              │
│     if success: return data                        │
│     if fail: retry or next source                  │
│                                                     │
│ OWNS: Exponential backoff, source iteration       │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ api/{source}.py (nordpool, entsoe, etc.)           │
│ Responsibility: API-specific data fetching         │
│                                                     │
│ async def fetch_raw_data():                        │
│   response = await session_manager.fetch()         │
│   return parse(response)                           │
│                                                     │
│ OWNS: API specifics, data parsing                 │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ api/base/session_manager.py                        │
│ Responsibility: HTTP transport ONLY                │
│                                                     │
│ async def fetch_with_retry():                      │
│   for attempt in range(retries):                  │
│     try:                                           │
│       response = await session.get(url, timeout)   │
│       return response                              │
│     except NetworkError:                           │
│       retry                                        │
│                                                     │
│ OWNS: HTTP, network errors, basic retry           │
│ DOES NOT: Control timeout strategy, track sources │
└─────────────────────────────────────────────────────┘
```

---

## Responsibility Matrix

| Component | Timeout Strategy | Source Tracking | Retry Logic | HTTP | Orchestration |
|-----------|-----------------|-----------------|-------------|------|---------------|
| **__init__.py** | ❌ | ❌ | ❌ | ❌ | Calls first_refresh |
| **fetch_data()** | ❌ | ✅ Failed sources | ❌ | ❌ | ✅ Decisions |
| **FallbackManager** | ✅ Exponential | ❌ | ✅ Per-source | ❌ | ❌ |
| **API classes** | ❌ | ❌ | ❌ | Calls session | Data parsing |
| **session_manager** | ❌ | ❌ | Basic network retry | ✅ HTTP | ❌ |

**✅ = Owns this responsibility**  
**❌ = Does NOT handle this**

---

## Data Flow

```
1. HA Boot
   ↓
2. __init__.py: await first_refresh()
   ↓
3. fetch_data(): Should we fetch? Yes
   ↓
4. fetch_data(): Filter failed sources (24h timeout)
   ↓
5. fetch_data(): Call FallbackManager.fetch_with_fallback()
   ↓
6. FallbackManager: Try source 1
   ├─ Attempt 1: timeout=2s  → fail
   ├─ Attempt 2: timeout=6s  → fail
   ├─ Attempt 3: timeout=18s → fail
   ↓
7. FallbackManager: Try source 2
   ├─ Attempt 1: timeout=2s  → SUCCESS ✅
   ↓
8. FallbackManager: Return data
   ↓
9. fetch_data(): Mark source 1 as failed (timestamp)
   ↓
10. fetch_data(): Mark source 2 as working (clear failure)
   ↓
11. fetch_data(): Cache result
   ↓
12. fetch_data(): Process & return
   ↓
13. Sensors created with valid data ✅
```

---

## Benefits of Clean Architecture

### ✅ Single Responsibility
- Each component does ONE thing well
- Easy to understand what each layer does
- Changes isolated to appropriate layer

### ✅ Testability
```python
# Test FallbackManager in isolation
mock_sources = [SlowSource(), FastSource()]
result = await fallback_manager.fetch(mock_sources, area)
assert result.source == "FastSource"

# Test timeout strategy
with assert_timeout(2):  # Should fail in 2s
    await fallback_manager.fetch([DownSource()], area)
```

### ✅ Maintainability
- Want different timeout? Change FallbackManager only
- Want different timeout strategy? Change FallbackManager only
- Want to add new source? No changes to timeout/retry logic

### ✅ Clear Dependencies
```
__init__.py
  → coordinator
    → fetch_data()
      → FallbackManager
        → API classes
          → session_manager
```

No circular dependencies, no mixed concerns.

---

## Removed Complexity

### ❌ Deleted
- Separate validation step (203-530 lines)
- Skip first_refresh logic
- Background validation tasks
- Slow source concept
- Multiple timeout constants
- `_validated_sources`, `_disabled_sources`, `_energy_charts_validation_task`

### ✅ Simplified to
- Always call first_refresh
- FallbackManager handles all retry logic
- Single timeout strategy (exponential)
- Single source tracking (failed_sources dict)

**Lines of code removed:** ~400  
**Lines of code added:** ~80 (FallbackManager timeout logic)  
**Net reduction:** ~320 lines  
**Complexity reduction:** ~75%

---

## Future Flexibility

With clean separation, easy to add:

1. **Adaptive timeouts** (FallbackManager only)
   ```python
   # Track source performance
   timeout = historical_avg[source] * 1.5
   ```

2. **Circuit breaker** (fetch_data only)
   ```python
   if source.failure_count > 10:
       disable_permanently(source)
   ```

3. **Different retry strategies** (FallbackManager only)
   ```python
   if source.is_flaky:
       use_fibonacci_backoff()
   else:
       use_exponential_backoff()
   ```

All without touching other layers!

---

## Conclusion

**Before:** Spaghetti of validation, timeouts, retries scattered across multiple files

**After:** Clean layers, each with clear responsibility

This is how it should be done. 🎯
