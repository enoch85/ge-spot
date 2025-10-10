# Daily Health Check Implementation Plan

## Overview
Replace per-source retry tasks with a single daily health check that validates ALL configured sources (working + failed) during special hour windows.

---

## Problem Statement

**Current behavior:**
- Only failed sources are retried during special hour windows
- Working sources are never re-validated
- User has no visibility into whether fallback sources are healthy
- Multiple retry tasks running independently (one per failed source)

**Example scenario:**
```
Priority: Nordpool → ENTSOE → Energy Charts
Nordpool always works → ENTSOE and Energy Charts NEVER validated
User has no idea if fallback sources are healthy
```

**Desired behavior:**
- Validate ALL sources once per day during special hour windows
- Update health status for all sources (working + failed)
- Single consolidated health check task
- User sees complete source health status in attributes

---

## Solution Design

### Core Principles

1. **Consolidate validation** - Single daily task instead of per-source retry tasks
2. **Validate everything** - Check ALL sources, not just failed ones
3. **Minimal changes** - Leverage existing FallbackManager exponential backoff
4. **Clean separation** - Health check is distinct from normal fetch operations
5. **User visibility** - Expose health status, timestamps, and retry schedule

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Special Hour Window (13:00-15:00 or 00:00-01:00)            │
│ Triggers once per day                                       │
└────────────────┬────────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ _schedule_health_check()                                    │
│ - Wait for special hour window                             │
│ - Add random delay (0-3600s) to spread load                │
│ - Call _validate_all_sources()                             │
│ - Sleep until next window (next day)                       │
└────────────────┬────────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ _validate_all_sources()                                     │
│ Loop through ALL configured sources:                        │
│   - Try each source independently                           │
│   - Use FallbackManager exponential backoff (2s→6s→18s)    │
│   - Success → Clear failure timestamp (_failed_sources[x]=None) │
│   - Failure → Mark with timestamp (_failed_sources[x]=now) │
│ Log summary: "3 validated, 2 failed"                       │
└────────────────┬────────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ Normal fetch_data() operations                              │
│ - Filter sources: skip those with recent failure timestamp │
│ - Use validated sources in priority order                  │
│ - If all fail: schedule health check (if not running)     │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow Example

```
17:36 → Energy Charts fails during normal fetch
        └─ _failed_sources["energy_charts"] = 2025-10-10 17:36:42
        └─ Schedule health check task (if not already running)

17:37 → Fallback tries Nordpool → Success
        └─ Energy Charts skipped (failed <24h ago)
        └─ _failed_sources["nordpool"] = None (working)

[Time passes... Energy Charts still in failed state]

13:05 (next day) → Daily health check runs
        ├─ Try Nordpool → Success → _failed_sources["nordpool"] = None ✓
        ├─ Try ENTSOE → Success → _failed_sources["entsoe"] = None ✓
        └─ Try Energy Charts → Success! → _failed_sources["energy_charts"] = None ✓
        └─ Log: "Health check complete: 3 validated, 0 failed"

13:06 → Normal fetch
        ├─ Filter sources: All have timestamp=None → All enabled
        ├─ Sort by priority: [Energy Charts, Nordpool, ENTSOE]
        └─ Fallback tries Energy Charts first → Success!
            └─ Energy Charts is back as primary source 🎉
```

---

## Implementation Details

### 1. unified_price_manager.py - Main Changes

#### 1.1 Update Initialization
**Location:** `__init__` method (lines 86-120)

**Changes:**
```python
# REMOVE:
self._retry_scheduled = set()  # No longer needed

# ADD:
self._health_check_scheduled = False  # Single flag for health check task
self._last_health_check = None  # datetime of last health check
```

**Rationale:** Single flag is simpler than tracking individual source tasks.

---

#### 1.2 Replace `_schedule_daily_retry()` with `_schedule_health_check()`
**Location:** Lines 225-295 (current `_schedule_daily_retry` method)

