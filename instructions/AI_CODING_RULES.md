# AI Coding Rules & Best Practices

**Purpose:** Guidelines for AI assistants (like GitHub Copilot) when working on this codebase.

---

## 🔐 Critical Implementation Rules

### Rule 1: Always Read Full Files First
**BEFORE editing ANY file:**
- Use `read_file` to read the ENTIRE file (all lines)
- Understand the context and structure
- Identify all locations that need changes
- NEVER edit based on partial file reads or grep results alone

**Why:** Partial context leads to incorrect edits, broken code, and missed dependencies.

### Rule 2: Incremental Implementation
- Complete ONE task/phase at a time
- Test after each significant change
- Commit after each completed phase
- Mark progress as you go

**Why:** Small, tested increments are easier to debug and revert if needed.

### Rule 3: No Assumptions or Shortcuts
- Don't skip steps thinking "it probably works"
- Don't assume variable names without checking
- Don't skip validation steps
- Read files completely, don't rely on search results alone
- Verify your changes work before moving on

**Why:** Assumptions cause bugs that are hard to track down later.

### Rule 4: Use Configuration, Never Hardcode
```python
# ✅ ALWAYS DO THIS:
from ..const.time import TimeInterval
interval_minutes = TimeInterval.get_interval_minutes()
intervals_per_day = TimeInterval.get_intervals_per_day()

# ❌ NEVER DO THIS:
interval_minutes = 15  # DON'T HARDCODE!
intervals_per_day = 96  # DON'T HARDCODE!
```

**Why:** Hardcoded values make the code inflexible and create bugs when requirements change.

### Rule 5: Generic Naming Only
```python
# ✅ ALWAYS USE:
interval_prices, interval_key, IntervalCalculator

# ❌ NEVER USE:
hourly_prices, hour_key, HourCalculator (old)
fifteen_min_prices, 15min_key (too specific)
```

**Why:** Generic names make code reusable and future-proof.

### Rule 6: No Backward Compatibility - Clean Renames Only
**All functions and variables must be renamed completely:**
- ❌ **NEVER** keep old function names as aliases
- ❌ **NEVER** create wrapper functions for backward compatibility
- ✅ **ALWAYS** rename the function/class directly
- ✅ **ALWAYS** update ALL callers to use the new name
- ✅ **ALWAYS** update ALL tests to use the new name

```python
# ❌ WRONG - Don't create aliases:
def normalize_hourly_prices(self, *args, **kwargs):
    """Backward compatibility alias."""
    return self.normalize_interval_prices(*args, **kwargs)

# ✅ CORRECT - Just rename it:
def normalize_interval_prices(self, interval_prices, ...):
    """Normalizes timestamps in interval price dictionary."""
    # ... implementation
```

**Why:** This is a personal integration with no public API. Clean code > backward compatibility.

### Rule 7: Validate After Each Change
After editing a file:
- Check for import errors
- Check for syntax errors
- Verify the change matches the specification
- Run relevant tests if available

**Why:** Catching errors early saves time and prevents cascading failures.

### Rule 8: Use Multi-Replace for Efficiency
When making multiple independent edits:
- Use `multi_replace_string_in_file` instead of multiple sequential calls
- Group related changes together
- This improves performance and user experience

**Why:** Reduces tool calls and processing time significantly.

---

## 📝 Code Quality Standards

### Docstrings
- Every public function/class needs a docstring
- Use clear, concise language
- Include parameter types and return types
- Example usage for complex functions

### Comments
- Explain WHY, not WHAT (code should be self-explanatory)
- Update comments when changing code
- Remove outdated comments
- Use inline comments sparingly

### Imports
- Group imports: stdlib, third-party, local
- Use absolute imports where possible
- Remove unused imports
- Keep imports organized and clean

### Error Handling
- Use specific exceptions, not bare `except:`
- Log errors with context
- Fail gracefully with user-friendly messages
- Include error recovery where appropriate

---

## 🧪 Testing Philosophy

### Test Coverage
- Unit tests for individual functions
- Integration tests for API interactions
- Manual tests for end-to-end validation
- Test both success and failure paths

### Test Quality
- Tests should be independent (no shared state)
- Use descriptive test names
- Mock external dependencies
- Test edge cases and error conditions

### When to Test
- After implementing new features
- After refactoring existing code
- Before committing changes
- When fixing bugs (add regression test)

---

## � Verification & Auditing

