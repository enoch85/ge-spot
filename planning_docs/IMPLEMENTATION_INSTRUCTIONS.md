# Implementation Instructions: 15-Minute Interval Migration

**To:** GitHub Copilot (AI Assistant)  
**From:** Repository Maintainer  
**Date:** October 1, 2025  
**Branch:** 15min  
**Priority:** High

---

## 🎯 Mission

Implement the 15-minute interval migration for the GE-Spot Home Assistant integration by following the comprehensive plan in `planning_docs/MASTER_MIGRATION_PLAN.md`.

---

## 📋 Prerequisites

1. ✅ Read `planning_docs/MASTER_MIGRATION_PLAN.md` from start to finish
2. ✅ Understand the configuration-driven architecture
3. ✅ Understand the generic naming convention
4. ✅ Have git checkpoint committed (7093b46)

---

## 🔐 Implementation Rules (CRITICAL - MUST FOLLOW)

### Rule 1: Always Read Full Files First
**BEFORE editing ANY file:**
- Use `read_file` to read the ENTIRE file (all lines)
- Understand the context and structure
- Identify all locations that need changes
- NEVER edit based on partial file reads

### Rule 2: Incremental Implementation
- Complete ONE phase at a time
- Test after each phase (run checks, look for errors)
- Commit after each completed phase
- Mark TODOs as complete in the master plan

### Rule 3: Follow the Master Plan Exactly
- Phases MUST be done in order: 1 → 2 → 3 → ... → 13
- Each TODO has exact specifications - follow them
- Use the code examples provided (good vs bad)
- Apply the patterns consistently

### Rule 4: No Assumptions or Shortcuts
- Don't skip steps thinking "it probably works"
- Don't assume variable names without checking
- Don't skip validation steps
- Read files completely, don't rely on search results alone

### Rule 5: Use Helper Methods, Never Hardcode
```python
# ✅ ALWAYS DO THIS:
interval_minutes = TimeInterval.get_interval_minutes()
intervals_per_day = TimeInterval.get_intervals_per_day()

# ❌ NEVER DO THIS:
interval_minutes = 15  # DON'T HARDCODE!
intervals_per_day = 96  # DON'T HARDCODE!
```

### Rule 6: Generic Naming Only
```python
# ✅ ALWAYS USE:
interval_prices, interval_key, IntervalCalculator

# ❌ NEVER USE:
hourly_prices, hour_key, HourCalculator (old)
fifteen_min_prices, 15min_key (too specific)
```

### Rule 7: Validate After Each Change
After editing a file:
- Check for import errors
- Check for syntax errors
- Verify the change matches the specification
- Update the progress tracker

---

## 📖 Step-by-Step Implementation Process

### Step 0: Preparation

1. **Read the master plan completely:**
   ```bash
   cat planning_docs/MASTER_MIGRATION_PLAN.md
   ```

2. **Understand the scope:**
   - 40+ files to modify
   - 415+ variable occurrences
   - 13 phases, 27 TODOs
   - Configuration-driven approach

3. **Open progress tracker:**
   - File: `planning_docs/MASTER_MIGRATION_PLAN.md`
   - Section: "File-by-File Checklist"
   - Mark items as you complete them

---

### Phase 1: Core Constants & Time Handling

#### TODO-001: Implement configuration-driven interval system

**File:** `custom_components/ge_spot/const/time.py`

**Instructions:**
1. Read the ENTIRE file first
2. Locate the `TimeInterval` class
3. Change `DEFAULT = HOURLY` to `DEFAULT = QUARTER_HOURLY`
4. Add these static methods to the class:
   ```python
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

5. **Validate:**
   - File imports correctly
   - Methods are accessible
   - Run: `python3 -c "from custom_components.ge_spot.const.time import TimeInterval; print(TimeInterval.get_intervals_per_day())"`
   - Should print: `96`

6. **Mark complete:**
   - Update checklist: `- [x] const/time.py`
   - Progress: 1/27 TODOs complete

---

#### TODO-002: Update default update interval

**File:** `custom_components/ge_spot/const/defaults.py`

**Instructions:**
1. Read the ENTIRE file first
2. Find the line: `UPDATE_INTERVAL = 30`
3. Change to: `UPDATE_INTERVAL = 15`
4. Add comment: `# Update every 15 minutes to match interval granularity`

5. **Validate:**
   - File imports correctly
   - No syntax errors