**New method:**
```python
async def _schedule_health_check(self):
    """Schedule daily health check for ALL sources during special hours.
    
    Validates all configured sources once per day during special hour windows.
    Uses FallbackManager's exponential backoff for each source independently.
    """
    import random
    
    last_check_date = None
    
    while True:
        now = dt_util.now()
        current_hour = now.hour
        today_date = now.date()
        
        # Check if we're in a special hour window
        in_special_hours = any(
            start <= current_hour < end
            for start, end in Network.Defaults.SPECIAL_HOUR_WINDOWS
        )
        
        # Only check once per day
        should_check = (
            in_special_hours and
            (last_check_date is None or last_check_date < today_date)
        )
        
        if should_check:
            # Random delay within current hour to spread load
            delay_seconds = random.randint(0, ValidationRetry.MAX_RANDOM_DELAY_SECONDS)
            _LOGGER.info(
                f"[{self.area}] Daily health check starting in {delay_seconds}s "
                f"(validating {len(self._api_classes)} sources)"
            )
            await asyncio.sleep(delay_seconds)
            
            # Validate ALL sources
            await self._validate_all_sources()
            
            last_check_date = now.date()
            self._last_health_check = now
        
        # Sleep 1 hour and check again (will naturally land in window tomorrow)
        await asyncio.sleep(3600)
```

**Key differences from old `_schedule_daily_retry`:**
- No `source_name` parameter - validates ALL sources
- No check for "did this specific source succeed" - tries everything
- Single task instead of one per failed source
- Simple hourly loop - random time within special window each day

---

#### 1.3 Add `_validate_all_sources()` method
**Location:** After `_schedule_health_check()` (new method, ~60 lines)

**New method:**
```python
async def _validate_all_sources(self):
    """Validate ALL configured sources independently.
    
    Unlike normal fetch (stops at first success), this tries EVERY source
    to get complete health status. Each source is tested with exponential
    backoff (2s → 6s → 18s) via FallbackManager logic.
    """
    now = dt_util.now()
    results = {
        "validated": [],
        "failed": []
    }
    
    _LOGGER.info(f"[{self.area}] Starting health check for {len(self._api_classes)} sources")
    
    for api_class in self._api_classes:
        source_name = api_class(config={}).source_type
        
        try:
            # Create API instance
            api_kwargs = {
                "area": self.area,
                "currency": self.currency,
                "config": self.config,
            }
            api_instance = api_class(**api_kwargs)
            
            # Try fetching with FallbackManager's exponential backoff
            # Pass single source to FallbackManager
            result = await self._fallback_manager.fetch_with_fallback(
                api_instances=[api_instance],
                area=self.area,
                reference_time=now,
                session=async_get_clientsession(self.hass)
            )
            
            # Check if source returned valid data
            if result and result.get("raw_data"):
                # Success - clear failure timestamp
                self._failed_sources[source_name] = None
                results["validated"].append(source_name)
                _LOGGER.info(f"[{self.area}] Health check: '{source_name}' ✓ validated")
            else:
                # No data - mark as failed
                self._failed_sources[source_name] = now
                results["failed"].append(source_name)
                
                # Count validated sources for user context
                validated_count = len([s for s in self._failed_sources.values() if s is None])
                _LOGGER.warning(
                    f"[{self.area}] Health check: '{source_name}' ✗ no data returned. "
                    f"Will retry during next daily health check. "
                    f"({validated_count} other source(s) available)"
                )
                
        except Exception as e:
            # Error - mark as failed
            self._failed_sources[source_name] = now
            results["failed"].append(source_name)
            
            # Count validated sources for user context
            validated_count = len([s for s in self._failed_sources.values() if s is None])
            _LOGGER.warning(
                f"[{self.area}] Health check: '{source_name}' ✗ failed: {e}. "
                f"Will retry during next daily health check. "
                f"({validated_count} other source(s) available)",
                exc_info=True
            )
    
    # Log summary
    _LOGGER.info(
        f"[{self.area}] Health check complete: "
        f"{len(results['validated'])} validated, {len(results['failed'])} failed. "
        f"Validated: {', '.join(results['validated']) or 'none'}. "
        f"Failed: {', '.join(results['failed']) or 'none'}"
    )
```