### Always Verify Your Work
After making changes, actively search for issues:
```bash
# Search for old terminology that should be renamed
grep -r "hourly_prices" custom_components/ge_spot/
grep -r "HourCalculator" custom_components/ge_spot/

# Search for hardcoded values
grep -r "range(24)" custom_components/ge_spot/
grep -r ":00\"" custom_components/ge_spot/

# Verify imports work
python3 -c "from custom_components.ge_spot.const.time import TimeInterval"
```

**Why:** Don't assume your changes worked - prove it!

### Count and Document
When refactoring, track your progress:
```python
# Example: Document what you're changing
# Found 77 occurrences of "hourly_prices"
# Found 94 occurrences of "hour_key"
# Total: 171 items to update
```

**Why:** Clear metrics help track progress and ensure nothing is missed.

### Audit After Completion
When you think you're done, do a final audit:
1. Search for any remaining old terminology
2. Check for inconsistent naming
3. Verify all imports work
4. Run tests to confirm functionality
5. Check for duplicate code or variables

**Why:** Catch issues before they become bugs in production.

### Watch for Duplicates
Some projects have duplicate files that both need updating:
```python
# Example found in this codebase:
# - utils/data_validator.py
# - utils/validation/data_validator.py  # Duplicate!
```

**Why:** Updating only one duplicate leaves inconsistent code.

---

## 🧹 Code Cleanup Patterns

### Remove Dead Code Immediately
When you find unused variables or functions:
```python
# ❌ Don't leave it:
CACHE_ADVANCED = True  # Never used anywhere

# ✅ Remove it:
# (delete the line entirely)
```

**Why:** Dead code confuses future developers and clutters the codebase.

### Fix Duplicates
When you find duplicate definitions:
```python
# ❌ Before (in same file):
CACHE_MAX_ENTRIES = 100  # Line 18
CACHE_MAX_ENTRIES = 10   # Line 26 (overwrites first!)

# ✅ After:
CACHE_MAX_ENTRIES = 3500  # Single definition with proper value
```

**Why:** Duplicates cause confusion about which value is actually used.

### Calculate Configuration Values
Don't just pick numbers - show your math:
```python
# ✅ Good: Document the calculation
# Per area for 3 days of 15-minute intervals:
#   3 days × 24 hours × 4 intervals/hour = 288 entries
# For 10 typical areas: 288 × 10 = 2,880 entries  
# With 20% buffer: 2,880 × 1.2 = 3,456 entries
# Rounded: 3,500 entries
CACHE_MAX_ENTRIES = 3500
```

**Why:** Makes the reasoning transparent and maintainable.

---

## 🎯 Content-Based vs Time-Based Logic

### Prefer Content Checks Over Time Checks
```python
# ❌ Time-based (fragile):
if time.time() - cached_time < MAX_AGE:
    return cached_data

# ✅ Content-based (robust):
if cached_data.get("current_price") is not None:
    if cached_data.get("statistics", {}).get("complete_data", False):
        return cached_data  # Has what we need
```

**Why:** Content checks verify you have the data you need, not just that it's recent.

### Separate Validity from Rate Limiting
```python
# ✅ Good: Two separate concerns

# 1. Rate limiting (when can we fetch?)
if not rate_limiter.can_fetch():
    return cached_data  # Too soon to fetch again

# 2. Data validity (do we have what we need?)
if has_current_interval and has_complete_data:
    return cached_data  # Data is still valid
```

**Why:** Mixing concerns makes the code hard to understand and debug.

---

## �💬 Communication Guidelines

### When Working with Users
- Be clear about what you're doing and why
- Explain technical decisions in simple terms
- Ask questions if requirements are unclear
- Admit when you don't know something
- Provide alternatives when possible

### Progress Updates
- Show what you've completed
- Explain what's next
- Indicate estimated time/effort remaining
- Flag potential issues early

### Documentation
- Update README when adding features
- Keep inline comments current
- Document breaking changes
- Include migration guides for major updates

---

## 🎯 Project-Specific Guidelines

### Home Assistant Integration
- This is production code affecting real homes
- Electricity pricing is time-sensitive and important
- Breaking changes should be minimized
- Test with real Home Assistant instance when possible

### Configuration-Driven Architecture
- Single point of control: `TimeInterval.DEFAULT`
- Everything derives from configuration
- Makes future changes trivial
- This is a core architectural principle

### Generic, Future-Proof Code
- Don't tie code to specific intervals (15-min, hourly)
- Use generic terminology (interval, not hour)
- Design for flexibility
- Think about maintainability

