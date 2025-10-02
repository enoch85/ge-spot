# Instructions for AI Assistants

This directory contains guidelines for AI coding assistants (like GitHub Copilot) working on the GE-Spot integration.

---

## 📁 Files in This Directory

### Core Guidelines

**`AI_CODING_RULES.md`** - Comprehensive coding rules and best practices
- Critical implementation rules (read files fully, no hardcoding, etc.)
- Code quality standards
- Testing philosophy
- Common mistakes to avoid
- Verification and auditing techniques
- Phase completion checklists
- Large refactoring strategies

### Policy Documents

**`NO_BACKWARD_COMPATIBILITY.md`** - Project policy on clean renames
- No aliases or wrapper functions
- Direct renaming only
- Update ALL callers

**`EV_SMART_CHARGING_COMPATIBILITY.md`** - Integration requirements
- Sensor attribute contracts
- Compatibility with EV Smart Charging integration
- Required data formats

---

## 🚀 Quick Start for AI Assistants

### Before Starting Any Work

1. **Read `AI_CODING_RULES.md`** from start to finish
2. **Read `NO_BACKWARD_COMPATIBILITY.md`** to understand the policy
3. **Review the README.md** in the repository root for project context
4. **Ask clarifying questions** if anything is unclear

### Core Principles

1. ✅ **Always read full files** before editing
2. ✅ **Use configuration, never hardcode** values
3. ✅ **Use generic naming** (interval, not hour or 15min)
4. ✅ **Test after each change** to verify it works
5. ✅ **Commit frequently** with clear messages
6. ✅ **Verify your work** by searching for old terminology

### The Golden Rule

**This is production code affecting real homes and electricity pricing.**

Quality and correctness are more important than speed.

---

## 🎯 Project-Specific Context

### Architecture Philosophy

**Configuration-Driven Design:**
```python
# Single point of control
TimeInterval.DEFAULT = QUARTER_HOURLY  # Change this one line

# Everything else adapts automatically
interval_minutes = TimeInterval.get_interval_minutes()  # Returns 15
intervals_per_day = TimeInterval.get_intervals_per_day()  # Returns 96
```

**Generic Naming:**
```python
# ✅ Good: Works for any interval
interval_prices, interval_key, IntervalCalculator

# ❌ Bad: Tied to specific values
hourly_prices, fifteen_min_key, QuarterHourCalculator
```

**Clean Renames Only:**
```python
# ✅ Good: Direct rename
def normalize_interval_prices(self, interval_prices):
    # ... implementation

# ❌ Bad: Backward compatibility wrapper
def normalize_hourly_prices(self, *args):
    return self.normalize_interval_prices(*args)  # NO!
```

### Home Assistant Integration

- This is a custom component for Home Assistant
- Affects real homes and electricity costs
- Time-sensitive data (prices change every 15 minutes)
- Must be reliable and maintainable
- Users depend on it for automation decisions

### Testing Requirements

- Unit tests for individual functions
- Integration tests for API interactions
- Manual tests for end-to-end validation
- Test both success and failure paths
- Mock external dependencies

---

## 📚 Additional Resources

### In This Repository

- `/workspaces/ge-spot/README.md` - Project overview and features
- `/workspaces/ge-spot/tests/README.md` - Testing guide
- `/workspaces/ge-spot/custom_components/ge_spot/` - Source code

### External References

- [Home Assistant Developer Docs](https://developers.home-assistant.io/)
- [Home Assistant Architecture](https://developers.home-assistant.io/docs/architecture_index)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
- [pytest Documentation](https://docs.pytest.org/)

---

## ✅ Success Checklist

Before considering your work complete:

### Code Quality
- [ ] No hardcoded values (use configuration)
- [ ] Generic naming throughout
- [ ] All imports work
- [ ] No syntax errors
- [ ] No duplicate code

### Documentation
- [ ] Docstrings updated
- [ ] Comments updated
- [ ] Type hints correct
- [ ] Examples work

### Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual smoke test successful
- [ ] No regressions introduced

### Verification
- [ ] Searched for old terminology (none found)
- [ ] All files in scope updated
- [ ] Base classes and derived classes aligned
- [ ] Validation schemas match code

---

## 🆘 When in Doubt

1. **Read the full file** - Don't guess based on partial context
2. **Check AI_CODING_RULES.md** - The answer might be there
3. **Look for existing patterns** - Follow established conventions
4. **Ask the user** - Clarification is better than wrong assumptions
5. **Test your changes** - Verify before moving on

---

## 📝 Feedback & Improvements

These guidelines evolve based on real-world experience. If you discover:
- A pattern that should be added
- A common mistake not covered
- A better way to explain something
- An outdated recommendation

**Document it!** Future AI assistants (and humans) will benefit.

---

**Last Updated:** October 2, 2025  
**For:** GE-Spot Home Assistant Integration  
**Maintained By:** Repository owner with AI assistance
