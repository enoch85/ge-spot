# Implementation Plan: 15-Minute Interval Support

## Overview
This document outlines the step-by-step plan to migrate GE-Spot from hourly (60-minute) intervals to 15-minute intervals for electricity price tracking.

**Date:** October 1, 2025
**Branch:** 15min
**Goal:** Support 15-minute price intervals with GENERIC naming for easy future changes

**Related Documents:**
- `FACT_FINDING_15MIN.md` - Complete analysis of all code requiring changes (40+ files, 415+ occurrences)

---

## Implementation Rules
1. ✅ Make it super clean! No complex code additions
2. ✅ Cleanup code when possible, maintain functionality
3. ✅ Read whole files before editing
4. ❌ No useEffect or useCallback (not applicable - Python project)
5. ✅ Ask before implementing each phase
6. ✅ Use TODOs to track progress
7. ✅ Use GENERIC naming (not "15min" specific) for easy future changes

---

## Key Design Principle: Configuration-Driven

### Single Point of Control
**Change ONE constant to control interval duration globally:**
```python
# const/time.py
class TimeInterval:
    DEFAULT = QUARTER_HOURLY  # ← Change ONLY this!
```

All other values auto-calculate from this:
- Interval duration (15 minutes)
- Intervals per hour (4)
- Intervals per day (96)
- DST adjustments (92/100 intervals)
- Format strings ("HH:MM")

**Benefits:**
- ✅ Future-proof: Easy to switch to 5-min, 30-min, etc.
- ✅ Testable: Can test both hourly and 15-min modes
- ✅ No hardcoded assumptions about "hourly" or "15-minute"

---

## Architecture Overview

### Current State (Hourly)
- **Data points per day:** 24 (one per hour)
- **Interval format:** "HH:00" (e.g., "14:00")
- **Update interval:** 30 minutes
- **Key variables:** `hourly_prices`, `next_hour_price`, `hour_key`
- **Code impact:** 389 "hourly" occurrences, 415 hour-related variables

### Target State (15-Minute with Generic Naming)
- **Data points per day:** 96 (four per hour: :00, :15, :30, :45)
- **Interval format:** "HH:MM" (e.g., "14:00", "14:15", "14:30", "14:45")
- **Update interval:** 15 minutes
- **Key variables:** `interval_prices`, `next_interval_price`, `interval_key` (GENERIC!)

### Generic Terminology Mapping
| Old (Hour-specific) | New (Generic) | Reason |
|---------------------|---------------|---------|
| `hourly_prices` | `interval_prices` | Works for any interval duration |
| `HourlyPrice` | `IntervalPrice` | Generic class name |
| `hour_key` | `interval_key` | Not tied to "hour" concept |
| `next_hour_price` | `next_interval_price` | Generic for any interval |
| `HourCalculator` | `IntervalCalculator` | Calculates any interval |
| `"HH:00"` format | `"HH:MM"` format | Supports all minute values |

---

## Phase 1: Core Constants & Time Handling

### 1.1 Update Time Constants (CONFIGURATION-DRIVEN APPROACH)
**File:** `custom_components/ge_spot/const/time.py`

**TODO-001:** Implement configuration-driven interval system
- [ ] Change `TimeInterval.DEFAULT` from `HOURLY` to `QUARTER_HOURLY` (single point of control!)
- [ ] Add static helper methods that auto-calculate from DEFAULT:
  - [ ] `get_interval_minutes()` → returns 15 (for QUARTER_HOURLY) or 60 (for HOURLY)
  - [ ] `get_intervals_per_hour()` → returns 4 (for QUARTER_HOURLY) or 1 (for HOURLY)
  - [ ] `get_intervals_per_day()` → returns 96 (for QUARTER_HOURLY) or 24 (for HOURLY)
- [ ] Update DST constants to be calculated:
  - [ ] `get_intervals_per_day_dst_spring()` → base_intervals - intervals_per_hour
  - [ ] `get_intervals_per_day_dst_fall()` → base_intervals + intervals_per_hour