6. **Mark complete:**
   - Update checklist: `- [x] const/defaults.py`
   - Progress: 2/27 TODOs complete

---

**Checkpoint 1:**
```bash
# Test imports
python3 -c "from custom_components.ge_spot.const.time import TimeInterval; from custom_components.ge_spot.const.defaults import Defaults; print('✓ Imports work')"

# Commit progress
git add custom_components/ge_spot/const/time.py custom_components/ge_spot/const/defaults.py
git commit -m "Phase 1: Implement configuration-driven interval system

- Add TimeInterval helper methods for dynamic calculation
- Change DEFAULT from HOURLY to QUARTER_HOURLY
- Update UPDATE_INTERVAL from 30 to 15 minutes
- All interval counts now derive from single constant

Progress: 2/27 TODOs complete (Phase 1 done)"

git push origin 15min
```

---

### Phase 2: Time Calculator Refactoring

#### TODO-003: Rename HourCalculator → IntervalCalculator

**File:** `custom_components/ge_spot/timezone/hour_calculator.py`

**Instructions:**
1. Read the ENTIRE file (all ~200 lines)
2. Make these changes:
   - Line 12: `class HourCalculator:` → `class IntervalCalculator:`
   - Line 27: `def get_current_hour_key(self)` → `def get_current_interval_key(self)`
   - Line 92: `def get_next_hour_key(self)` → `def get_next_interval_key(self)`
   - Line 141: `def get_hour_key_for_datetime(self, dt)` → `def get_interval_key_for_datetime(self, dt)`
   - Update ALL docstrings: "hour" → "interval", "HH:00" → "HH:MM"
   
3. **Rename the file:**
   ```bash
   git mv custom_components/ge_spot/timezone/hour_calculator.py custom_components/ge_spot/timezone/interval_calculator.py
   ```

4. **Update imports in other files:**
   - `timezone/service.py` line 18: `from .hour_calculator import HourCalculator` → `from .interval_calculator import IntervalCalculator`
   - `timezone/service.py` line 71: `self.hour_calculator = HourCalculator(...)` → `self.interval_calculator = IntervalCalculator(...)`
   - `timezone/service.py`: Update ALL references to `self.hour_calculator` → `self.interval_calculator`
   - `timezone/__init__.py` line 7: Update export

5. **Validate:**
   - File imports correctly
   - No reference to "HourCalculator" remains in codebase
   - Run: `grep -r "HourCalculator" custom_components/ge_spot/`
   - Should return: nothing

6. **Mark complete:**
   - Update checklist: `- [x] timezone/interval_calculator.py (renamed)`
   - Progress: 3/27 TODOs complete

---

#### TODO-004: Update interval calculation logic

**File:** `custom_components/ge_spot/timezone/interval_calculator.py`