**Behavior:**
- Tries each source **independently** (doesn't stop at first success)
- Uses existing FallbackManager for exponential backoff
- Updates `_failed_sources` for every source
- Provides clear logging for debugging

---

#### 1.4 Update `fetch_data()` - Replace scheduling logic
**Location:** Lines 579-599 (current per-source scheduling)

**Replace:**
```python
# OLD (lines 579-599):
# Implicit validation: Mark all attempted sources as failed and schedule daily retry
if self._attempted_sources:
    _LOGGER.info(...)
    for source_name in self._attempted_sources:
        self._failed_sources[source_name] = now
        
        # Schedule daily retry if not already scheduled
        if source_name not in self._retry_scheduled:
            _LOGGER.info(f"[{self.area}] Scheduling daily retry for '{source_name}'")
            # Find the API class for this source
            for cls in self._api_classes:
                if cls(config={}).source_type == source_name:
                    asyncio.create_task(
                        self._schedule_daily_retry(source_name, cls)
                    )
                    self._retry_scheduled.add(source_name)
                    break

# NEW:
# Mark attempted sources as failed
if self._attempted_sources:
    _LOGGER.info(
        f"[{self.area}] Marking {len(self._attempted_sources)} failed source(s): "
        f"{', '.join(self._attempted_sources)}"
    )
    for source_name in self._attempted_sources:
        self._failed_sources[source_name] = now
    
    # Schedule health check task (once) if not already running
    if not self._health_check_scheduled:
        _LOGGER.info(
            f"[{self.area}] Scheduling daily health check task "
            f"(will validate all {len(self._api_classes)} sources)"
        )
        asyncio.create_task(self._schedule_health_check())
        self._health_check_scheduled = True
```

**Key change:** Single task creation instead of loop creating tasks per source.

---

#### 1.5 Add helper method for failed source details
**Location:** After `get_enabled_sources()` (around line 210)

**New method:**
```python
def get_failed_source_details(self) -> List[Dict[str, Any]]:
    """Get detailed information about failed sources.
    
    Returns:
        List of dicts with source name, failure time, and retry time
    """
    failed_details = []
    now = dt_util.now()
    
    for source_name, failure_time in self._failed_sources.items():
        if failure_time is not None:  # Source has failed
            # Calculate next health check time
            next_check = self._calculate_next_health_check(now)
            
            failed_details.append({
                "source": source_name,
                "failed_at": failure_time.isoformat(),
                "retry_at": next_check.isoformat() if next_check else None,
            })
    
    return sorted(failed_details, key=lambda x: x["source"])

def _calculate_next_health_check(self, from_time: datetime) -> Optional[datetime]:
    """Calculate when the next health check will occur.
    
    Returns the start of the next special hour window.
    """
    current_hour = from_time.hour
    today = from_time.date()
    
    # Check windows for today
    for start, end in Network.Defaults.SPECIAL_HOUR_WINDOWS:
        if current_hour < start:
            # Haven't reached this window yet today
            return from_time.replace(hour=start, minute=0, second=0, microsecond=0)
    
    # All windows passed for today, use first window tomorrow
    if Network.Defaults.SPECIAL_HOUR_WINDOWS:
        first_window_start = Network.Defaults.SPECIAL_HOUR_WINDOWS[0][0]
        tomorrow = today + timedelta(days=1)
        return from_time.replace(
            year=tomorrow.year,
            month=tomorrow.month,
            day=tomorrow.day,
            hour=first_window_start,
            minute=0,
            second=0,
            microsecond=0
        )
    
    return None
```

**Purpose:** Provides user-friendly information about when failed sources will be retried.

---

#### 1.6 Update `_process_result()` to include failed source details
**Location:** Line 693 (where validated_sources is added)

**Add after validated_sources:**
```python
# Add validated sources (what's been tested and working)
processed_data["validated_sources"] = self.get_validated_sources()

# ADD: Failed source details with timestamps
failed_source_details = self.get_failed_source_details()
if failed_source_details:
    processed_data["failed_sources"] = failed_source_details
```

**Note:** We don't add `last_health_check` or `next_health_check` at the top level - the per-source `failed_at` and `retry_at` provide all necessary timing information.

---

### 2. sensor/base.py - Update Attributes Display

**Location:** Lines 105-107 (current validated_sources display)

**Update to show failed sources:**
```python
# Show validated sources (what's been tested and working)
validated_sources = self.coordinator.data.get("validated_sources")
if validated_sources:
    source_info["validated_sources"] = validated_sources

# ADD: Show failed sources with details
failed_sources = self.coordinator.data.get("failed_sources")
if failed_sources:
    source_info["failed_sources"] = failed_sources
```

**Note:** We don't add `last_health_check` or `next_health_check` to attributes - the `retry_at` field in each failed source already shows when the next validation will occur.

---

### 3. Optional: First Boot Health Check

**Location:** `__init__.py`, line 68 (after first_refresh)

**Add background health check on first boot:**
```python
try:
    await coordinator.async_config_entry_first_refresh()
    
    # Schedule initial health check in background (non-blocking)
    if not coordinator.price_manager._health_check_scheduled:
        _LOGGER.info(f"Scheduling background health check for {area} on first boot")
        asyncio.create_task(coordinator.price_manager._schedule_health_check())
        coordinator.price_manager._health_check_scheduled = True
        
except Exception as e:
    ...
```

**Note:** This is **optional**. Without this, health check only starts after first failure or during next special window.

---

## Files to Modify

### Required Changes

1. ✅ `custom_components/ge_spot/coordinator/unified_price_manager.py`
   - Remove `_retry_scheduled` set
   - Add `_health_check_scheduled`, `_last_health_check`
   - Replace `_schedule_daily_retry()` with `_schedule_health_check()`
   - Add `_validate_all_sources()`
   - Add `get_failed_source_details()`
   - Add `_calculate_next_health_check()`
   - Update `fetch_data()` scheduling logic
   - Update `_process_result()` to include new attributes

2. ✅ `custom_components/ge_spot/sensor/base.py`
   - Add failed source details to attributes
   - Add health check timestamps

### Optional Changes

3. 🔵 `custom_components/ge_spot/__init__.py`
   - Add background health check on first boot

---

## Expected User-Visible Changes

### Sensor Attributes Before
```json
{
  "source_info": {
    "active_source": "nordpool",
    "validated_sources": ["nordpool"]
  }
}
```

### Sensor Attributes After
```json
{
  "source_info": {
    "active_source": "nordpool",
    "validated_sources": ["nordpool", "entsoe"],
    "failed_sources": [
      {
        "source": "energy_charts",
        "failed_at": "2025-10-10T17:36:42+02:00",
        "retry_at": "2025-10-11T13:00:00+02:00"
      }
    ]
  }
}
```

### Log Messages

**Health check starting:**
```
[NO] Daily health check starting in 1847s (validating 3 sources)
```

**During health check:**
```
[NO] Starting health check for 3 sources
[NO] Health check: 'nordpool' ✓ validated
[NO] Health check: 'entsoe' ✓ validated
[NO] Health check: 'energy_charts' ✗ failed: Connection timeout. Will retry during next daily health check. (2 other source(s) available)
```

**Health check complete:**
```
[NO] Health check complete: 2 validated, 1 failed. Validated: nordpool, entsoe. Failed: energy_charts
```

**Failed source recovery:**
```
[NO] Health check: 'energy_charts' ✓ validated
[NO] Health check complete: 3 validated, 0 failed. Validated: energy_charts, entsoe, nordpool. Failed: none
```

---

## Testing Plan

### Unit Tests

**File:** `tests/pytest/unit/test_unified_price_manager.py`

```python
@pytest.mark.asyncio
async def test_health_check_scheduled_on_failure(manager, auto_mock_core_dependencies):
    """Test that health check task is scheduled when all sources fail."""
    # Arrange
    mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
    mock_fallback.return_value = MOCK_FAILURE_RESULT
    
    # Act
    await manager.fetch_data()
    
    # Assert
    assert manager._health_check_scheduled is True

@pytest.mark.asyncio
async def test_health_check_only_scheduled_once(manager, auto_mock_core_dependencies):
    """Test that health check task is not scheduled multiple times."""
    # Arrange
    mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
    mock_fallback.return_value = MOCK_FAILURE_RESULT
    
    # Act - multiple failures
    await manager.fetch_data()
    await manager.fetch_data()
    await manager.fetch_data()
    
    # Assert - flag set once
    assert manager._health_check_scheduled is True
    # Only one task should be created (can't easily test asyncio.create_task count, 
    # but flag ensures we don't spam tasks)

@pytest.mark.asyncio
async def test_validate_all_sources_success(manager, auto_mock_core_dependencies):
    """Test _validate_all_sources marks all working sources as validated."""
    # Arrange
    mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
    mock_fallback.return_value = MOCK_SUCCESS_RESULT
    
    # Mark sources as failed first
    manager._failed_sources["nordpool"] = dt_util.now()
    manager._failed_sources["entsoe"] = dt_util.now()
    
    # Act
    await manager._validate_all_sources()
    
    # Assert - all sources cleared
    assert manager._failed_sources["nordpool"] is None
    assert manager._failed_sources["entsoe"] is None

@pytest.mark.asyncio
async def test_validate_all_sources_partial_failure(manager, auto_mock_core_dependencies):
    """Test _validate_all_sources handles mixed success/failure."""
    # Arrange
    mock_fallback = auto_mock_core_dependencies["fallback_manager"].return_value.fetch_with_fallback
    
    # First source succeeds, second fails
    mock_fallback.side_effect = [
        MOCK_SUCCESS_RESULT,  # nordpool success
        MOCK_FAILURE_RESULT   # entsoe failure
    ]
    
    # Act
    await manager._validate_all_sources()
    
    # Assert
    assert manager._failed_sources["nordpool"] is None  # Success
    assert manager._failed_sources["entsoe"] is not None  # Failed

def test_failed_source_details_format(manager):
    """Test get_failed_source_details returns correct format."""
    # Arrange
    now = dt_util.now()
    manager._failed_sources = {
        "nordpool": None,  # Working
        "energy_charts": now - timedelta(hours=2),  # Failed 2h ago
    }
    
    # Act
    details = manager.get_failed_source_details()
    
    # Assert
    assert len(details) == 1
    assert details[0]["source"] == "energy_charts"
    assert "failed_at" in details[0]
    assert "retry_at" in details[0]

def test_next_health_check_calculation(manager):
    """Test _calculate_next_health_check returns correct next window."""
    # Test at 12:00 - should return 13:00 (start of 13-15 window)
    test_time = dt_util.now().replace(hour=12, minute=0, second=0, microsecond=0)
    next_check = manager._calculate_next_health_check(test_time)
    assert next_check.hour == 13
    assert next_check.date() == test_time.date()
    
    # Test at 16:00 - should return next day 00:00 (first window)
    test_time = dt_util.now().replace(hour=16, minute=0, second=0, microsecond=0)
    next_check = manager._calculate_next_health_check(test_time)
    assert next_check.hour == 0
    assert next_check.date() == test_time.date() + timedelta(days=1)
```

### Integration Tests

**File:** `tests/pytest/integration/test_health_check_integration.py`

```python
@pytest.mark.asyncio
async def test_health_check_restores_failed_source(manager):
    """Test complete flow: failure → health check → restoration."""
    # 1. Normal fetch fails
    # 2. Source marked as failed
    # 3. Health check runs
    # 4. Source validates successfully
    # 5. Next fetch uses restored source
    
@pytest.mark.asyncio
async def test_priority_restored_after_validation(manager):
    """Test that source priority is correctly restored after validation."""
    # Primary fails → fallback used
    # Health check runs → primary validates
    # Next fetch → primary is tried first again
```

### Manual Testing Checklist

- [ ] Configure 3+ sources with different priorities
- [ ] Simulate primary source failure
  - [ ] Verify fallback works
  - [ ] Verify health check task scheduled
  - [ ] Check logs for scheduling message
- [ ] Wait for special hour window (or mock time)
  - [ ] Verify health check runs
  - [ ] Verify all sources attempted
  - [ ] Check logs for validation results
- [ ] Check sensor attributes
  - [ ] Verify `failed_sources` array format
  - [ ] Verify timestamps present
  - [ ] Verify `next_health_check` calculated correctly
- [ ] Simulate failed source recovery
  - [ ] Verify source marked as validated
  - [ ] Verify priority restored
  - [ ] Verify next fetch uses recovered source

---

## Migration & Compatibility

### Breaking Changes
- ❌ None - purely additive changes

### Behavioral Changes
- ✅ All sources validated daily (not just failed ones)
- ✅ Single health check task instead of per-source retry tasks
- ✅ Health check runs even if all sources are working
- ✅ Users see when sources were last validated
- ✅ Failed sources show detailed information (when failed, when retry)

### Backward Compatibility
- ✅ Existing `validated_sources` attribute unchanged
- ✅ Existing `_failed_sources` tracking mechanism unchanged
- ✅ Existing special hour window configuration unchanged
- ✅ No configuration changes required
- ✅ No cache format changes

### Performance Impact
- **API calls:** Same total number, just consolidated into one window
- **Memory:** Negligible (one flag + one timestamp)
- **CPU:** Negligible (one task instead of many)
- **Network:** Actually better - no race conditions from multiple tasks
- **User experience:** Better - complete source health visibility

---

## Complexity Estimate

### Code Changes
- **Lines added:** ~150
- **Lines removed:** ~30
- **Net change:** ~120 lines
- **Files modified:** 2 (required), 3 (with optional first-boot)

### Complexity Rating
**Low** - Clean refactoring with well-separated concerns

### Risk Assessment
- **Low risk:** Changes are isolated to health check logic
- **No breaking changes:** Purely additive
- **Easy rollback:** Remove health check task, restore per-source retry
- **Well tested:** Existing FallbackManager logic reused

---

## Implementation Checklist

### Phase 1: Core Implementation
- [ ] Update `unified_price_manager.py.__init__()` - Add new attributes
- [ ] Replace `_schedule_daily_retry()` with `_schedule_health_check()`
- [ ] Add `_validate_all_sources()` method
- [ ] Update `fetch_data()` scheduling logic
- [ ] Add `get_failed_source_details()` helper
- [ ] Add `_calculate_next_health_check()` helper
- [ ] Update `_process_result()` to include new attributes

### Phase 2: Sensor Updates
- [ ] Update `sensor/base.py` to show failed source details
- [ ] Update `sensor/base.py` to show health check timestamps

### Phase 3: Testing
- [ ] Write unit tests for health check scheduling
- [ ] Write unit tests for `_validate_all_sources()`
- [ ] Write unit tests for helper methods
- [ ] Write integration tests for complete flow
- [ ] Manual testing with real APIs

### Phase 4: Documentation
- [ ] Update docstrings
- [ ] Update code comments
- [ ] Add logging for debugging

### Phase 5: Optional
- [ ] Add first-boot health check in `__init__.py`
- [ ] Consider configuration option for health check window

---

## Open Questions

### 1. First Boot Behavior
**Question:** Should we run health check immediately on HA restart?

**Options:**
- A) Yes, in background (non-blocking) - Users see health status faster
- B) No, wait for scheduled window - Simpler, less API calls on restart

