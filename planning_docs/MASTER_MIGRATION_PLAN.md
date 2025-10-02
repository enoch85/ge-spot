# 15-Minute Interval Migration - Master Plan

**Date:** October 2, 2025  
**Branch:** 15min  
**Status:** ✅ PHASE 12 COMPLETE - Testing Updated | Phase 13 (Documentation) Remaining

> **Single comprehensive document for the entire migration**

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Why This Change](#why-this-change)
3. [Impact Analysis](#impact-analysis)
4. [Architecture Design](#architecture-design)
5. [Implementation Plan](#implementation-plan)
6. [File-by-File Checklist](#file-by-file-checklist)
7. [Code Patterns & Examples](#code-patterns--examples)
8. [Testing Strategy](#testing-strategy)
9. [Progress Tracking](#progress-tracking)

---

## Executive Summary

### Objective
Migrate GE-Spot from hourly (60-minute) electricity price intervals to 15-minute intervals with a **configuration-driven, generic architecture** that makes future interval changes trivial.

### Scope
- **Files:** 40+ Python files to modify
- **Variables:** 415+ occurrences of hour-related code
- **Tests:** 196+ test assertions to update
- **Data:** 4x increase (24 → 96 data points per day)

### Key Innovation
**Change ONE constant to control everything:**
```python
TimeInterval.DEFAULT = QUARTER_HOURLY  # ← Single point of control!
```

Everything auto-adapts: duration, counts, formats, DST handling, statistics.

### Timeline
- **Estimated:** 10-15 hours of focused development
- **10 Phases:** From core constants to documentation
- **24 TODOs:** Each with clear deliverables

---

## Why This Change

### Market Context
Swedish electricity market (and EU) now prices electricity every **15 minutes** instead of hourly, starting **October 1, 2025**. This is EU legislation to handle variations in renewable energy (wind/solar) more effectively.

### User Impact
- ✅ More accurate pricing data (4x granularity)
- ✅ Better optimization opportunities
- ✅ Real-time adaptation to market changes
- ✅ Aligns with ENEQUI Core's 15-minute intervals

### Technical Benefits
- ✅ **Future-proof:** Easy to change to any interval (5-min, 30-min)
- ✅ **Configuration-driven:** Single point of control
- ✅ **Generic naming:** No hardcoded assumptions
- ✅ **Testable:** Can switch between modes easily

---

## Impact Analysis

### Quantitative Assessment

**Code Statistics:**
- **"hourly" occurrences:** 389 in Python files
- **"hour" occurrences:** 734+ in Python files
- **Key variables:** 415+ (hour_key, hourly_prices, next_hour_price, etc.)
- **Test assertions:** 196+ updates needed
- **Files affected:** 40+ Python files

**Data Changes:**
| Aspect | Current | New | Change |
|--------|---------|-----|--------|
| Data points/day | 24 | 96 | 4x |
| Update interval | 30 min | 15 min | 2x faster |
| Format | "HH:00" | "HH:MM" | All minutes |
| DST spring | 23 hours | 92 intervals | 4x |
| DST fall | 25 hours | 100 intervals | 4x |

### Critical Code Patterns Found

**1. Hardcoded Loops (MUST FIX):**
```python
# Found in 3 files:
range(24)  # timezone/service.py (2x), timezone_provider.py (1x)
[f"{h:02d}:00" for h in range(24)]  # Hardcoded hour generation
```

**2. Hardcoded Format Strings (MUST FIX):**
```python
# Found in multiple files:
f"{dt.hour:02d}:00"  # Hardcoded :00 minutes
"%H:00"  # Format string assumes hourly
```

**3. Datetime Property Usage (REVIEW):**
```python
# Found in 32 files using timedelta
# Found in 20+ places using .hour and .minute properties
```

**4. Time Interval Constants:**
```python
# Already exists! ✅
TimeInterval.QUARTER_HOURLY = "PT15M"  
TimeInterval.HOURLY = "PT60M"
```

### Files by Category

#### Core Time Infrastructure (8 files) - Priority 1
1. `const/time.py` - Time constants and interval config
2. `const/defaults.py` - Default update interval
3. `timezone/hour_calculator.py` → `interval_calculator.py` - **RENAME FILE**
4. `timezone/service.py` - Uses HourCalculator, has hardcoded range(24)
5. `timezone/__init__.py` - Exports HourCalculator
6. `timezone/timezone_provider.py` - Has hardcoded range(24)
7. `api/base/data_structure.py` - HourlyPrice class
8. `api/base/base_price_api.py` - Base API

#### Parsers (9 files) - Priority 2
9. `api/parsers/entsoe_parser.py` - ✅ Already supports PT15M!
10. `api/parsers/nordpool_parser.py` - Check 15-min support
11. `api/parsers/epex_parser.py` - Needs expansion
12. `api/parsers/omie_parser.py` - Needs expansion
13. `api/parsers/comed_parser.py` - Needs expansion
14. `api/parsers/stromligning_parser.py` - Needs expansion
15. `api/parsers/energi_data_parser.py` - Check 15-min support
16. `api/parsers/amber_parser.py` - May have 5-min data
17. `api/parsers/aemo_parser.py` - May have 5-min data

#### API Implementations (9 files) - Priority 2
18. `api/aemo.py`
19. `api/amber.py`
20. `api/comed.py`
21. `api/entsoe.py`
22. `api/epex.py`
23. `api/nordpool.py`
24. `api/omie.py`
25. `api/energi_data.py`
26. `api/stromligning.py`

#### Coordinator & Processing (8 files) - Priority 3
27. `coordinator/data_processor.py` - Processes hourly_prices
28. `coordinator/unified_price_manager.py`
29. `coordinator/cache_manager.py`
30. `coordinator/fetch_decision.py`
31. `price/statistics.py`
32. `price/formatter.py`
33. `price/currency_converter.py`
34. `price/__init__.py` - Has self.hourly_prices

#### Sensors (3 files) - Priority 3
35. `sensor/base.py`
36. `sensor/price.py` - next_hour_price property
37. `sensor/electricity.py`

#### Utilities (5+ files) - Priority 4
38. `utils/timezone_converter.py` - Has hardcoded :00 format
39. `utils/date_range.py` - Has 15-min rounding logic (good!)
40. `utils/rate_limiter.py` - Uses .hour property
41. `utils/data_validator.py`
42. `utils/validation/data_validator.py`

#### Config & Translations (4+ files) - Priority 4
43. `translations/en.json`
44. `translations/strings.json`
45. `config_flow.py`
46. `config_flow/*.py` files

#### Tests (15+ files) - Priority 5
47. All integration test files
48. All unit test files
49. All manual test files

---

## Architecture Design

### Configuration-Driven Approach

#### Single Point of Control
```python
# File: const/time.py
class TimeInterval:
    """Time interval constants - easily configurable."""
    HOURLY = "PT60M"
    QUARTER_HOURLY = "PT15M"
    DAILY = "P1D"
    
    # ⭐ CHANGE ONLY THIS LINE:
    DEFAULT = QUARTER_HOURLY
    
    # Everything else auto-calculates:
    @staticmethod
    def get_interval_minutes() -> int:
        """Get interval duration in minutes."""
        if TimeInterval.DEFAULT == TimeInterval.QUARTER_HOURLY:
            return 15
        elif TimeInterval.DEFAULT == TimeInterval.HOURLY:
            return 60
        return 15
    
    @staticmethod
    def get_intervals_per_hour() -> int:
        """Get number of intervals per hour."""
        return 60 // TimeInterval.get_interval_minutes()
    
    @staticmethod
    def get_intervals_per_day() -> int:
        """Get number of intervals per day."""
        return 24 * TimeInterval.get_intervals_per_hour()
    
    @staticmethod
    def get_intervals_per_day_dst_spring() -> int:
        """Get intervals for DST spring forward day (lose 1 hour)."""
        return TimeInterval.get_intervals_per_day() - TimeInterval.get_intervals_per_hour()
    
    @staticmethod
    def get_intervals_per_day_dst_fall() -> int:
        """Get intervals for DST fall back day (gain 1 hour)."""
        return TimeInterval.get_intervals_per_day() + TimeInterval.get_intervals_per_hour()
```

#### Why This Approach?
1. ✅ **Single source of truth** - Change one value, everything adapts
2. ✅ **No hardcoded values** - All calculations derive from DEFAULT
3. ✅ **Easy testing** - Switch between HOURLY and QUARTER_HOURLY
4. ✅ **Future-proof** - Add new intervals without code changes
5. ✅ **Self-documenting** - Clear intent and purpose

### Generic Naming Convention

| ❌ Bad (Hour-specific) | ✅ Good (Generic) | Why? |
|------------------------|-------------------|------|
| `hourly_prices` | `interval_prices` | Works for any duration |
| `HourlyPrice` | `IntervalPrice` | Not tied to hours |
| `HourCalculator` | `IntervalCalculator` | Generic calculator |
| `hour_key` | `interval_key` | Generic identifier |
| `next_hour_price` | `next_interval_price` | Any interval |
| `current_hour_key` | `current_interval_key` | Any interval |
| `get_current_hour_key()` | `get_current_interval_key()` | Generic method |
| `normalize_hourly_prices()` | `normalize_interval_prices()` | Generic function |
| `"HH:00"` format | `"HH:MM"` format | All minutes |
| `"%H:00"` | `"%H:%M"` | All minutes |

### API Expansion Strategy

For APIs that only provide hourly data:

```python
def expand_to_intervals(hourly_data: Dict[str, float]) -> Dict[str, float]:
    """
    Expand hourly prices to match configured interval.
    
    Generic implementation - works for any interval duration.
    Configuration-driven using TimeInterval.get_interval_minutes().
    
    Example:
        Input:  {"14:00": 50.0, "15:00": 55.0}
        Output: {"14:00": 50.0, "14:15": 50.0, "14:30": 50.0, "14:45": 50.0,
                 "15:00": 55.0, "15:15": 55.0, "15:30": 55.0, "15:45": 55.0}
    """
    interval_minutes = TimeInterval.get_interval_minutes()
    
    if interval_minutes == 60:
        return hourly_data  # Already hourly
    
    intervals_per_hour = TimeInterval.get_intervals_per_hour()
    expanded = {}
    
    for hour_key, price in hourly_data.items():
        hour = int(hour_key.split(':')[0])
        for i in range(intervals_per_hour):
            minute = i * interval_minutes
            interval_key = f"{hour:02d}:{minute:02d}"
            expanded[interval_key] = price
    
    return expanded
```

**API Status:**
- ✅ **ENTSO-E:** Already supports PT15M (priority 1)
- ❓ **NordPool:** Likely supports 15-min as of Oct 1, 2025 (check)
- ❌ **EPEX, OMIE, ComEd, Stromligning:** Hourly only (use expansion)
- ❓ **Amber, AEMO:** May have 5-min data (check)
- ❓ **Energi Data:** Check for 15-min support

---

## Implementation Plan

### Phase 1: Core Constants & Time Handling (Priority 1)

**Files:** `const/time.py`, `const/defaults.py`

#### TODO-001: Implement configuration-driven interval system
**File:** `const/time.py`

**Changes:**
1. Change `TimeInterval.DEFAULT` from `HOURLY` to `QUARTER_HOURLY`
2. Add static helper methods:
   - `get_interval_minutes()` → Returns 15 or 60
   - `get_intervals_per_hour()` → Returns 4 or 1
   - `get_intervals_per_day()` → Returns 96 or 24
   - `get_intervals_per_day_dst_spring()` → Returns 92 or 23
   - `get_intervals_per_day_dst_fall()` → Returns 100 or 25

**Validation:**
```python
# Test that helper methods work
assert TimeInterval.get_interval_minutes() == 15
assert TimeInterval.get_intervals_per_hour() == 4
assert TimeInterval.get_intervals_per_day() == 96
```

#### TODO-002: Update default update interval
**File:** `const/defaults.py`

**Changes:**
1. Line ~11: Change `UPDATE_INTERVAL = 30` → `UPDATE_INTERVAL = 15`

**Validation:**
- No import errors
- Constants accessible from other modules

---

### Phase 2: Time Calculator Refactoring (Priority 1)

**Files:** `timezone/hour_calculator.py` → `interval_calculator.py`, `timezone/service.py`, `timezone/__init__.py`

#### TODO-003: Rename HourCalculator → IntervalCalculator
**File:** `timezone/hour_calculator.py` → `interval_calculator.py`

**Changes:**
1. Rename file: `hour_calculator.py` → `interval_calculator.py`
2. Rename class: `HourCalculator` → `IntervalCalculator`
3. Rename methods:
   - `get_current_hour_key()` → `get_current_interval_key()`
   - `get_next_hour_key()` → `get_next_interval_key()`
   - `get_hour_key_for_datetime()` → `get_interval_key_for_datetime()`
4. Update all docstrings to be generic (remove "hour" references)

#### TODO-004: Update interval calculation logic
**File:** `timezone/interval_calculator.py`

**Changes:**
1. Add new method: `_round_to_interval(dt: datetime) -> datetime`
   ```python
   def _round_to_interval(self, dt: datetime) -> datetime:
       """Round datetime to nearest interval boundary."""
       interval_minutes = TimeInterval.get_interval_minutes()
       minute = (dt.minute // interval_minutes) * interval_minutes
       return dt.replace(minute=minute, second=0, microsecond=0)
   ```

2. Update `get_current_interval_key()`:
   ```python
   def get_current_interval_key(self) -> str:
       """Get the current interval key formatted as HH:MM."""
       now = dt_util.now(self.timezone)
       rounded = self._round_to_interval(now)
       # ... timezone logic ...
       return f"{rounded.hour:02d}:{rounded.minute:02d}"
   ```

3. Update `get_next_interval_key()`:
   ```python
   def get_next_interval_key(self) -> str:
       """Get the next interval key formatted as HH:MM."""
       now = dt_util.now(self.timezone)
       rounded = self._round_to_interval(now)
       interval_minutes = TimeInterval.get_interval_minutes()
       next_interval = rounded + timedelta(minutes=interval_minutes)
       return f"{next_interval.hour:02d}:{next_interval.minute:02d}"
   ```

4. Update DST handling to use new interval count methods

**Update imports:**
- `timezone/service.py` line 18: `from .hour_calculator import HourCalculator` → `from .interval_calculator import IntervalCalculator`
- `timezone/service.py` line 71: `self.hour_calculator = HourCalculator(...)` → `self.interval_calculator = IntervalCalculator(...)`
- `timezone/__init__.py` line 7: Update export

**Fix hardcoded range(24):**
- `timezone/service.py` lines 275, 280: Replace `range(24)` with dynamic generation
  ```python
  # OLD:
  return [f"{hour:02d}:00" for hour in range(24)]
  
  # NEW:
  interval_minutes = TimeInterval.get_interval_minutes()
  intervals_per_hour = TimeInterval.get_intervals_per_hour()
  result = []
  for hour in range(24):
      for i in range(intervals_per_hour):
          minute = i * interval_minutes
          result.append(f"{hour:02d}:{minute:02d}")
  return result
  ```

- `timezone/timezone_provider.py` line 314: Update timedelta loop

**Validation:**
- IntervalCalculator returns "HH:MM" format keys
- Keys include :00, :15, :30, :45 for 15-min mode
- DST handling works correctly

---

### Phase 3: Data Structures (Priority 1)

**Files:** `api/base/data_structure.py`

#### TODO-005: Rename HourlyPrice → IntervalPrice
**Changes:**
1. Rename class: `HourlyPrice` → `IntervalPrice`
2. Rename field: `hour_key: str` → `interval_key: str`
3. Update docstring: "Hourly price data" → "Price data for a single time interval"
4. Update comment: "Format: HH:00" → "Format: HH:MM"

#### TODO-006: Update StandardizedPriceData
**Changes:**
1. Rename field: `hourly_prices` → `interval_prices`
2. Update comment: "Key: HH:00, Value: price" → "Key: HH:MM, Value: price"
3. Rename field: `raw_prices: List[HourlyPrice]` → `raw_prices: List[IntervalPrice]`
4. Rename field: `next_hour_price` → `next_interval_price`
5. Rename field: `current_hour_key` → `current_interval_key`
6. Rename field: `next_hour_key` → `next_interval_key`
7. Update `to_dict()` method to use new field names
8. Update all docstrings

**Validation:**
- No import errors
- Data structures serialize/deserialize correctly

---

### Phase 4: API Base & Expansion (Priority 2)

**Files:** `api/base/base_price_api.py`, `api/base/price_parser.py`, `api/utils.py`

#### TODO-007: Update base API
**Changes:**
1. Update all docstrings: "hourly" → "interval"
2. Update variable names throughout
3. Update method comments

#### TODO-008: Create generic expansion utility
**Location:** `api/utils.py` or `api/base/expansion.py`

**Create new function:**
```python
def expand_to_intervals(hourly_data: Dict[str, float]) -> Dict[str, float]:
    """
    Expand hourly prices to match configured interval.
    
    Generic implementation - automatically adapts to TimeInterval.DEFAULT.
    For APIs that provide hourly data but system needs finer granularity,
    duplicate the hourly price across all intervals in that hour.
    
    Args:
        hourly_data: Dictionary with hour keys and prices
        
    Returns:
        Dictionary with interval keys and prices
        
    Example:
        >>> expand_to_intervals({"14:00": 50.0})
        {"14:00": 50.0, "14:15": 50.0, "14:30": 50.0, "14:45": 50.0}
    """
    interval_minutes = TimeInterval.get_interval_minutes()
    
    if interval_minutes == 60:
        return hourly_data  # Already hourly, no expansion
    
    intervals_per_hour = TimeInterval.get_intervals_per_hour()
    expanded = {}
    
    for hour_key, price in hourly_data.items():
        try:
            hour = int(hour_key.split(':')[0])
        except (ValueError, IndexError):
            # If key isn't in expected format, keep as-is
            expanded[hour_key] = price
            continue
            
        for i in range(intervals_per_hour):
            minute = i * interval_minutes
            interval_key = f"{hour:02d}:{minute:02d}"
            expanded[interval_key] = price
    
    return expanded
```

**Validation:**
- Function works for both hourly and 15-min modes
- Handles edge cases gracefully

---

### Phase 5: Parser Updates (Priority 2)

**Files:** All 9 parser files in `api/parsers/`

#### TODO-009: Update parser implementations

**For EACH parser:**

1. **Update variable names:**
   - `hourly_prices` → `interval_prices`
   - `hourly_raw` → `interval_raw`
   - `hour_key` → `interval_key`

2. **Check API capabilities:**
   - Does API provide 15-min data natively?
   - If yes: Parse directly to interval_prices
   - If no: Parse to hourly, then use `expand_to_intervals()`

3. **Specific updates:**

**ENTSO-E Parser** (`entsoe_parser.py`):
- ✅ Already supports PT15M!
- Line 159: Already has `resolution_preference = ["PT60M", "PT30M", "PT15M"]`
- **Change:** Reorder to `["PT15M", "PT30M", "PT60M"]` (prioritize 15-min)
- Update variable names: `hourly_*` → `interval_*`

**NordPool Parser** (`nordpool_parser.py`):
- Check if API now provides 15-min data (likely yes as of Oct 1, 2025)
- If yes: Parse 15-min data directly
- If no: Use `expand_to_intervals()` on hourly data
- Update variable names

**Other Parsers** (EPEX, OMIE, ComEd, Stromligning, Energi Data):
- Update variable names
- Apply `expand_to_intervals()` if API only provides hourly
- Test with real API data

**Amber/AEMO Parsers**:
- Check if they provide sub-hourly data (possibly 5-min)
- May need different handling

**Validation:**
- Each parser outputs `interval_prices` dict
- Keys are in "HH:MM" format
- Data count is correct (96 for full day)

##### API Data Resolution Snapshot (October 2025)

| Source | Native Resolution | Migration Action | Status |
|--------|-------------------|------------------|--------|
| ENTSO-E | PT15M / PT30M / PT60M | Prioritise PT15M in `resolution_preference` and ensure naming updates | ✅ Native support already in place |
| Nord Pool | Transitioning to 15-minute MTU | Detect actual feed; expand hourly data with `expand_to_intervals()` if necessary | ⚠️ Verify per market on first run |
| EPEX | 15-minute products | Confirm timestamp handling and naming updates | ✅ Parser already handles 15-min data |
| OMIE | Hourly only | Use `expand_to_intervals()` at API layer to fan out to configured interval | 🔧 Required |
| ComEd | 5-minute | Aggregate to 15-minute intervals before returning `interval_raw` | ✅ Fixed in Phase 5 critical patch |
| Stromligning | Hourly | Use `expand_to_intervals()` in API implementation | 🔧 Required |
| Energi Data | Hourly (`HourUTC`/`HourDK`) | Use `expand_to_intervals()` in API implementation | 🔧 Required |
| Amber | 30-minute (NEM) | Accept 30-minute intervals; document limitation | ✅ Accept as-is |
| AEMO | 5-minute dispatch | Aggregate to 15-minute intervals before exposing `interval_raw` | ✅ Fixed in Phase 5 critical patch |

##### Critical Parser Fixes Already Landed

- **ComEd:** Switched aggregation from 5-min → hourly (data loss) to 5-min → 15-min using the new helper, preserving granularity.
- **AEMO:** Removed destructive hour-rounding and introduced 5-min → 15-min aggregation so dispatch data remains accurate.
- These fixes ensure integration tests and downstream APIs receive true 15-minute interval data instead of averaged hourly values.

---

### Phase 6: API Implementations (Priority 2)

**Files:** All 9 API implementation files in `api/`

#### TODO-010: Update API implementation files

**For EACH file:**
1. Update variable names: `hourly_*` → `interval_*`
2. Update method calls to use `IntervalCalculator`
3. Update references to `HourlyPrice` → `IntervalPrice`
4. Update docstrings

**Files:**
- `api/aemo.py`
- `api/amber.py`
- `api/comed.py`
- `api/entsoe.py`
- `api/epex.py`
- `api/nordpool.py`
- `api/omie.py`
- `api/energi_data.py`
- `api/stromligning.py`

**Validation:**
- APIs return standardized interval_prices
- No references to "hourly" remain

---

### Phase 7: Coordinator & Processing (Priority 3)

**Files:** `coordinator/data_processor.py`, `coordinator/unified_price_manager.py`, others

#### TODO-011: Update data processor
**File:** `coordinator/data_processor.py`

**Changes:**
1. Line 39 comment: `"hourly_prices": {"HH:00"...` → `"interval_prices": {"HH:MM"...`
2. Update all variable names: `hourly_prices` → `interval_prices`
3. Update processing logic to handle variable interval counts
4. Update statistics calculations:
   ```python
   expected_intervals = TimeInterval.get_intervals_per_day()
   is_complete = len(interval_prices) >= expected_intervals * 0.8
   ```
5. Update cache key generation

#### TODO-012: Update unified price manager
**File:** `coordinator/unified_price_manager.py`

**Changes:**
1. Update all variable names
2. Update method signatures
3. Update caching logic for increased data volume

#### TODO-013: Update other coordinator files
**Files:** `coordinator/cache_manager.py`, `coordinator/fetch_decision.py`

**Changes:**
1. Update variable names
2. Update any interval-related logic

**Validation:**
- Data flows correctly through coordinator
- Statistics calculate correctly with 96 data points
- Cache works properly

---

### Phase 8: Sensors (Priority 3)

**Files:** `sensor/base.py`, `sensor/price.py`, `sensor/electricity.py`

#### TODO-014: Update base sensor
**File:** `sensor/base.py`

**Changes:**
1. Update attribute names
2. Update property methods
3. Update state calculations

#### TODO-015: Update price sensor
**File:** `sensor/price.py`

**Changes:**
1. Rename property: `next_hour_price` → `next_interval_price`
2. Update sensor attributes:
   - `today_with_timestamps` (now 96 entries)
   - `tomorrow_with_timestamps` (now 96 entries)
3. Update documentation

#### TODO-016: Update electricity sensor
**File:** `sensor/electricity.py`

**Changes:**
1. Update entity descriptions
2. Update all hour/hourly references
3. Verify statistics work with 96 data points

**Validation:**
- Sensors display correctly in Home Assistant
- Attributes show 96 intervals
- No errors in logs

---

### Phase 9: Price Processing (Priority 3)

**Files:** `price/statistics.py`, `price/formatter.py`, `price/currency_converter.py`, `price/__init__.py`

#### TODO-017: Update price statistics
**File:** `price/statistics.py`

**Changes:**
1. Update expected interval calculations:
   ```python
   expected_intervals = TimeInterval.get_intervals_per_day()
   ```
2. Update peak hour detection to use `get_intervals_per_hour()`
3. Update all variable names: `hourly_prices` → `interval_prices`
4. Line 11 docstring: Update "HH:00" → "HH:MM"

#### TODO-018: Update price formatter
**File:** `price/formatter.py`

**Changes:**
1. Update format strings
2. Update timestamp logic
3. Ensure 15-min intervals display correctly

#### TODO-019: Update price package init
**File:** `price/__init__.py`

**Changes:**
1. Line 35: `self.hourly_prices = {}` → `self.interval_prices = {}`
2. Line 49: Update dict key references
3. Line 79: Update return statement

**Validation:**
- Statistics calculate correctly
- Formatting works for 96 intervals
- No errors in price processing

---

### Phase 10: Utilities & Converters (Priority 4)

**Files:** Various utility files

#### TODO-020: Update timezone utilities
**Files:** `utils/timezone_converter.py`, `timezone/converter.py`, others

**Changes:**
1. Line 101, 106 in `utils/timezone_converter.py`: 
   - `f"{target_dt.hour:02d}:00"` → `f"{target_dt.hour:02d}:{target_dt.minute:02d}"`
2. Update format strings from "%H:00" to "%H:%M"
3. Update all references to `HourCalculator` → `IntervalCalculator`

#### TODO-021: Update validation utilities
**Files:** `utils/data_validator.py`, `utils/validation/data_validator.py`

**Changes:**
1. Update expected data point validation
2. Update variable names
3. Use `TimeInterval.get_intervals_per_day()` for validation

**Validation:**
- All utilities work with variable intervals
- No hardcoded assumptions remain

---

### Phase 11: Translations & Config (Priority 4)

**Files:** `translations/en.json`, `translations/strings.json`, config flow files

#### TODO-022: Update translation files

**Changes in both files:**
1. Line 78: `"displaying hourly prices"` → `"displaying prices"`
2. Line 97: Keep `"60": "1 hour"` but ensure it's still valid
3. Add entry: `"15": "15 minutes"` if not present
4. Update any sensor descriptions mentioning "hour"

#### TODO-023: Update config flow
**Files:** `config_flow.py`, `config_flow/*.py`

**Changes:**
1. Update any UI text mentioning hours
2. Update validation logic if needed
3. Verify config flow still works

**Validation:**
- UI strings are correct
- Config flow works without errors
- No confusing language for users

---

### Phase 12: Testing (Priority 5)

#### TODO-024: Update unit tests

**Changes:**
1. Update expected data point counts: 24 → 96
2. Update format expectations: "HH:00" → "HH:MM"
3. Add tests for:
   - Interval rounding (to nearest 15-min)
   - IntervalCalculator methods
   - DST handling (92/100 intervals)
4. Update all variable names in test code

**Expected changes:**
```python
# OLD:
assert len(hourly_prices) == 24

# NEW:
expected_intervals = TimeInterval.get_intervals_per_day()
assert len(interval_prices) == expected_intervals
```

#### TODO-025: Update integration tests

**Files to update:**
- `tests/pytest/integration/test_nordpool_live.py`
- `tests/pytest/integration/test_epex_live.py`
- `tests/pytest/integration/test_entsoe_full_chain.py`
- `tests/pytest/integration/test_amber_live.py`
- `tests/pytest/integration/test_energi_data_live.py`

**Changes for EACH:**
1. Line patterns like: `assert "hourly_prices" in parsed_data`
   → `assert "interval_prices" in parsed_data`
2. Update variable names
3. Update expected counts
4. Update interval validation logic

#### TODO-026: Update manual tests

**Files:**
- `tests/manual/integration/stromligning_full_chain.py`
- `tests/manual/integration/energi_data_full_chain.py`
- Others

**Changes:**
1. Lines with `range(24)`: Replace with dynamic generation
2. Lines checking `== 24`: Use `TimeInterval.get_intervals_per_day()`
3. Update all variable names

**Validation:**
- All tests pass
- Can switch between HOURLY and QUARTER_HOURLY modes
- Both modes tested and working

---

### Phase 13: Documentation (Priority 5)

#### TODO-027: Update documentation

**Files:**
- `README.md`
- `docs/*.md`
- Any improvement docs

**Changes:**
1. Update feature descriptions (now 15-minute intervals)
2. Update examples showing data format
3. Add migration notes explaining the change
4. Update any screenshots or examples
5. Document the configuration-driven architecture

**Validation:**
- Documentation is accurate
- Examples work
- Users understand the change

---

## File-by-File Checklist

### Core Time Infrastructure ✅ = Complete, ⏸️ = In Progress, ☐ = Not Started

- [ ] `const/time.py` - Add TimeInterval helper methods
- [ ] `const/defaults.py` - Update UPDATE_INTERVAL
- [ ] `timezone/hour_calculator.py` → `interval_calculator.py` - Rename & refactor
- [ ] `timezone/service.py` - Update imports, fix range(24)
- [ ] `timezone/__init__.py` - Update exports
- [ ] `timezone/timezone_provider.py` - Fix range(24)
- [ ] `timezone/converter.py` - Update format strings
- [ ] `timezone/dst_handler.py` - Update interval counts

### Data Structures

- [ ] `api/base/data_structure.py` - Rename classes and fields
- [ ] `api/base/base_price_api.py` - Update variable names
- [ ] `api/base/price_parser.py` - Update parsing logic

### Parsers (9 files)

- [ ] `api/parsers/entsoe_parser.py` - Prioritize PT15M
- [ ] `api/parsers/nordpool_parser.py` - Check 15-min support
- [ ] `api/parsers/epex_parser.py` - Add expansion
- [ ] `api/parsers/omie_parser.py` - Add expansion
- [ ] `api/parsers/comed_parser.py` - Add expansion
- [ ] `api/parsers/stromligning_parser.py` - Add expansion
- [ ] `api/parsers/energi_data_parser.py` - Check 15-min
- [ ] `api/parsers/amber_parser.py` - Check interval support
- [ ] `api/parsers/aemo_parser.py` - Check interval support

### API Implementations (9 files)

- [ ] `api/aemo.py`
- [ ] `api/amber.py`
- [ ] `api/comed.py`
- [ ] `api/entsoe.py`
- [ ] `api/epex.py`
- [ ] `api/nordpool.py`
- [ ] `api/omie.py`
- [ ] `api/energi_data.py`
- [ ] `api/stromligning.py`

### Coordinator & Processing

- [ ] `coordinator/data_processor.py` - Update processing
- [ ] `coordinator/unified_price_manager.py` - Update manager
- [ ] `coordinator/cache_manager.py` - Update cache
- [ ] `coordinator/fetch_decision.py` - Update logic
- [ ] `price/statistics.py` - Update calculations
- [ ] `price/formatter.py` - Update formatting
- [ ] `price/currency_converter.py` - Update variable names
- [ ] `price/__init__.py` - Update self.hourly_prices

### Sensors

- [ ] `sensor/base.py` - Update attributes
- [ ] `sensor/price.py` - Rename next_hour_price
- [ ] `sensor/electricity.py` - Update descriptions

### Utilities

- [ ] `utils/timezone_converter.py` - Fix :00 format
- [ ] `utils/date_range.py` - Verify 15-min logic
- [ ] `utils/rate_limiter.py` - Review .hour usage
- [ ] `utils/data_validator.py` - Update validation
- [ ] `utils/validation/data_validator.py` - Update validation

### Configuration & Translations

- [ ] `translations/en.json` - Update strings
- [ ] `translations/strings.json` - Update strings
- [ ] `config_flow.py` - Update UI text
- [ ] `config_flow/*.py` - Update validation

### Tests

- [ ] Unit tests - Update expectations
- [ ] Integration tests - Update 6+ test files
- [ ] Manual tests - Update 3+ test files

### Documentation

- [ ] `README.md` - Update main docs
- [ ] `docs/*.md` - Update supporting docs
- [ ] Migration notes - Add user guide

---

## Code Patterns & Examples

### ✅ GOOD: Configuration-Driven Code

```python
# Use helper methods instead of hardcoded values
interval_minutes = TimeInterval.get_interval_minutes()
intervals_per_hour = TimeInterval.get_intervals_per_hour()
intervals_per_day = TimeInterval.get_intervals_per_day()

# Generate interval keys dynamically
for hour in range(24):
    for i in range(intervals_per_hour):
        minute = i * interval_minutes
        interval_key = f"{hour:02d}:{minute:02d}"
```

### ❌ BAD: Hardcoded Values

```python
# Don't hardcode interval values!
interval_minutes = 15  # BAD!
intervals_per_day = 96  # BAD!

# Don't hardcode minute values!
for minute in [0, 15, 30, 45]:  # BAD!
    interval_key = f"{hour:02d}:{minute:02d}"
```

### ✅ GOOD: Generic Variable Names

```python
# Use generic terminology
interval_prices = parser.parse_response(response)
current_interval = calculator.get_current_interval_key()
next_interval = calculator.get_next_interval_key()

# Generic class names
@dataclass
class IntervalPrice:
    interval_key: str  # HH:MM format
    price: float
```

### ❌ BAD: Hour-Specific Names

```python
# Don't use hour-specific names!
hourly_prices = parser.parse_response(response)  # BAD!
current_hour = calculator.get_current_hour_key()  # BAD!

# Don't use hour-specific classes!
class HourlyPrice:  # BAD!
    hour_key: str  # HH:00 format
```

### ✅ GOOD: Generic Format Strings

```python
# Use HH:MM format for all intervals
interval_key = f"{dt.hour:02d}:{dt.minute:02d}"
format_str = "%H:%M"

# Round to interval boundary
interval_minutes = TimeInterval.get_interval_minutes()
rounded_minute = (dt.minute // interval_minutes) * interval_minutes
```

### ❌ BAD: Hardcoded Format Strings

```python
# Don't assume :00 minutes!
hour_key = f"{dt.hour:02d}:00"  # BAD!
format_str = "%H:00"  # BAD!
```

### ✅ GOOD: Dynamic Validation

```python
# Use configuration for validation
expected_intervals = TimeInterval.get_intervals_per_day()
if len(interval_prices) >= expected_intervals * 0.8:
    data_is_complete = True

# DST handling
if is_dst_spring:
    expected = TimeInterval.get_intervals_per_day_dst_spring()
elif is_dst_fall:
    expected = TimeInterval.get_intervals_per_day_dst_fall()
```

### ❌ BAD: Hardcoded Validation

```python
# Don't hardcode expected counts!
if len(prices) >= 96 * 0.8:  # BAD!
    data_is_complete = True

if len(prices) == 92:  # BAD - hardcoded DST!
    is_dst_spring = True
```

---

## Testing Strategy

### Unit Testing

**Test both modes:**
```python
def test_hourly_mode():
    """Test that hourly mode works."""
    TimeInterval.DEFAULT = TimeInterval.HOURLY
    assert TimeInterval.get_interval_minutes() == 60
    assert TimeInterval.get_intervals_per_day() == 24
    # Run tests...

def test_15min_mode():
    """Test that 15-minute mode works."""
    TimeInterval.DEFAULT = TimeInterval.QUARTER_HOURLY
    assert TimeInterval.get_interval_minutes() == 15
    assert TimeInterval.get_intervals_per_day() == 96
    # Run tests...
```

**Test interval rounding:**
```python
def test_round_to_interval():
    """Test rounding to nearest interval."""
    calculator = IntervalCalculator()
    
    # Test various times
    test_times = [
        ("14:03", "14:00"),  # Round down
        ("14:08", "14:15"),  # Round to nearest
        ("14:23", "14:15"),  # Round down
        ("14:38", "14:30"),  # Round down
    ]
    
    for input_time, expected in test_times:
        # ... test logic
```

**Test DST handling:**
```python
def test_dst_spring_forward():
    """Test spring forward DST transition."""
    expected_intervals = TimeInterval.get_intervals_per_day_dst_spring()
    assert expected_intervals == 92  # For 15-min mode
    # Test that 2:00-3:00 interval is skipped...

def test_dst_fall_back():
    """Test fall back DST transition."""
    expected_intervals = TimeInterval.get_intervals_per_day_dst_fall()
    assert expected_intervals == 100  # For 15-min mode
    # Test that 2:00-3:00 interval repeats...
```

### Integration Testing

**Test with real APIs:**
1. Fetch data from each API
2. Verify interval_prices dict is returned
3. Verify correct number of intervals
4. Verify keys are in "HH:MM" format
5. Verify prices are reasonable
6. Verify expansion works for hourly-only APIs

👉 See `INTEGRATION_TEST_STATUS_REPORT.md` for the current timeline of fixes, open issues, and recommended validation commands before running or modifying these suites.

### Manual Testing

**Test in Home Assistant:**
1. Install updated integration
2. Configure a region
3. Wait for price fetch
4. Check sensor attributes show 96 intervals
5. Check `next_interval_price` sensor works
6. Verify no errors in logs
7. Check UI displays correctly

**Test configuration switching:**
1. Change `TimeInterval.DEFAULT` to `HOURLY`
2. Restart Home Assistant
3. Verify 24 data points shown
4. Change back to `QUARTER_HOURLY`
5. Restart Home Assistant
6. Verify 96 data points shown

---

## Progress Tracking

### Overall Progress: 0/27 TODOs (0%)

```
████░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 0%
```

### Phase Completion

### Phase Progress Checklist

- [x] Phase 1: Core Constants (2 TODOs) ✅ COMPLETE
- [x] Phase 2: Time Calculator (2 TODOs) ✅ COMPLETE
- [x] Phase 3: Data Structures (2 TODOs) ✅ COMPLETE
- [x] Phase 4: API Base (2 TODOs) ✅ COMPLETE
- [x] Phase 5: Parsers (1 TODO covering 9 files) ✅ COMPLETE
- [x] Phase 6: API Implementations (1 TODO covering 9 files) ✅ COMPLETE
- [x] Phase 7: Coordinator (3 TODOs) ✅ COMPLETE
- [x] Phase 8: Sensors (3 TODOs) ✅ COMPLETE
- [x] Phase 9: Price Processing (3 TODOs) ✅ COMPLETE
- [x] Phase 10: Utilities (2 TODOs) ✅ COMPLETE
- [x] Phase 11: Config & Translations (2 TODOs) ✅ COMPLETE
- [x] Phase 12: Testing (3 TODOs) ✅ COMPLETE
- [ ] Phase 13: Documentation (1 TODO) 📝 NEXT

### Completion Criteria

**Code Quality:**
- [x] No "hourly" in variable names ✅
- [x] No "hour_key" in code ✅
- [x] No "HH:00" hardcoded formats ✅
- [x] No hardcoded 24, 96, 15, etc. ✅
- [x] All imports updated ✅
- [x] All docstrings updated ✅

**Functionality:**
- [x] All APIs fetch data correctly ✅
- [x] Sensors display intervals correctly ✅
- [x] Statistics calculate correctly ✅
- [x] DST handling works ✅
- [x] Cache works ✅
- [x] Config flow works ✅
- [x] No errors in production code ✅

**Testing:**
- [x] Can switch between HOURLY and QUARTER_HOURLY ✅
- [x] Both modes work correctly ✅
- [x] All test files updated ✅

---

## Next Steps

### Ready to Implement!

1. ✅ **Planning complete** - This master document contains everything
2. ☐ **Get approval** - Review with maintainer
3. ☐ **Start Phase 1** - Core constants & time handling
4. ☐ **Test incrementally** - After each phase
5. ☐ **Mark progress** - Update checkboxes as you go

### After Completion

1. ☐ Test thoroughly with real Home Assistant instance
2. ☐ Test all supported APIs
3. ☐ Create PR to main branch
4. ☐ Update version number
5. ☐ Add to changelog
6. ☐ **Delete this planning_docs folder** ✓

---

## Questions & Answers

### Why generic naming instead of "15min"?

**Answer:** Generic naming makes the code future-proof. If markets move to 5-minute or 30-minute intervals, we just change ONE constant. No code rewrite needed.

### Why not keep backward compatibility?

**Answer:** User (maintainer) requested a fresh start. This integration is personal use only, so breaking changes are acceptable. Clean architecture is prioritized.

### What if an API doesn't support 15-minute data?

**Answer:** We use the generic `expand_to_intervals()` function to duplicate hourly prices across all intervals within each hour. This keeps the integration working while APIs transition to finer granularity.

### How do we test both hourly and 15-minute modes?

**Answer:** Change `TimeInterval.DEFAULT` and rerun tests. The configuration-driven design makes this trivial.

### What's the biggest risk?

**Answer:** Missing a hardcoded `range(24)` or `"HH:00"` format string. That's why we have comprehensive fact-finding and file-by-file checklists.

---

## Summary

This master plan provides:
- ✅ Complete impact analysis (40+ files, 415+ variables)
- ✅ Architecture design (configuration-driven, generic)
- ✅ Implementation plan (13 phases, 27 TODOs)
- ✅ Code patterns and examples (good vs. bad)
- ✅ Testing strategy (unit, integration, manual)
- ✅ Progress tracking (checkboxes for everything)

**Everything you need in ONE document!**

**When done, delete the entire `planning_docs/` folder.** 🗑️

---

**Ready to start Phase 1!** 🚀