**Instructions:**
1. Read the ENTIRE file again (now that it's renamed)

2. Add new method after `__init__`:
   ```python
   def _round_to_interval(self, dt: datetime) -> datetime:
       """Round datetime to nearest interval boundary.
       
       Uses configured interval duration from TimeInterval.DEFAULT.
       Works for any interval duration (15-min, hourly, etc.).
       """
       from ..const.time import TimeInterval
       interval_minutes = TimeInterval.get_interval_minutes()
       minute = (dt.minute // interval_minutes) * interval_minutes
       return dt.replace(minute=minute, second=0, microsecond=0)
   ```

3. Update `get_current_interval_key()` method:
   - Find where it returns `f"{...}:00"`
   - Change to use `_round_to_interval()` and return `f"{rounded.hour:02d}:{rounded.minute:02d}"`
   - Make sure it handles timezone logic correctly

4. Update `get_next_interval_key()` method:
   - Use `_round_to_interval()` to get current
   - Add interval duration: `next_interval = rounded + timedelta(minutes=TimeInterval.get_interval_minutes())`
   - Return `f"{next_interval.hour:02d}:{next_interval.minute:02d}"`

5. Update `get_interval_key_for_datetime()` method:
   - Use `_round_to_interval()` instead of just using `.hour`
   - Return `f"{rounded.hour:02d}:{rounded.minute:02d}"`

6. **Update timezone/service.py - Fix hardcoded range(24):**
   - Read the ENTIRE file first
   - Find line 275: `return [f"{hour:02d}:00" for hour in range(24)]`
   - Replace with:
     ```python
     from ..const.time import TimeInterval
     interval_minutes = TimeInterval.get_interval_minutes()
     intervals_per_hour = TimeInterval.get_intervals_per_hour()
     result = []
     for hour in range(24):
         for i in range(intervals_per_hour):
             minute = i * interval_minutes
             result.append(f"{hour:02d}:{minute:02d}")
     return result
     ```
   - Do the same for line 280 (similar pattern)

7. **Update timezone/timezone_provider.py:**
   - Find line 314: `return [day_start + timedelta(hours=i) for i in range(24)]`
   - Replace with interval-based generation using `get_intervals_per_day()`

8. **Validate:**
   - Test IntervalCalculator returns "HH:MM" format
   - Run: `python3 -c "from custom_components.ge_spot.timezone.interval_calculator import IntervalCalculator; from homeassistant.util import dt as dt_util; calc = IntervalCalculator(); print(calc.get_current_interval_key())"`
   - Should print something like "14:15" or "14:30" (not "14:00" unless it's exactly on the hour)

9. **Mark complete:**
   - Update checklist: `- [x] timezone/interval_calculator.py (logic updated)`
   - Update checklist: `- [x] timezone/service.py (imports + range(24) fixed)`
   - Update checklist: `- [x] timezone/__init__.py (exports)`
   - Update checklist: `- [x] timezone/timezone_provider.py (range(24) fixed)`
   - Progress: 4/27 TODOs complete

---

**Checkpoint 2:**
```bash
# Test interval calculator
python3 -c "
from custom_components.ge_spot.timezone.interval_calculator import IntervalCalculator
from custom_components.ge_spot.const.time import TimeInterval
print('Interval minutes:', TimeInterval.get_interval_minutes())
print('Intervals per day:', TimeInterval.get_intervals_per_day())
calc = IntervalCalculator()
print('Current interval key:', calc.get_current_interval_key())
print('✓ All working!')
"

# Verify no HourCalculator references remain
grep -r "HourCalculator" custom_components/ge_spot/ || echo "✓ No HourCalculator references found"

# Verify no hardcoded range(24) remain in critical files
grep -n "range(24)" custom_components/ge_spot/timezone/ || echo "✓ No hardcoded range(24) in timezone/"

# Commit progress
git add -A
git commit -m "Phase 2: Refactor HourCalculator to IntervalCalculator

- Rename class and file to generic IntervalCalculator
- Add _round_to_interval() method using TimeInterval config
- Update all key methods to return HH:MM format (not HH:00)
- Fix hardcoded range(24) in timezone/service.py
- Fix hardcoded range(24) in timezone/timezone_provider.py
- Update all imports and references
- Remove all HourCalculator references from codebase

Progress: 4/27 TODOs complete (Phase 2 done)"

git push origin 15min
```

---

### Phase 3: Data Structures

#### TODO-005 & TODO-006: Update data classes

**File:** `custom_components/ge_spot/api/base/data_structure.py`

**Instructions:**
1. Read the ENTIRE file (all ~233 lines)

2. **Rename HourlyPrice class (line 7-20):**
   - `class HourlyPrice:` → `class IntervalPrice:`
   - `hour_key: str` → `interval_key: str`
   - Docstring: "Hourly price data" → "Price data for a single time interval"
   - Comment: "Format: HH:00" → "Format: HH:MM"

3. **Update StandardizedPriceData class (line 59-80):**
   - `hourly_prices: Dict[str, float]` → `interval_prices: Dict[str, float]`
   - Comment: "Key: HH:00, Value: price" → "Key: HH:MM, Value: price"
   - `raw_prices: List[HourlyPrice]` → `raw_prices: List[IntervalPrice]`
   - `next_hour_price: Optional[float]` → `next_interval_price: Optional[float]`
   - `current_hour_key: Optional[str]` → `current_interval_key: Optional[str]`
   - `next_hour_key: Optional[str]` → `next_interval_key: Optional[str]`

4. **Update to_dict() method:**
   - Find all references to renamed fields
   - Update dictionary keys to use new names

5. **Update all other references in the file:**
   - Search for "hourly", "hour_key", "hour"
   - Update docstrings, comments, variable names

6. **Validate:**
   - File imports correctly
   - No "HourlyPrice" or "hourly_prices" references remain
   - Run: `grep -n "HourlyPrice\|hourly_prices\|hour_key\|next_hour_price\|current_hour_key\|next_hour_key" custom_components/ge_spot/api/base/data_structure.py`
   - Should return: nothing (or only in comments explaining the change)

7. **Mark complete:**
   - Update checklist: `- [x] api/base/data_structure.py`
   - Progress: 6/27 TODOs complete

---

**Checkpoint 3:**
```bash
# Test data structure imports
python3 -c "
from custom_components.ge_spot.api.base.data_structure import IntervalPrice, StandardizedPriceData
print('✓ IntervalPrice imports successfully')
print('✓ StandardizedPriceData imports successfully')
"

# Verify no old names remain
grep -r "HourlyPrice" custom_components/ge_spot/api/base/data_structure.py || echo "✓ No HourlyPrice found"
grep -r "hourly_prices" custom_components/ge_spot/api/base/data_structure.py || echo "✓ No hourly_prices found"

# Commit progress
git add custom_components/ge_spot/api/base/data_structure.py
git commit -m "Phase 3: Rename data structure classes to generic names

- HourlyPrice → IntervalPrice
- hourly_prices → interval_prices
- hour_key → interval_key
- next_hour_price → next_interval_price
- current_hour_key → current_interval_key
- next_hour_key → next_interval_key
- Update all docstrings and comments
- HH:00 format → HH:MM format

Progress: 6/27 TODOs complete (Phase 3 done)"

git push origin 15min
```

---

### Phases 4-13: Continue Similarly

For each subsequent phase:

1. **Read the phase section in MASTER_MIGRATION_PLAN.md**
2. **For each TODO in the phase:**
   - Read the ENTIRE file(s) first
   - Make the specified changes
   - Validate the changes
   - Mark the TODO complete
3. **After completing the phase:**
   - Run the checkpoint validation
   - Commit with descriptive message
   - Push to origin
   - Update progress counter

**Follow this pattern for:**
- Phase 4: API Base & Expansion (TODOs 7-8)
- Phase 5: Parser Updates (TODO 9 - covers 9 files)
- Phase 6: API Implementations (TODO 10 - covers 9 files)
- Phase 7: Coordinator & Processing (TODOs 11-13)
- Phase 8: Sensors (TODOs 14-16)
- Phase 9: Price Processing (TODOs 17-19)
- Phase 10: Utilities & Converters (TODOs 20-21)
- Phase 11: Translations & Config (TODOs 22-23)
- Phase 12: Testing (TODOs 24-26)
- Phase 13: Documentation (TODO 27)

---

## 🧪 Testing Protocol

### After Each Phase
```bash
# Check for import errors
python3 -c "from custom_components.ge_spot import *; print('✓ No import errors')"

# Check for syntax errors
python3 -m py_compile custom_components/ge_spot/**/*.py

# Run Home Assistant config check (if available)
hass --script check_config -c /path/to/config
```

### After Complete Implementation
```bash
# Run all tests
cd tests
python3 -m pytest

# Or run manual tests
./scripts/run_pytest.sh
```

---

## ✅ Validation Checklist

Before considering the migration complete:

### Code Quality
- [ ] No "hourly" in variable names (except comments explaining changes)
- [ ] No "hour_key" in code
- [ ] No "HourlyPrice" or "HourCalculator" classes
- [ ] No hardcoded "HH:00" format strings
- [ ] No hardcoded values: 24, 96, 15 (use TimeInterval methods)
- [ ] All imports updated
- [ ] All docstrings updated

### Functionality
- [ ] Can import all modules without errors
- [ ] IntervalCalculator returns "HH:MM" format keys
- [ ] TimeInterval.get_*() methods work correctly
- [ ] Can switch between HOURLY and QUARTER_HOURLY modes
- [ ] All APIs fetch data successfully
- [ ] Sensors display 96 intervals (not 24)
- [ ] Statistics calculate correctly
- [ ] No errors in Home Assistant logs

### Testing
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Manual testing in Home Assistant successful
- [ ] Tested with at least 2 different APIs
- [ ] DST transitions handled correctly

---

## 🔄 If Something Goes Wrong

### Revert to Checkpoint
```bash
# See all commits
git log --oneline

# Revert to planning checkpoint
git reset --hard 7093b46

# Or revert to last working phase
git reset --hard HEAD~1  # Go back one commit

# Or revert specific files
git checkout 7093b46 -- custom_components/ge_spot/const/time.py
```

### Debug Issues
```bash
# Check for remaining old variable names
grep -r "hourly_prices" custom_components/ge_spot/
grep -r "HourCalculator" custom_components/ge_spot/
grep -r "hour_key" custom_components/ge_spot/

# Check for hardcoded values
grep -r "range(24)" custom_components/ge_spot/
grep -r ":00\"" custom_components/ge_spot/

# Check import errors
python3 -c "from custom_components.ge_spot.const.time import TimeInterval"
```

---

## 📊 Progress Tracking

Update this as you go:

```
Phase 1:  ☐ Not Started  ⏸️ In Progress  ✅ Complete
Phase 2:  ☐ Not Started  ⏸️ In Progress  ✅ Complete
Phase 3:  ☐ Not Started  ⏸️ In Progress  ✅ Complete
Phase 4:  ☐ Not Started  ⏸️ In Progress  ✅ Complete
Phase 5:  ☐ Not Started  ⏸️ In Progress  ✅ Complete
Phase 6:  ☐ Not Started  ⏸️ In Progress  ✅ Complete
Phase 7:  ☐ Not Started  ⏸️ In Progress  ✅ Complete
Phase 8:  ☐ Not Started  ⏸️ In Progress  ✅ Complete
Phase 9:  ☐ Not Started  ⏸️ In Progress  ✅ Complete
Phase 10: ☐ Not Started  ⏸️ In Progress  ✅ Complete
Phase 11: ☐ Not Started  ⏸️ In Progress  ✅ Complete
Phase 12: ☐ Not Started  ⏸️ In Progress  ✅ Complete
Phase 13: ☐ Not Started  ⏸️ In Progress  ✅ Complete

Overall: [__________] 0% → [██████████] 100%
TODOs: 0/27 → 27/27
```

---

## 🎯 Final Steps

### When All Phases Complete:

1. **Run full test suite:**
   ```bash
   cd /workspaces/ge-spot
   python3 -m pytest tests/
   ```

2. **Test in Home Assistant:**
   - Restart Home Assistant
   - Check integration loads
   - Verify sensors show 96 data points
   - Check for errors in logs
   - Test for 24 hours to ensure stability

3. **Clean up planning docs:**
   ```bash
   git rm -r planning_docs/
   git commit -m "Clean up planning documents after successful migration"
   git push origin 15min
   ```

4. **Final commit:**
   ```bash
   git commit --allow-empty -m "Migration complete: 15-minute intervals now active

   All 13 phases completed successfully:
   ✅ Configuration-driven interval system implemented
   ✅ Generic naming applied throughout codebase
   ✅ All 40+ files updated
   ✅ All 415+ variables renamed
   ✅ All tests passing
   ✅ Home Assistant integration working
   
   System now supports 96 intervals per day (15-minute granularity).
   Can easily switch back to hourly by changing TimeInterval.DEFAULT.
   
   Closes: 15-minute interval migration"
   
   git push origin 15min
   ```

5. **Create pull request to main:**
   - Title: "Implement 15-minute interval support"
   - Description: Reference planning docs and benefits
   - Request review if needed
   - Merge when approved

---

## 📝 Notes to Self (AI)

### When I (Copilot) implement this:

1. **ALWAYS read full files** - No shortcuts
2. **Follow the plan exactly** - It's comprehensive for a reason
3. **Test after each phase** - Catch issues early
4. **Commit frequently** - Can revert if needed
5. **Use configuration methods** - Never hardcode
6. **Be consistent** - Same pattern everywhere
7. **Update progress** - Keep track of where I am
8. **Ask if unsure** - Better to clarify than mess up

### Remember:
- This is production code for a real user
- Home Assistant integration affects real homes
- Electricity pricing is time-sensitive and important
- Code quality matters - it's replacing a working system
- User wants clean, maintainable, future-proof code
- Configuration-driven is the key architectural principle

---

## 🚀 Ready to Execute

When you're ready to start:

1. Acknowledge you've read this document
2. Acknowledge you've read MASTER_MIGRATION_PLAN.md
3. Confirm understanding of:
   - Configuration-driven approach
   - Generic naming convention
   - Phase-by-phase process
   - Testing requirements
4. Ask any clarifying questions
5. Begin with Phase 1, TODO-001

**Let's make this migration perfect!** 🎯

---

**Document Version:** 1.0  
**Last Updated:** October 1, 2025  
**Status:** Ready for Implementation
