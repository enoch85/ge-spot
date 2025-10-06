# Timezone Fix: Data Validity Timestamps

## Issue

User reported that sensor attributes showed incorrect timezone for `data_valid_until` and `last_valid_interval` timestamps when using "Local Area Time" setting.

**Example:**
- Setting: "Local Area Time" (show prices in area's timezone)
- Area: AEMO NSW1 (Sydney, Australia +11:00)
- Home Assistant: Europe/Berlin (+02:00)
- **Bug**: `data_valid_until: '2025-10-07T04:15:00+02:00'` ❌ (Berlin timezone)
- **Expected**: `data_valid_until: '2025-10-07T04:15:00+11:00'` ✅ (Sydney timezone)

## Root Cause

`calculate_data_validity()` in `coordinator/data_validity.py` was using `dt_util.as_local()` which **always converts to Home Assistant's timezone**, ignoring the user's time reference setting.

```python
# OLD CODE (WRONG)
interval_dt = dt_util.as_local(interval_dt)  # Always HA timezone
```

This created a semantic mismatch:
- Interval keys like `"04:15"` represent times in **target timezone** (e.g., Sydney)
- But timestamps were localized in **HA timezone** (e.g., Berlin)

## Solution

Added `target_timezone` parameter to `calculate_data_validity()` and use it to localize timestamps in the correct timezone.

```python
# NEW CODE (CORRECT)
if target_timezone:
    tz = pytz.timezone(target_timezone)
    interval_dt = tz.localize(interval_dt)
else:
    interval_dt = dt_util.as_local(interval_dt)  # Fallback to HA timezone
```

## Files Changed

### 1. `custom_components/ge_spot/coordinator/data_validity.py`

**Changes:**
- Added `target_timezone: Optional[str] = None` parameter
- Added `from typing import Dict` import (was missing)
- Use `pytz.timezone(target_timezone).localize()` instead of `dt_util.as_local()`
- Applied to both today's and tomorrow's intervals

### 2. `custom_components/ge_spot/coordinator/data_processor.py`

**Changes:**
- Get target timezone: `target_timezone = str(self._tz_service.target_timezone)`
- Pass to calculate_data_validity: `target_timezone=target_timezone`
- Added comment: "The interval_prices keys are already in target_timezone"

### 3. `custom_components/ge_spot/coordinator/unified_price_manager.py`

**Changes:**
- Get target timezone from service
- Pass to calculate_data_validity when calculating from cache
- Added comment: "Cached interval keys are in target_timezone"

## Why This Fix is Correct

### Data Flow Understanding

1. **API Returns**: Data in source timezone (e.g., Sydney +11:00)
   ```python
   # AEMO API returns:
   interval_raw = {"2025-10-07T03:00:00+11:00": 124.96}
   ```

2. **TimezoneConverter Converts**: Source → Target timezone
   ```python
   # Line 97 of timezone_converter.py:
   target_dt = dt.astimezone(self._tz_service.target_timezone)
   
   # Line 105: Create key AFTER conversion
   target_key = f"{target_dt.hour:02d}:{target_dt.minute:02d}"
   ```

3. **Keys Represent Target Timezone**: After conversion
   ```python
   # interval_prices keys are in target_timezone:
   interval_prices = {"03:00": 12.49}  # "03:00" in Sydney time
   ```

4. **data_validity Must Match**: Use same timezone as keys
   ```python
   # Must localize in the timezone the keys represent
   tz = pytz.timezone(target_timezone)  # Sydney
   interval_dt = tz.localize(interval_dt)  # 03:00 Sydney
   ```

### Time Reference Modes

**Local Area Time:**
- `target_timezone` = Area's timezone (e.g., Sydney)
- Keys: Times in Sydney
- Validity: Timestamps in Sydney ✅

**Home Assistant Time:**
- `target_timezone` = HA's timezone (e.g., Berlin)
- Keys: Times in Berlin (converted from Sydney)
- Validity: Timestamps in Berlin ✅

## Verification

### Unit Tests
- ✅ All 104 unit tests pass

### Integration Tests
- ✅ ComEd full chain test passes
- ✅ Nordpool full chain test passes
- ✅ Energi Data full chain test passes
- ✅ OMIE full chain test passes

### Multi-Source Testing

Verified with live data from multiple APIs with different source timezones:

| Source | Source TZ | Target TZ | HA TZ | Result |
|--------|-----------|-----------|-------|--------|
| AEMO | Sydney +11 | Sydney +11 | Berlin +2 | ✅ Validity in +11:00 |
| AEMO | Sydney +11 | Berlin +2 | Berlin +2 | ✅ Validity in +02:00 |
| ComEd | Chicago -5 | Chicago -5 | NY -4 | ✅ Validity in -05:00 |
| ComEd | Chicago -5 | NY -4 | NY -4 | ✅ Validity in -04:00 |

**Pattern:** NEW fix is always correct. OLD code only worked when `target_tz = HA_tz` (by luck).

## Impact

- **Minimal**: Only 3 files changed, 2 callers updated
- **Safe**: All existing tests pass
- **Correct**: Fixes semantic mismatch between keys and timestamps
- **Complete**: Works for all API sources and timezone combinations

## Migration Notes

No migration needed. The change is backward compatible:
- If `target_timezone` not provided, falls back to `dt_util.as_local()` (old behavior)
- All callers updated to pass `target_timezone`
- Cache continues to work (keys already in target timezone)
