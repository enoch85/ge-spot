# Daily Health Check Feature

## Overview

The Daily Health Check feature provides comprehensive monitoring and validation of all configured price data sources in the GE-Spot integration. This feature ensures that backup sources are regularly tested and ready to take over if the primary source fails.

## Problem Solved

**Before:** Only failed sources were retried during special hour windows. Working sources were never re-validated, leaving users unaware of whether their backup sources were functional.

**Example scenario:**
```
Priority: Nordpool → ENTSOE → Energy Charts
Nordpool always works → ENTSOE and Energy Charts NEVER validated
User has no idea if fallback sources are healthy
```

**After:** All sources are validated daily during special hour windows, providing complete visibility into source health status.

## Key Features

### 1. Consolidated Daily Health Check
- **Single task** validates all configured sources once per day
- Runs during configured special hour windows (default: 00:00-01:00 and 13:00-15:00)
- Random delay (0-3600 seconds) spreads load across the hour
- Independent validation of each source (doesn't stop at first success)

### 2. Complete Source Validation
- **All sources tested**, not just failed ones
- Each source validated with exponential backoff (5s → 15s → 45s)
- Success clears failure timestamp
- Failure marks source with timestamp for 24-hour skip

### 3. User Visibility
- **Validated sources** shown in sensor attributes
- **Failed sources** displayed with detailed information:
  - Source name
  - Failure timestamp (`failed_at`)
  - Next retry time (`retry_at`)

## Architecture

### Components

#### 1. Health Check Scheduler (`_schedule_health_check`)
```python
async def _schedule_health_check(self):
    """Validates all configured sources once per day during special hours."""
```

- Runs continuously in background
- Checks hourly if in special hour window
- Executes health check once per day
- Sleeps between checks

#### 2. Source Validator (`_validate_all_sources`)
```python
async def _validate_all_sources(self):
    """Validate ALL configured sources independently."""
```

- Creates API instances for each source
- Uses FallbackManager for exponential backoff
- Updates `_failed_sources` dictionary
- Logs validation results

#### 3. Helper Methods

**`get_failed_source_details()`**
- Returns list of failed sources with timestamps
- Calculates next retry time for each

**`_calculate_next_health_check()`**
- Determines next special hour window
- Handles day boundaries

### Data Flow

```
Normal Fetch Failure
        ↓
Mark source as failed
        ↓
Schedule health check task (if not running)
        ↓
Wait for special hour window
        ↓
Random delay (0-3600s)
        ↓
Validate ALL sources independently
        ↓
Update _failed_sources dictionary
        ↓
Log summary (validated vs failed)
        ↓
Sleep until next day
```

## Configuration

### Special Hour Windows

Defined in `const/network.py`:

```python
SPECIAL_HOUR_WINDOWS = [
    (0, 1),   # 00:00-01:00 - For today's new prices
    (13, 15), # 13:00-15:00 - For tomorrow's data
]
```

### Validation Retry Settings

Defined in `const/time.py`:

```python
class ValidationRetry:
    MAX_RANDOM_DELAY_SECONDS = 3600  # Random delay within retry window
    RETRY_CHECK_INTERVAL_SECONDS = 1800  # 30 minutes
```

## User-Visible Changes

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

## Log Messages

### Health Check Starting
```
[NO] Daily health check starting in 1847s (validating 3 sources)
```

### During Validation
```
[NO] Starting health check for 3 sources
[NO] Health check: 'nordpool' ✓ validated
[NO] Health check: 'entsoe' ✓ validated
[NO] Health check: 'energy_charts' ✗ failed: Connection timeout. 
     Will retry during next daily health check. (2 other source(s) available)
```

### Health Check Complete
```
[NO] Health check complete: 2 validated, 1 failed. 
     Validated: nordpool, entsoe. Failed: energy_charts
```

### Source Recovery
```
[NO] Health check: 'energy_charts' ✓ validated
[NO] Health check complete: 3 validated, 0 failed. 
     Validated: energy_charts, entsoe, nordpool. Failed: none
```

## Behavioral Changes

### Before Implementation
- ❌ Only failed sources retried
- ❌ Multiple retry tasks (one per failed source)
- ❌ Working sources never re-validated
- ❌ No visibility into backup source health

### After Implementation
- ✅ All sources validated daily
- ✅ Single consolidated health check task
- ✅ Working sources regularly tested
- ✅ Complete source health visibility
- ✅ Failed sources show retry schedule

## Performance Impact

### API Calls
- **Same total number** of calls, just consolidated into one window
- Spread over 0-3600 seconds with random delay
- Uses existing exponential backoff (5s → 15s → 45s per source)

### Memory
- **Negligible**: One boolean flag + one timestamp
- Removed per-source retry task tracking

### CPU
- **Improved**: Single task instead of multiple
- No race conditions from concurrent tasks

### Network
- **Better**: Coordinated validation prevents overlapping requests

## Technical Details

### Failed Source Tracking

```python
# Dictionary maps source name to last failure time
_failed_sources = {
    "nordpool": None,  # Working (None = no failure)
    "energy_charts": datetime(2025, 10, 10, 17, 36, 42),  # Failed
}
```

### Source Filtering (24-hour Skip)

During normal fetch operations, sources that failed within the last 24 hours are skipped:

```python
# Filter out recently failed sources (within last 24 hours)
for cls in self._api_classes:
    source_name = cls(config={}).source_type
    last_failure = self._failed_sources.get(source_name)
    
    # Skip if failed recently (unless force=True)
    if not force and last_failure and (now - last_failure).total_seconds() < 86400:
        continue
```

### Health Check Scheduling

Health check is scheduled when all sources fail:

```python
# Mark attempted sources as failed
if self._attempted_sources:
    for source_name in self._attempted_sources:
        self._failed_sources[source_name] = now
    
    # Schedule health check task (once)
    if not self._health_check_scheduled:
        asyncio.create_task(self._schedule_health_check())
        self._health_check_scheduled = True
```

## Testing

### Unit Tests

Six comprehensive tests cover all functionality:

1. **`test_health_check_scheduled_on_failure`**
   - Verifies health check task is scheduled when all sources fail
   
2. **`test_health_check_only_scheduled_once`**
   - Ensures no duplicate health check tasks created
   
3. **`test_validate_all_sources_success`**
   - Tests that all sources are marked as validated on success
   
4. **`test_validate_all_sources_partial_failure`**
   - Verifies handling of mixed success/failure results
   
5. **`test_failed_source_details_format`**
   - Validates the structure of failed source details
   
6. **`test_next_health_check_calculation`**
   - Tests calculation of next retry window

### Test Coverage

- ✅ All 20 tests passing
- ✅ Task cleanup prevents lingering background tasks
- ✅ Existing tests updated for new architecture

## Migration Notes

### Breaking Changes
- **None** - Purely additive changes

### Compatibility
- ✅ Existing `validated_sources` attribute unchanged
- ✅ Existing `_failed_sources` tracking mechanism unchanged
- ✅ No configuration changes required
- ✅ No cache format changes

### Upgrade Path
1. Update code to latest version
2. Restart Home Assistant
3. Health check automatically scheduled on first source failure
4. Check sensor attributes for `failed_sources` array

## Troubleshooting

### Health Check Not Running

**Check logs for:**
```
[AREA] Scheduling daily health check task (will validate all X sources)
```

**Verify:**
- At least one source has failed previously
- Current time is outside special hour windows (won't run until next window)

### Sources Not Being Validated

**Check logs for:**
```
[AREA] Starting health check for X sources
```

**Verify:**
- Health check task is scheduled
- Current time is within special hour windows
- No exceptions in logs during validation

### Failed Sources Not Shown in Attributes

**Verify:**
- Source actually failed (check logs)
- Failure occurred less than 24 hours ago
- Sensor state has been updated (wait for next coordinator refresh)

## Future Enhancements

Potential improvements not in current scope:

1. **Configurable health check schedule** - Allow users to set custom windows
2. **Health check on-demand** - Service call to trigger immediate validation
3. **Source health history** - Track success/failure trends over time
4. **Alerts/notifications** - Notify user when sources fail/recover
5. **Health check metrics** - Response times, success rates, etc.
6. **First-boot health check** - Validate all sources immediately on HA restart

## Code References

### Key Files Modified

- `custom_components/ge_spot/coordinator/unified_price_manager.py`
  - `_schedule_health_check()` - Main scheduler
  - `_validate_all_sources()` - Source validator
  - `get_failed_source_details()` - Helper for failed sources
  - `_calculate_next_health_check()` - Calculate next window
  
- `custom_components/ge_spot/sensor/base.py`
  - Updated attributes to show failed sources

### Constants Used

- `Network.Defaults.SPECIAL_HOUR_WINDOWS` - Retry windows
- `ValidationRetry.MAX_RANDOM_DELAY_SECONDS` - Random delay
- `TimeInterval` methods - Interval calculations

## Related Documentation

- [Architecture Overview](../README.md#architecture)
- [Source Configuration](../custom_components/ge_spot/const/sources.py)
- [Network Constants](../custom_components/ge_spot/const/network.py)
- [Testing Guide](../tests/README.md)

## Version History

- **v1.0** (2025-10-10) - Initial implementation
  - Replaced per-source retry with daily health check
  - Added comprehensive source validation
  - Added failed source details to attributes
  - All tests passing (20/20)

---

**Status:** ✅ Production Ready  
**Tests:** ✅ All Passing (20/20)  
**Documentation:** ✅ Complete