- [ ] Keep existing `QUARTER_HOURLY = "PT15M"` (already exists!)
- [ ] Keep existing `HOURLY = "PT60M"`

**Why Configuration-Driven?**
- Change ONE value (`DEFAULT`) to switch between 15-min, hourly, or any future interval
- All code auto-adapts by calling `get_interval_*()` methods
- Easy to test both modes by changing single constant

### 1.2 Update Default Values
**File:** `custom_components/ge_spot/const/defaults.py`

**TODO-002:** Update update interval
- [ ] Change `UPDATE_INTERVAL = 30` → `UPDATE_INTERVAL = 15`

### 1.3 Rename & Refactor Hour Calculator → Interval Calculator (GENERIC)
**Files:** 
- `custom_components/ge_spot/timezone/hour_calculator.py` → `interval_calculator.py`
- Update all imports in:
  - `timezone/service.py` (line 18)
  - `timezone/__init__.py` (line 7)

**TODO-003:** Rename class and file (GENERIC naming)
- [ ] Rename file: `hour_calculator.py` → `interval_calculator.py`
- [ ] Rename class: `HourCalculator` → `IntervalCalculator`
- [ ] Rename method: `get_current_hour_key()` → `get_current_interval_key()`
- [ ] Rename method: `get_next_hour_key()` → `get_next_interval_key()`
- [ ] Rename method: `get_hour_key_for_datetime()` → `get_interval_key_for_datetime()`

**TODO-004:** Update interval calculation logic (CONFIGURATION-DRIVEN)
- [ ] Add method: `_round_to_interval(dt: datetime) -> datetime`
  - Gets interval minutes from `TimeInterval.get_interval_minutes()`
  - Rounds to nearest interval boundary (works for any duration)
- [ ] Update `get_current_interval_key()`:
  - Use `_round_to_interval()` to round current time
  - Return "HH:MM" format (not hardcoded to ":00")
- [ ] Update `get_next_interval_key()`:
  - Add `TimeInterval.get_interval_minutes()` to current time
  - Return "HH:MM" format
- [ ] Update DST handling:
  - Use `TimeInterval.get_intervals_per_day_dst_spring()` for spring forward
  - Use `TimeInterval.get_intervals_per_day_dst_fall()` for fall back
- [ ] Update all docstrings to be generic (not mention "hour")

**Why Generic?**
- Works for 15-min, hourly, or any future interval
- No hardcoded ":00" assumptions
- Easy to maintain and test

---

## Phase 2: Data Structures

### 2.1 Update Data Classes
**File:** `custom_components/ge_spot/api/base/data_structure.py`

**TODO-005:** Rename HourlyPrice class (GENERIC)
- [ ] Rename class: `HourlyPrice` → `IntervalPrice`
- [ ] Rename field: `hour_key: str` → `interval_key: str`
- [ ] Update docstring: "Hourly price data" → "Price data for a single time interval"
- [ ] Update field comment: "Format: HH:00" → "Format: HH:MM"

**TODO-006:** Update StandardizedPriceData class (GENERIC)
- [ ] Rename field: `hourly_prices: Dict[str, float]` → `interval_prices: Dict[str, float]`
- [ ] Update comment: "Key: HH:00, Value: price" → "Key: HH:MM, Value: price"
- [ ] Rename field: `raw_prices: List[HourlyPrice]` → `raw_prices: List[IntervalPrice]`
- [ ] Rename field: `next_hour_price: Optional[float]` → `next_interval_price: Optional[float]`
- [ ] Rename field: `current_hour_key: Optional[str]` → `current_interval_key: Optional[str]`
- [ ] Rename field: `next_hour_key: Optional[str]` → `next_interval_key: Optional[str]`
- [ ] Update `to_dict()` method to use new field names
- [ ] Update all docstrings to be generic (not mention "hour" or "hourly")

**Why Generic Naming?**
- `interval_prices` works for any interval duration (5-min, 15-min, hourly)
- `IntervalPrice` doesn't assume hourly granularity
- Future-proof for different market structures