**Recommendation:** Option B for initial implementation, can add A later if requested

---

### 2. Health Check Frequency
**Question:** Is once per day sufficient?

**Options:**
- A) Once per day (current plan)
- B) Configurable (1-24 hours)
- C) Multiple checks per day

**Recommendation:** Option A - keeps it simple, 24h is reasonable for source health

---

### 3. Timeout Strategy for Health Check
**Question:** Should health check use same exponential backoff as normal fetch?

**Options:**
- A) Yes, use FallbackManager (2s → 6s → 18s per source) - **Current plan**
- B) Single attempt, shorter timeout (e.g., 10s)

**Recommendation:** Option A - Consistent behavior, accurate validation

**Time impact:** For 3 sources, max 78 seconds (3 × 26s) if all timeout. Acceptable since:
- It's a background task in low-traffic window
- Only runs once per day
- After completion, sleeps until next day's window

---

### 4. Failed Source Logging
**Question:** How should failed sources be reported?

**Options:**
- A) WARNING log + attributes (current plan) - Visible in HA logs, no UI spam
- B) ERROR log + persistent notification - More aggressive alerting
- C) DEBUG log + attributes only - Silent, check attributes to see status

**Recommendation:** Option A - Warning logs are visible but not alarming, attributes provide details

**Current logging:**
```python
_LOGGER.warning(f"[{self.area}] Health check: '{source_name}' ✗ failed: {e}")
```

