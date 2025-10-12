# Issue #3: Validation Key Format Mismatch - Investigation Guide

**Status:** INVESTIGATION REQUIRED - DO NOT FIX WITHOUT RUNTIME DATA  
**Area:** DK1  
**Source:** energi_data_service  
**Severity:** HIGH  
**Impact:** DK1 validation fails, causing unnecessary fallback to other sources

---

## Problem Summary

DK1 energi_data_service returns data successfully, but validation fails claiming "current interval price not found in interval_raw". This causes unnecessary fallback to other sources even though data is valid.

---

## Evidence from debug.log (2025-10-12)

```log
Line 80: [DK1] Parser energi_data_service_parser output keys: ['interval_raw', 'current_price', ...]
Line 81: energi_data_service: Validation FAILED - current interval price not found in interval_raw
Line 82: [DK1] Parsed data validation failed for source 'energi_data_service' - trying next source
Line 83: [DK1] Attempting fallback to source 'entsoe'
```

**Key observation:** Parser creates `interval_raw` but validation can't find current interval price within it.

---

## Root Cause Analysis

### What We Know

1. **Parser succeeds** - Creates `interval_raw` dictionary
2. **Validation fails** - Can't find current interval key
3. **Fallback works** - ENTSO-E provides data instead
4. **Not a total failure** - DK1 gets data, just not from preferred source

### What We DON'T Know (Requires Runtime Investigation)

1. **What are the actual keys in `interval_raw`?**
   - Are they in format "HH:MM"?
   - Are they ISO timestamps?
   - Are they datetime objects?
   - Are they in different timezone?

2. **What is the current interval key being searched for?**
   - What format does validation expect?
   - What timezone is it using?

3. **Is this parser-specific or a general issue?**
   - Does it affect other parsers?
   - Is it specific to energi_data_service API structure?

---

## Investigation Steps (DO NOT SKIP)

### Step 1: Add Detailed Debug Logging

**File:** `custom_components/ge_spot/api/parsers/energi_data_service.py`

Add after creating `interval_raw`:

```python
# After building interval_raw dictionary
if interval_raw:
    sample_keys = list(interval_raw.keys())[:10]  # First 10 keys
    _LOGGER.debug(f"[energi_data_service] interval_raw contains {len(interval_raw)} entries")
    _LOGGER.debug(f"[energi_data_service] Sample keys: {sample_keys}")
    _LOGGER.debug(f"[energi_data_service] Key types: {[type(k).__name__ for k in sample_keys]}")
else:
    _LOGGER.warning(f"[energi_data_service] interval_raw is EMPTY after parsing!")
```

**File:** `custom_components/ge_spot/api/parsers/price_parser.py`

Add in `validate_parsed_data()` method:

```python
def validate_parsed_data(self, data: Dict[str, Any]) -> bool:
    """Validate that parsed data contains current interval price."""
    if not data or not isinstance(data, dict):
        _LOGGER.warning(f"{self.source}: Parsed data is None or not a dict")
        return False
    
    interval_raw = data.get("interval_raw", {})
    if not interval_raw:
        _LOGGER.warning(f"{self.source}: interval_raw is empty")
        return False
    
    # ADD THIS DEBUG LOGGING
    from homeassistant.util import dt as dt_util
    now = dt_util.now()
    current_key = now.strftime("%H:%M")
    
    _LOGGER.debug(f"[{self.source}] Validation check:")
    _LOGGER.debug(f"  - Current time: {now}")
    _LOGGER.debug(f"  - Looking for key: '{current_key}'")
    _LOGGER.debug(f"  - interval_raw has {len(interval_raw)} entries")
    _LOGGER.debug(f"  - First 5 keys in interval_raw: {list(interval_raw.keys())[:5]}")
    
    current_price = self._get_current_price(interval_raw)
    
    if current_price is None:
        _LOGGER.warning(f"{self.source}: Current interval price not found in interval_raw - failing validation")
        _LOGGER.debug(f"  - Searched for any of: {current_key}, datetime variants, ISO formats")
        _LOGGER.debug(f"  - Available keys: {list(interval_raw.keys())}")
        return False
    
    _LOGGER.debug(f"{self.source}: Validation passed - found current price: {current_price}")
    return True
```