---

## Phase 3: API Layer Changes

### 3.1 Update Base API
**File:** `custom_components/ge_spot/api/base/base_price_api.py`

**TODO-007:** Update base API documentation and references (GENERIC)
- [ ] Update all docstrings mentioning "hourly" → "interval"
- [ ] Update method comments and variable names
- [ ] Search for any hardcoded "hourly" strings and make generic

### 3.2 Create Generic Interval Expansion Utility
**Location:** `custom_components/ge_spot/api/base/` or `api/utils.py`

**TODO-008:** Create generic interval expansion helper (CONFIGURATION-DRIVEN)
- [ ] Create function `expand_to_intervals(data: Dict[str, float]) -> Dict[str, float]`
  - Uses `TimeInterval.get_interval_minutes()` for expansion factor
  - Works for ANY interval duration (not hardcoded to 15-min)
  - Returns original data if already at correct granularity
- [ ] Add detection logic to check current data granularity
- [ ] Document expansion strategy in docstrings

**Generic Expansion Logic:**
```python
def expand_to_intervals(hourly_data: Dict[str, float]) -> Dict[str, float]:
    """
    Expand hourly prices to match configured interval.
    
    Generic implementation - automatically adapts to configured interval duration.
    If API provides hourly data but system needs finer granularity,
    duplicate the hourly price across all intervals in that hour.
    
    Configuration-driven: Uses TimeInterval.get_interval_minutes() to determine
    expansion factor. Works for 15-min, 5-min, or any future interval.
    """
    interval_minutes = TimeInterval.get_interval_minutes()
    
    if interval_minutes == 60:
        return hourly_data  # Already hourly, no expansion needed
    
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

### 3.3 Update API Parsers
**Directory:** `custom_components/ge_spot/api/parsers/`

**TODO-009:** Update parser implementations (API-SPECIFIC)
- [ ] **ENTSO-E parser** (`entsoe_parser.py`):
  - ✅ Already supports PT15M resolution!
  - [ ] Prioritize PT15M over PT60M in resolution_preference
  - [ ] Update variable names: `hourly_*` → `interval_*`
- [ ] **NordPool parser** (`nordpool_parser.py`):
  - [ ] Check if API now provides 15-min data (likely yes as of Oct 1, 2025)
  - [ ] Add 15-min parsing if available
  - [ ] Use expansion helper if still hourly
- [ ] **Other parsers** (EPEX, OMIE, ComEd, Stromligning, Energi Data):
  - [ ] Update variable names: `hourly_*` → `interval_*`
  - [ ] Apply expansion helper if API only provides hourly data
  - [ ] Update docstrings to be generic
- [ ] **Amber/AEMO parsers**:
  - [ ] Check if they provide sub-hourly data (5-min?)
  - [ ] Adapt or expand as needed

**Parser Strategy:**
1. Check if API provides native interval data
2. If yes: Parse directly to interval_prices
3. If no: Parse to hourly, then use `expand_to_intervals()`
4. Always use GENERIC variable names
```

### 3.3 Update Individual API Implementations
**Files:** All files in `custom_components/ge_spot/api/`

**TODO-009:** Update each API implementation file
- [ ] `aemo.py`
- [ ] `amber.py`
- [ ] `comed.py`
- [ ] `energi_data.py`
- [ ] `entsoe.py`
- [ ] `epex.py`
- [ ] `nordpool.py`
- [ ] `omie.py`
- [ ] `stromligning.py`

For each file:
- [ ] Update variable names (`hourly_*` → `interval_*`)
- [ ] Update method calls to use new interval calculator
- [ ] Add interpolation logic if API provides only hourly data

---

## Phase 4: Coordinator & Data Processing

### 4.1 Update Data Processor
**File:** `custom_components/ge_spot/coordinator/data_processor.py`