---

### 5. Failed Source Display
**Question:** Show all failed sources or only recent (e.g., last 7 days)?

**Options:**
- A) Show all failed sources - **Current plan**
- B) Only show sources failed in last 7 days
- C) Configurable retention period

**Recommendation:** Option A - Since we retry daily, failed sources either recover or stay failed. No need for retention logic yet.

---

### 6. Health Check Cancellation
**Question:** Should health check task be cancellable?

**Options:**
- A) No, runs until coordinator shutdown - **Current plan**
- B) Add cancel method for testing/debugging

**Recommendation:** Option A initially. Task is benign and low-overhead.

---

## Success Criteria

### Functional Requirements
- ✅ Health check validates ALL configured sources once per day
- ✅ Health check runs during special hour windows
- ✅ Failed sources show detailed information in attributes
- ✅ Working sources are re-validated to confirm health
- ✅ Source priority automatically restored when failed source recovers

### Non-Functional Requirements
- ✅ No breaking changes to existing functionality
- ✅ No performance degradation
- ✅ Clean, maintainable code
- ✅ Comprehensive logging for debugging
- ✅ User-friendly attribute format

### User Experience
- ✅ User sees complete source health status
- ✅ User knows when sources were last checked
- ✅ User knows when failed sources will be retried
- ✅ Clear log messages for troubleshooting

---

## Future Enhancements (Not in Scope)

1. **Configurable health check schedule** - Allow users to set custom windows
2. **Health check on-demand** - Service call to trigger immediate validation
3. **Source health history** - Track success/failure trends over time
4. **Alerts/notifications** - Notify user when sources fail/recover
5. **Health check metrics** - Response times, success rates, etc.

---

## Questions for Discussion

1. Should we implement first-boot health check (optional Phase 5)?
2. Any concerns about the attribute format for `failed_sources`?
3. Should we add more logging levels (debug vs info vs warning)?
4. Any edge cases we should test specifically?
5. Should health check task have a maximum runtime cap?

---

**Status:** Ready for review and discussion
**Next Step:** Review plan, discuss questions, then proceed with implementation