### Step 2: Capture Runtime Data

1. **Deploy debug logging** to production
2. **Clear cache** for DK1: `rm -f /config/.storage/ge_spot_cache_DK1_*.json`
3. **Restart Home Assistant**
4. **Wait for DK1 fetch** (should happen within 5 minutes)
5. **Capture logs** showing validation attempt

### Step 3: Analyze Captured Data

Look for:

```
[energi_data_service] Sample keys: [...]
[energi_data_service] Validation check:
  - Current time: 2025-10-12 13:45:00+02:00
  - Looking for key: '13:45'
  - interval_raw has X entries
  - First 5 keys in interval_raw: [...]
```

**Compare:**
- What key format is being searched for? (e.g., "13:45")
- What keys actually exist? (e.g., "2025-10-12T13:45:00+02:00" or datetime objects)
- Is there a mismatch?

---

## Possible Root Causes (Hypotheses)

### Hypothesis 1: Timezone Mismatch
**Symptom:** Keys in UTC, search in Europe/Copenhagen  
**Example:**
- Looking for: "13:45" (Copenhagen time)
- Keys are: "11:45" (UTC time)
- Mismatch: 2 hour difference

**Fix:** Ensure parser normalizes timestamps to HA timezone before creating keys

### Hypothesis 2: Key Format Mismatch
**Symptom:** Keys are full ISO timestamps, not "HH:MM"  
**Example:**
- Looking for: "13:45"
- Keys are: "2025-10-12T13:45:00+02:00"
- Mismatch: Format difference

**Fix:** Either change parser to create "HH:MM" keys, or change validation to search ISO format

### Hypothesis 3: Datetime Object Keys
**Symptom:** Keys are datetime objects, not strings  
**Example:**
- Looking for: "13:45" (string)
- Keys are: datetime(2025, 10, 12, 13, 45) (object)
- Mismatch: Type difference

**Fix:** Convert datetime keys to "HH:MM" strings in parser

### Hypothesis 4: Parser Validation Logic Issue
**Symptom:** Parser creates correct keys but validation logic has bug  
**Example:**
- Keys are correct: "13:45"
- But `_get_current_price()` doesn't check this format
- Mismatch: Logic bug

**Fix:** Update `_get_current_price()` to handle all key formats

### Hypothesis 5: Empty interval_raw
**Symptom:** Parser fails silently, creates empty dict  
**Example:**
- Parser encounters error parsing API response
- Returns empty `interval_raw` instead of raising exception
- Validation fails on empty dict

**Fix:** Improve parser error handling to raise exceptions instead of returning empty data

---

## What NOT To Do

❌ **DO NOT** modify `_get_current_price()` without understanding the actual issue  
❌ **DO NOT** assume key format without seeing actual runtime data  
❌ **DO NOT** change parser output format without checking impact on other code  
❌ **DO NOT** skip debug logging step - runtime data is essential  

---

## Correct Investigation Flow

```
1. Add debug logging to parser and validator
   ↓
2. Deploy to production and capture logs
   ↓
3. Analyze actual keys vs. expected keys
   ↓
4. Identify exact mismatch (format, timezone, type, etc.)
   ↓
5. Design fix based on evidence
   ↓
6. Implement fix in correct location (parser OR validator, not both)
   ↓
7. Test with real API data
   ↓
8. Verify DK1 energi_data_service validation succeeds
```

---

## Expected Validation Flow (How It Should Work)