**TODO-010:** Update data processor for 15-minute intervals
- [ ] Update variable names (`hourly_*` → `interval_*`)
- [ ] Update processing logic to handle 96 intervals per day
- [ ] Update statistics calculations (ensure they still work with 4x data points)
- [ ] Update cache key generation
- [ ] Verify peak/off-peak hour detection works with 15-min intervals

### 4.2 Update Unified Price Manager
**File:** `custom_components/ge_spot/coordinator/unified_price_manager.py`

**TODO-011:** Update price manager
- [ ] Update all references to hourly data
- [ ] Update method signatures and internal variables
- [ ] Update caching logic for increased data volume

---

## Phase 5: Sensor Layer

### 5.1 Update Sensor Base
**File:** `custom_components/ge_spot/sensor/base.py`

**TODO-012:** Update base sensor class
- [ ] Update attribute names (`next_hour_price` → `next_interval_price`)
- [ ] Update property methods
- [ ] Update state calculations

### 5.2 Update Price Sensor
**File:** `custom_components/ge_spot/sensor/price.py`

**TODO-013:** Update price sensor
- [ ] Rename `next_hour_price` property → `next_interval_price`
- [ ] Update sensor attributes:
  - `today_with_timestamps` (will now have 96 entries)
  - `tomorrow_with_timestamps` (will now have 96 entries)
- [ ] Update documentation and comments

### 5.3 Update Electricity Sensor
**File:** `custom_components/ge_spot/sensor/electricity.py`

**TODO-014:** Update electricity sensor
- [ ] Update sensor entity names and descriptions
- [ ] Update all references to hour/hourly
- [ ] Ensure statistics still calculate correctly with 96 data points

---

## Phase 6: Price Processing

### 6.1 Update Price Formatter
**File:** `custom_components/ge_spot/price/formatter.py`

**TODO-015:** Update price formatter
- [ ] Update any hardcoded "hour" strings in formatting
- [ ] Update timestamp formatting logic if needed
- [ ] Ensure display logic handles 15-minute intervals

### 6.2 Update Price Statistics
**File:** `custom_components/ge_spot/price/statistics.py`

**TODO-016:** Update statistics calculations
- [ ] Verify min/max/average calculations work with 96 data points
- [ ] Verify median calculations
- [ ] Update peak hour detection (may need to consider 15-min granularity)

---

## Phase 7: Utilities

### 7.1 Update Timezone Utilities
**Files:**
- `custom_components/ge_spot/timezone/converter.py`
- `custom_components/ge_spot/timezone/dst_handler.py`
- `custom_components/ge_spot/timezone/service.py`
- Other timezone modules

**TODO-017:** Update timezone handling
- [ ] Update all references to `HourCalculator` → `IntervalCalculator`
- [ ] Update imports
- [ ] Verify DST handling works with 15-minute intervals
- [ ] Update any hour-based calculations

### 7.2 Update Other Utilities
**Files:**
- `custom_components/ge_spot/utils/date_range.py`
- Other utility files as needed

**TODO-018:** Update utility functions
- [ ] Search for any remaining "hour" references
- [ ] Update to use interval concepts where appropriate

---

## Phase 8: Configuration & Translations

### 8.1 Update Translation Files
**Files:**
- `custom_components/ge_spot/translations/en.json`
- `custom_components/ge_spot/translations/strings.json`

**TODO-019:** Update UI strings
- [ ] "Next Hour Price" → "Next Interval Price" (or "Next 15-min Price")
- [ ] "Current hour price" → "Current interval price"
- [ ] "Hourly prices" → "Interval prices"
- [ ] Update any other user-facing strings mentioning hours
- [ ] Update sensor descriptions

### 8.2 Update Config Flow
**Files:**
- `custom_components/ge_spot/config_flow.py`
- Files in `custom_components/ge_spot/config_flow/`

**TODO-020:** Update configuration
- [ ] Update any UI text mentioning hours
- [ ] Update validation logic if needed
- [ ] Verify config flow still works correctly

---

## Phase 9: Testing

### 9.1 Update Unit Tests
**Directory:** `tests/pytest/unit/`

