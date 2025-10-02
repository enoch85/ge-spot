# AI Coding Rules & Best Practices

**Purpose:** Guidelines for AI assistants (like GitHub Copilot) when working on this codebase.

---

## 🔐 Critical Implementation Rules

### Rule 0: No Verbose Summaries
**After making changes:**
- DO NOT provide lengthy summaries or recaps
- DO NOT create bulleted lists of what was changed
- DO NOT write "implementation complete" paragraphs
- ONLY respond with confirmation if asked
- Let the user ask questions if they need clarification

**Why:** Summaries waste time and tokens. The user can see the changes in their editor.

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
from ..const.config import Config
item_duration = Config.get_item_duration()
items_per_cycle = Config.get_items_per_cycle()

# ❌ NEVER DO THIS:
item_duration = 15  # DON'T HARDCODE!
items_per_cycle = 96  # DON'T HARDCODE!
```

**Why:** Hardcoded values make the code inflexible and create bugs when requirements change.

### Rule 5: Generic Naming Only
```python
# ✅ ALWAYS USE:
# Generic, reusable names
data_items, item_key, DataProcessor, process_records()

# ❌ NEVER USE:
# Overly specific or implementation-detail names
hourly_data, record_24, DataProcessor24Hour, process_exactly_24()
daily_data_15min, fifteen_minute_key (too specific to current implementation)
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
def process_old_format(self, *args, **kwargs):
    """Backward compatibility alias."""
    return self.process_new_format(*args, **kwargs)

# ✅ CORRECT - Just rename it:
def process_new_format(self, data, ...):
    """Processes data in the new format."""
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

### Test Production Code, Not Tests

**Priority:** Test that the actual production code works correctly.

```python
# ✅ Good: Test production functionality with real calls
def test_api_fetch_real_data():
    """Test actual API can fetch and parse real data."""
    api = ProductionAPI(api_key="test_key")
    result = api.fetch_data(region="TEST")
    
    assert result is not None
    assert "data" in result
    assert len(result["data"]) > 0

# ❌ Bad: Testing the test helpers
def test_mock_returns_correct_structure():
    """Test that our mock returns what we expect."""
    mock_data = create_mock_data()
    assert mock_data["field"] == "expected"
```

**When to Use Mocks:**
- External API calls that cost money or have rate limits
- External services that require authentication
- Slow operations (database, network) in unit tests
- Non-deterministic behavior (random, timestamps)

**When to Use Real Calls:**
- Integration tests verifying end-to-end flow
- Testing parsers with real API response structures
- Validating configuration and connection logic
- Smoke tests before deployment

### Test Coverage

- **Unit tests** for individual functions (fast, isolated, use mocks)
- **Integration tests** for API interactions (real calls, verify production works)
- **Manual tests** for end-to-end validation (real Home Assistant, real data)
- **Test both success and failure paths** (happy path + error handling)

### Test Quality

- Tests should be independent (no shared state)
- Use descriptive test names (`test_parser_handles_empty_response`)
- Don't mock what you're testing (mock dependencies only)
- Verify behavior, not implementation details
- Test edge cases and error conditions

### When to Test

- After implementing new features
- After refactoring existing code
- Before committing changes
- When fixing bugs (add regression test)
- **Run integration tests to verify production APIs work correctly**

---

## � Verification & Auditing

### Always Verify Your Work
After making changes, actively search for issues:
```bash
# Search for old terminology that should be renamed
grep -r "old_function_name" custom_components/
grep -r "OldClassName" custom_components/

# Search for hardcoded values that should use configuration
grep -r "range(24)" custom_components/
grep -r "fixed_value" custom_components/

# Verify imports work
python3 -c "from custom_components.ge_spot.module import NewClass"
```

**Why:** Don't assume your changes worked - prove it!

### Count and Document
When refactoring, track your progress:
```python
# Example: Document what you're changing
# Found 77 occurrences of "old_api_call"
# Found 94 occurrences of "deprecated_method"
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
CACHE_MAX_ENTRIES = 1000  # Single definition with proper value
```

**Why:** Duplicates cause confusion about which value is actually used.

### Calculate Configuration Values
Don't just pick numbers - show your math:
```python
# ✅ Good: Document the calculation
# Per area for 3 days of data at current resolution:
#   3 days × 24 hours × resolution_factor = base_entries
# For typical_areas configured: base × typical_areas = total
# With buffer_percent buffer: total × (1 + buffer) = final
# Example: 3 × 24 × 4 × 10 × 1.2 = 3,456 → round to 3,500
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
if cached_data.get("required_field") is not None:
    if cached_data.get("statistics", {}).get("data_complete", False):
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
if has_required_data and data_is_complete:
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
- Single point of control for major settings
- Everything derives from configuration
- Makes future changes trivial
- This is a core architectural principle

### Generic, Future-Proof Code
- Don't tie code to specific implementation details
- Use generic terminology that scales
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
for i in range(24):  # What if requirements change?
    ...

# GOOD:
item_count = Config.get_item_count()
for i in range(item_count):
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
# Round to nearest time boundary for timestamp alignment
value = (raw_value // resolution) * resolution
```

---

## 🚨 Common Issues Found in Real Audits

### Issue 1: Incomplete Phase Claims
```python
# ❌ Commit says "Phase 8 complete" but...
# Files still have BOTH old and new terminology:
self.old_data = {}      # Old
self.new_data = {}      # New (both exist - incomplete transition!)
```

**Lesson:** Don't claim a phase is complete until ALL files in that phase are fully updated.

### Issue 2: Base Classes Missed
```python
# ❌ Updated all implementations but forgot:
# - api/base/base_api.py
# - api/base/parser.py
# - api/base/validator.py
```

**Lesson:** Base classes affect everything - they're often the most important to update first!

### Issue 3: Validation/Schema Files
```python
# ❌ Updated code but forgot validation:
# utils/validator.py still expects:
SCHEMA = {
    "old_key": dict,  # Old key!
    "deprecated_field": float  # Old field!
}
```

**Lesson:** Update validation schemas when you change data structures.

### Issue 4: Mixed State
```python
# ❌ Some files updated, others not:
# coordinator/processor.py: ✅ Uses new_data_structure
# utils/helper.py: ❌ Still uses old_data_structure
```

**Lesson:** Mixed terminology creates bugs - complete one layer at a time.

### Issue 5: Comments and Docstrings
```python
# ❌ Code updated but comments weren't:
def calculate_stats(new_data: Dict[str, float]):
    """Calculate statistics from old data format."""  # Wrong!
    #                              ^^^ outdated terminology
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
# ✅ Good: Adapts to configuration changes
item_duration = Config.get_item_duration()
items_per_cycle = Config.get_items_per_cycle()
items_per_day = Config.get_items_per_day()
```

### Generic Naming
```python
# ✅ Good: Works for any time period or data structure
data_items = parser.parse_response(response)
current_item = calculator.get_current_item_key()
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
def expand_data(source_data: Dict[str, float]) -> Dict[str, float]:
    """
    Expand source data to match configured target resolution.
    
    Generic implementation - automatically adapts to Config.get_resolution().
    For sources that provide coarse data but system needs finer granularity.
    
    Args:
        source_data: Dictionary with source keys and values
        
    Returns:
        Dictionary with target resolution keys and values
        
    Example:
        >>> expand_data({"00:00": 50.0})
        {"00:00": 50.0, "00:15": 50.0, "00:30": 50.0, "00:45": 50.0}
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
- Run smoke tests to verify imports work
- Check for syntax errors
- Run relevant unit tests
- Verify integration points

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