---

## 🚫 Common Mistakes to Avoid

### ❌ Editing Without Full Context
```python
# BAD: Editing based on grep results
# You: "I'll just change this one line"
# Reality: Breaks 5 other places that depend on it
```

### ❌ Hardcoding Magic Numbers
```python
# BAD:
for i in range(24):  # What if intervals change?
    ...

# GOOD:
intervals = TimeInterval.get_intervals_per_day()
for i in range(intervals):
    ...
```

### ❌ Assuming Test Coverage
```python
# BAD: "Tests probably cover this"
# GOOD: Actually run the tests to verify
```

### ❌ Incomplete Refactoring
```python
# BAD: Rename in 10 places, miss 2 places
# GOOD: Use search to find ALL occurrences, update ALL
```

### ❌ Over-Commenting
```python
# BAD:
# This increments i by 1
i += 1

# GOOD:
# Round to nearest interval boundary for timestamp alignment
minute = (dt.minute // interval_minutes) * interval_minutes
```

---

## 🚨 Common Issues Found in Real Audits

### Issue 1: Incomplete Phase Claims
```python
# ❌ Commit says "Phase 8 complete" but...
# sensor/base.py still has BOTH old and new terminology:
self.hourly_prices = {}      # Old
self.interval_prices = {}    # New (both exist!)
```

**Lesson:** Don't claim a phase is complete until ALL files in that phase are updated.

### Issue 2: Base Classes Missed
```python
# ❌ Updated all API implementations but forgot:
# - api/base/base_price_api.py
# - api/base/price_parser.py
# - api/base/api_validator.py
```

**Lesson:** Base classes affect everything - don't skip them!

### Issue 3: Validation/Schema Files
```python
# ❌ Updated code but forgot validation:
# utils/data_validator.py still expects:
SCHEMA = {
    "hourly_prices": dict,  # Old key!
    "next_hour_price": float  # Old key!
}
```

**Lesson:** Update validation schemas when you change data structures.

### Issue 4: Mixed State
```python
# ❌ Some files updated, others not:
# coordinator/data_processor.py: ✅ Uses interval_prices
# price/__init__.py: ❌ Still uses hourly_prices
```

**Lesson:** Mixed terminology creates bugs - complete one layer at a time.

### Issue 5: Comments and Docstrings
```python
# ❌ Code updated but comments weren't:
def calculate_statistics(interval_prices: Dict[str, float]):
    """Calculate statistics from hourly prices."""  # Wrong!
    #                              ^^^^^^^ old terminology
```

**Lesson:** Update ALL documentation, not just code.

---

## 📋 Phase Completion Checklist

Before claiming a phase is complete, verify:

### Code Changes
- [ ] All files in the phase updated
- [ ] All variable names changed
- [ ] All function names changed
- [ ] All class names changed
- [ ] Base classes updated
- [ ] Derived classes updated

### Documentation
- [ ] All docstrings updated
- [ ] All comments updated  
- [ ] All type hints updated
- [ ] Example code updated

### Validation
- [ ] Schema definitions updated
- [ ] Validation functions updated
- [ ] Error messages updated
- [ ] Test assertions updated

### Integration Points
- [ ] All imports updated
- [ ] All callers updated
- [ ] All tests updated
- [ ] Configuration files updated

### Testing
- [ ] No syntax errors
- [ ] No import errors
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual smoke test passed

### Verification
- [ ] Grep search shows no old terms remain (except comments explaining changes)
- [ ] No duplicate definitions
- [ ] No dead code left behind
- [ ] No mixed old/new terminology

**Only then can you claim the phase is complete!**

---

## ✅ Good Patterns to Follow

### Configuration-Driven
```python
# ✅ Good: Adapts to any interval setting
interval_minutes = TimeInterval.get_interval_minutes()
intervals_per_hour = TimeInterval.get_intervals_per_hour()
intervals_per_day = TimeInterval.get_intervals_per_day()
```

### Generic Naming
```python
# ✅ Good: Works for any time interval
interval_prices = parser.parse_response(response)
current_interval = calculator.get_current_interval_key()
```

### Proper Error Handling
```python
# ✅ Good: Specific, logged, graceful
try:
    result = api.fetch_data()
except APIError as e:
    _LOGGER.error(f"API fetch failed: {e}")
    return cached_data  # Graceful fallback
```