### Normal Case (Working)
```
1. API returns data with timestamps
2. Parser converts to interval_raw: {"13:45": 1.234, "14:00": 1.567, ...}
3. Validation gets current time: 13:48
4. Validation looks for "13:45" key (current interval)
5. Key found → validation SUCCESS
6. Data processor uses the data
```

### DK1 energi_data_service Case (Broken)
```
1. API returns data with timestamps ← NEED TO SEE THIS
2. Parser converts to interval_raw: {???} ← NEED TO SEE THIS
3. Validation gets current time: 13:48
4. Validation looks for "13:45" key
5. Key NOT found → validation FAIL
6. Fallback to next source
```

**The ??? is what we need runtime data to reveal.**

---

## Debug Logging Deployment

### Option 1: Manual Edit (Quick)
```bash
# Edit the parser file directly
nano /config/custom_components/ge_spot/api/parsers/energi_data_service.py

# Add debug logging as shown in Step 1 above

# Edit the validator file
nano /config/custom_components/ge_spot/api/parsers/price_parser.py

# Add debug logging as shown in Step 1 above

# Restart Home Assistant
# Settings > System > Restart
```

### Option 2: Git Patch (Proper)
```bash
# Create a debug-logging branch
git checkout -b debug-issue-3

# Add debug logging to files
# (make edits as shown in Step 1)

# Commit changes
git add custom_components/ge_spot/api/parsers/energi_data_service.py
git add custom_components/ge_spot/api/parsers/price_parser.py
git commit -m "Add debug logging for Issue #3 investigation"

# Deploy to production
git push origin debug-issue-3

# Pull on production server
cd /config/custom_components/ge_spot
git fetch
git checkout debug-issue-3

# Restart Home Assistant
```

---

## Success Criteria for Investigation

After adding debug logging and capturing data, you should be able to answer:

- [ ] What format are the keys in `interval_raw` for energi_data_service?
- [ ] What timezone are the keys in?
- [ ] What key format is validation searching for?
- [ ] Why doesn't the search match the actual keys?
- [ ] Is this specific to energi_data_service or affects other parsers?

Once these are answered, the fix becomes obvious and can be implemented confidently.

---

## After Investigation: Implementing the Fix

Based on what you discover, the fix will be ONE of these:

### Fix Type 1: Parser Needs to Normalize Keys
**If:** Keys are in wrong format/timezone  
**Action:** Update energi_data_service parser to create "HH:MM" keys in HA timezone

### Fix Type 2: Validator Needs to Handle More Formats
**If:** Keys are valid but validator doesn't recognize them  
**Action:** Update `_get_current_price()` to search more key formats

### Fix Type 3: Parser Has Bug
**If:** Parser returns empty or malformed interval_raw  
**Action:** Fix parser logic to correctly build interval_raw dict

### Fix Type 4: Timezone Conversion Missing
**If:** Parser creates keys in UTC instead of HA timezone  
**Action:** Add timezone conversion step in parser

---

## Timeline Estimate

- **Debug logging deployment:** 15 minutes
- **Wait for DK1 fetch:** 5-30 minutes  
- **Log analysis:** 10 minutes
- **Fix implementation:** 30-60 minutes
- **Testing:** 30 minutes

**Total:** 2-3 hours from start to verified fix

---

## Related Files

- `custom_components/ge_spot/api/parsers/energi_data_service.py` - Parser that creates interval_raw
- `custom_components/ge_spot/api/parsers/price_parser.py` - Base validator that checks interval_raw
- `custom_components/ge_spot/timezone/timezone_converter.py` - Timezone utilities
- `custom_components/ge_spot/utils/interval_calculator.py` - Interval key generation

---

## Notes

- **Do not guess** - Runtime data is required
- **Other parsers work** - So validator logic is generally correct
- **Fallback succeeds** - So DK1 isn't completely broken
- **Only energi_data_service fails validation** - Parser-specific issue most likely

This is a **data format issue**, not a logic issue. We need to see the actual data to fix it correctly.