**TODO-021:** Update unit tests
- [ ] Update test expectations: 24 → 96 data points per day
- [ ] Update hour key format tests: "HH:00" → "HH:MM"
- [ ] Add tests for 15-minute interval rounding
- [ ] Add tests for interval boundary calculations
- [ ] Update DST transition tests (23/25 hours → 92/100 intervals)

### 9.2 Update Integration Tests
**Directory:** `tests/pytest/integration/`

**TODO-022:** Update integration tests
- [ ] Update `test_nordpool_live.py`
- [ ] Update `test_epex_live.py`
- [ ] Update `test_entsoe_full_chain.py`
- [ ] Update `test_amber_live.py`
- [ ] Update `test_energi_data_live.py`
- [ ] Update all other integration tests

For each test:
- [ ] Update expected data point counts (24 → 96)
- [ ] Update variable names (`hourly_prices` → `interval_prices`)
- [ ] Update interval validation logic
- [ ] Add tests for APIs with native 15-min support vs interpolated

### 9.3 Update Manual Tests
**Directory:** `tests/manual/`

**TODO-023:** Update manual test scripts
- [ ] Update API test scripts
- [ ] Update full chain test scripts
- [ ] Test with real API data

---

## Phase 10: Documentation

**TODO-024:** Update documentation
- [ ] Update README.md
- [ ] Update any documentation in `docs/`
- [ ] Update improvement documents if needed
- [ ] Add migration notes for users

---

## Code Impact Summary

### Quantitative Analysis (from FACT_FINDING_15MIN.md)
- **Total files to modify:** 40+ Python files
- **"hourly" occurrences:** 389 in Python files
- **"hour" occurrences:** 734+ in Python files  
- **hour-related variables:** 415+ occurrences
- **Test files affected:** 196+ test assertions
- **Expected data points:** 24 → 96 (4x increase)

### Files by Priority

#### Priority 1: Core Infrastructure (8 files)
- `const/time.py` - Add configuration-driven interval system
- `const/defaults.py` - Update UPDATE_INTERVAL
- `timezone/hour_calculator.py` → `interval_calculator.py` (rename + refactor)
- `timezone/service.py` - Update imports
- `timezone/__init__.py` - Update imports
- `api/base/data_structure.py` - Rename classes
- `api/base/base_price_api.py` - Update API base
- `api/base/price_parser.py` - Update parsing logic

#### Priority 2: API & Parsers (15 files)
- All 9 parser files in `api/parsers/`
- All 6 API implementation files in `api/`

#### Priority 3: Processing & Display (10 files)
- `coordinator/data_processor.py`
- `coordinator/unified_price_manager.py`
- `coordinator/cache_manager.py`
- `coordinator/fetch_decision.py`
- `sensor/base.py`
- `sensor/price.py`
- `sensor/electricity.py`
- `price/statistics.py`
- `price/currency_converter.py`
- `price/formatter.py`

#### Priority 4: Config, Utils & Tests (20+ files)
- Translation files (2)
- Utility files (5+)
- Test files (15+)

---

## Implementation Order

### Sprint 1: Foundation (Phases 1-2)
1. Phase 1: Core Constants & Time Handling
2. Phase 2: Data Structures

**Checkpoint:** Run type checks, ensure no import errors

### Sprint 2: API Layer (Phase 3)
3. Phase 3: API Layer Changes

**Checkpoint:** Test parser outputs, verify interpolation logic

### Sprint 3: Processing & Display (Phases 4-6)
4. Phase 4: Coordinator & Data Processing
5. Phase 5: Sensor Layer
6. Phase 6: Price Processing

**Checkpoint:** Test with Home Assistant, verify sensors display correctly

### Sprint 4: Configuration & Utilities (Phases 7-8)
7. Phase 7: Utilities
8. Phase 8: Configuration & Translations

**Checkpoint:** Test configuration flow, verify UI strings

### Sprint 5: Testing & Documentation (Phases 9-10)
9. Phase 9: Testing
10. Phase 10: Documentation

**Checkpoint:** All tests pass, documentation complete