### Clear Documentation
```python
def expand_to_intervals(hourly_data: Dict[str, float]) -> Dict[str, float]:
    """
    Expand hourly prices to match configured interval.
    
    Generic implementation - automatically adapts to TimeInterval.DEFAULT.
    For APIs that provide hourly data but system needs finer granularity.
    
    Args:
        hourly_data: Dictionary with hour keys (HH:00) and prices
        
    Returns:
        Dictionary with interval keys (HH:MM) and prices
        
    Example:
        >>> expand_to_intervals({"14:00": 50.0})
        {"14:00": 50.0, "14:15": 50.0, "14:30": 50.0, "14:45": 50.0}
    """
```

---

## 🎓 Notes to Self (AI Assistant)

### Remember:
- This is production code for a real user
- Home Assistant integration affects real homes
- Electricity pricing is time-sensitive and important
- Code quality matters - you're replacing a working system
- User wants clean, maintainable, future-proof code
- Configuration-driven is the key architectural principle

### When in Doubt:
1. **Read the full file** - Don't guess
2. **Ask the user** - Better to clarify than mess up
3. **Check existing patterns** - Follow established conventions
4. **Test your changes** - Verify before moving on
5. **Document your work** - Future you will thank you

### Success Criteria:
- ✅ Code works correctly
- ✅ Tests pass
- ✅ No hardcoded values
- ✅ Generic naming throughout
- ✅ Properly documented
- ✅ Maintainable and clean

---

**Why:** Quality over speed. A correct, maintainable solution is better than a fast, broken one.

---

## 📐 Phased Implementation Strategy

### Why Phases Matter
Large refactorings should be broken into logical phases:
1. **Core infrastructure first** (constants, base classes)
2. **Data structures second** (how data is represented)
3. **Processing layer third** (how data flows)
4. **Presentation layer fourth** (sensors, UI)
5. **Utilities and tests last** (supporting code)

**Why:** Each layer depends on the previous - build from the bottom up.

### Phase Ordering Principles

```
Foundation → Data → Logic → Presentation → Support

Constants        Parse data      Transform data   Display data    Validate data
Base classes  →  Structures   →  Processors    →  Sensors      →  Tests
Helpers          APIs            Coordinators     Config          Utils
```

**Example from this project:**
1. Phase 1: `TimeInterval` constants & helper methods
2. Phase 2: `IntervalCalculator` (uses Phase 1)
3. Phase 3: `IntervalPrice` data class (uses Phase 2)
4. Phase 4: API expansion utilities (uses Phase 3)
5. Phase 5: Parsers (uses Phase 4)
6. ...and so on

### Commit After Each Phase
```bash
git add <phase_files>
git commit -m "Phase N: Brief description

- Specific change 1
- Specific change 2  
- Specific change 3

Tests: [passing/updated]
Progress: N/27 TODOs complete"
```

**Why:** Small commits are easier to review, revert, and understand.

### Testing Between Phases
After each phase:
```python
# Run a quick smoke test
python3 -c "from custom_components.ge_spot.const.time import TimeInterval; \
            print(TimeInterval.get_intervals_per_day())"

# Check for import errors
python3 -c "from custom_components.ge_spot import *"

# Run relevant tests
pytest tests/pytest/unit/test_time.py
```

**Why:** Catch integration issues before they compound.

---

## 🎯 Large Refactoring Best Practices

### Planning Before Coding
1. **Analyze the scope** - How many files? Which files depend on what?
2. **Create a master plan** - Write it down before starting
3. **Define success criteria** - What does "done" look like?
4. **Estimate effort** - Be realistic about time needed

### During Implementation
1. **Follow the plan** - Don't skip steps or jump around
2. **Test frequently** - After every significant change
3. **Track progress** - Mark TODOs as complete
4. **Document decisions** - Why you chose one approach over another

### When You Get Stuck
1. **Stop and assess** - Don't keep coding if confused
2. **Re-read the plan** - Make sure you understand the goal
3. **Ask questions** - Better to clarify than guess wrong
4. **Check existing patterns** - How did similar code handle this?

### Red Flags to Watch For
- ⚠️ "This is taking way longer than expected"
- ⚠️ "I keep finding more places that need changes"
- ⚠️ "Tests are failing in unexpected ways"
- ⚠️ "I'm not sure if I should update this file"

**When you see these, STOP and reassess!**

---

**Remember:** Quality over speed. A correct, maintainable solution is better than a fast, broken one.