---

## Key Considerations

### API-Specific Handling
Each API source needs individual assessment:
- **Nord Pool:** Check if they provide 15-min data now (likely yes as of Oct 1, 2025)
- **ENTSO-E:** May provide 15-min data for some regions
- **Other APIs:** Most likely still hourly, will need interpolation

### Performance Impact
- **4x more data points:** Monitor memory usage and processing time
- **Cache size:** May need to adjust cache TTL and size limits
- **Database storage:** If persisting data, storage requirements increase 4x

### DST Transitions
- **Spring forward:** 92 intervals (lose 4 intervals at 2:00-3:00)
- **Fall back:** 100 intervals (gain 4 intervals at 2:00-3:00)
- Ensure interval calculator handles these edge cases

### Backward Compatibility
**NOT REQUIRED** - This is a breaking change, no backward compatibility needed per user request.

---

## Progress Tracking

### Overall Progress: 0/24 (0%)

#### Phase 1: ☐ Not Started (0/2)
- ☐ TODO-001: Add 15-minute interval constants
- ☐ TODO-002: Update update interval

#### Phase 2: ☐ Not Started (0/2)
- ☐ TODO-003: Rename HourCalculator class and methods
- ☐ TODO-004: Update interval calculation logic

#### Phase 3: ☐ Not Started (0/4)
- ☐ TODO-005: Rename HourlyPrice class
- ☐ TODO-006: Update StandardizedPriceData class
- ☐ TODO-007: Update base API documentation
- ☐ TODO-008: Update parser implementations

#### Phase 4: ☐ Not Started (0/4)
- ☐ TODO-009: Update API implementation files
- ☐ TODO-010: Update data processor
- ☐ TODO-011: Update unified price manager
- ☐ TODO-012: Update base sensor

#### Phase 5: ☐ Not Started (0/3)
- ☐ TODO-013: Update price sensor
- ☐ TODO-014: Update electricity sensor
- ☐ TODO-015: Update price formatter

#### Phase 6: ☐ Not Started (0/3)
- ☐ TODO-016: Update price statistics
- ☐ TODO-017: Update timezone handling
- ☐ TODO-018: Update utility functions

#### Phase 7: ☐ Not Started (0/3)
- ☐ TODO-019: Update translation files
- ☐ TODO-020: Update config flow
- ☐ TODO-021: Update unit tests

#### Phase 8: ☐ Not Started (0/3)
- ☐ TODO-022: Update integration tests
- ☐ TODO-023: Update manual tests
- ☐ TODO-024: Update documentation

---

## Next Steps

**READY TO START:** Phase 1 - Core Constants & Time Handling

Before proceeding with implementation:
1. ✅ Review this plan with the user
2. ✅ Review FACT_FINDING_15MIN.md for detailed analysis
3. ☐ Get approval to proceed with Phase 1
4. ☐ Read entire files before editing (as per rules)
5. ☐ Implement changes incrementally
6. ☐ Test after each phase
7. ☐ Mark TODOs as complete

---

## Key Success Criteria

### Configuration-Driven Architecture ✅
- Change ONE constant (`TimeInterval.DEFAULT`) to control everything
- All values auto-calculate from this single point
- No hardcoded assumptions about interval duration

### Generic Naming ✅
- Use `interval_*` instead of `hourly_*` or `15min_*`
- Variable names work for any interval duration
- Future-proof for 5-min, 30-min, or other intervals

### Clean Implementation ✅
- Remove unused code
- Simplify where possible
- Keep functionality intact
- Maintain readability

### Complete Migration ✅
- All 40+ files updated
- All 415+ variable occurrences renamed
- All 196+ test assertions updated
- Translations updated

---

## Notes
- All changes should maintain clean, readable code
- Remove unused code where possible
- Add clear comments explaining configuration-driven logic
- Keep the codebase simple and maintainable
- **GENERIC naming is mandatory** - no "15min" or "hourly" specific names
- Always use `TimeInterval` helper methods instead of hardcoded values
