# 15-Minute Interval Migration - Executive Summary

**Date:** October 1, 2025  
**Branch:** 15min  
**Status:** Planning Complete - Ready for Implementation

---

## 🎯 Objective

Migrate GE-Spot from hourly electricity price intervals to 15-minute intervals, with a **configuration-driven, generic architecture** that makes future interval changes trivial.

---

## 📊 Scope of Changes

### Impact Assessment
- **Files to modify:** 40+ Python files
- **Code occurrences:** 389 "hourly", 734 "hour", 415 key variables
- **Test assertions:** 196+ updates needed
- **Data volume:** 4x increase (24 → 96 data points per day)

### Why This Matters
Swedish electricity market (and EU) now prices electricity every 15 minutes instead of hourly, starting October 1, 2025. This integration must adapt to provide accurate, real-time pricing data.

---

## 🏗️ Architecture Approach

### ⭐ Key Innovation: Configuration-Driven Design

**Single Point of Control:**
```python
# Change ONLY this to switch interval duration:
TimeInterval.DEFAULT = QUARTER_HOURLY  # 15-minute intervals
# or
TimeInterval.DEFAULT = HOURLY  # Back to hourly
```

**Everything auto-adapts:**
- Interval duration (15 or 60 minutes)
- Intervals per day (96 or 24)
- Time format ("HH:MM" keys)
- DST handling (92/100 or 23/25 intervals)
- Statistics calculations
- Parser logic
- Sensor attributes

### Generic Naming Strategy

| Old (Hour-specific) | New (Generic) | Benefit |
|---------------------|---------------|---------|
| `hourly_prices` | `interval_prices` | Works for any duration |
| `HourCalculator` | `IntervalCalculator` | Not tied to hours |
| `next_hour_price` | `next_interval_price` | Future-proof |
| `"HH:00"` format | `"HH:MM"` format | Supports all minutes |

**Why Generic?**
- ✅ Easy to change to 5-min, 30-min, or any future interval
- ✅ No hardcoded assumptions
- ✅ Testable with both hourly and 15-min modes
- ✅ Clean, maintainable code

---

## 📋 Implementation Plan

### 10 Phases, 24 TODO Items

#### Phase 1: Core Constants & Time Handling (2 TODOs)
- Implement configuration-driven interval system
- Update default update interval to 15 minutes

#### Phase 2: Data Structures (2 TODOs)
- Rename `HourlyPrice` → `IntervalPrice`
- Update `StandardizedPriceData` fields

#### Phase 3: API Layer (3 TODOs)
- Create generic expansion utility for APIs
- Update base API documentation
- Update all 9 parser implementations

#### Phase 4: Coordinator & Processing (3 TODOs)
- Update data processor for variable intervals
- Update price manager
- Update cache logic

#### Phase 5: Sensor Layer (3 TODOs)
- Rename sensor properties
- Update attributes (24 → 96 data points)
- Update display logic

#### Phase 6: Price Processing (3 TODOs)
- Update formatter
- Update statistics (works with any interval count)
- Update timezone handling

#### Phase 7: Utilities (3 TODOs)
- Update timezone utilities
- Update other utility functions
- Update validation logic

#### Phase 8: Configuration & Translations (3 TODOs)
- Update UI strings
- Update config flow
- Remove hour-specific language

#### Phase 9: Testing (3 TODOs)
- Update unit tests (24 → 96 expectations)
- Update integration tests
- Update manual tests

#### Phase 10: Documentation (1 TODO)
- Update all documentation

---

## 🔄 API Strategy

### API-Specific Handling

**Known Status:**
- ✅ **ENTSO-E:** Already supports PT15M (15-minute data)!
- ⚠️ **NordPool:** Likely now supports 15-min (check on Oct 1)
- ❓ **Others:** Most likely hourly, need expansion

**Expansion Strategy:**
For APIs providing only hourly data, we'll duplicate the hourly price across all intervals within that hour using a **generic expansion function** that works for any interval duration.

```python
# If API gives hourly: "14:00" → 50 EUR
# We expand to: "14:00" → 50, "14:15" → 50, "14:30" → 50, "14:45" → 50
```

This keeps the integration working immediately while APIs transition to 15-minute data.

---

## 📈 Data Changes

### Current vs. New

| Aspect | Current (Hourly) | New (15-Min) | Multiplier |
|--------|------------------|--------------|------------|
| Data points/day | 24 | 96 | 4x |
| Format | "HH:00" | "HH:MM" | - |
| Update interval | 30 min | 15 min | 2x faster |
| DST spring | 23 hours | 92 intervals | 4x |
| DST fall | 25 hours | 100 intervals | 4x |

### Performance Considerations
- **Storage:** 4x more data points
- **Processing:** Minimal impact (statistics scale linearly)
- **Cache:** May need larger TTL, but managed automatically
- **Memory:** Negligible increase (~3KB → ~12KB per day)

---

## ✅ Quality Assurance

### Design Principles Followed
1. ✅ **Clean code:** No added complexity
2. ✅ **Generic naming:** Future-proof terminology
3. ✅ **Configuration-driven:** Single point of control
4. ✅ **Incremental:** Phase-by-phase approach
5. ✅ **Tested:** Each phase has checkpoint
6. ✅ **Documented:** Comprehensive guides created

### Documentation Artifacts
- ✅ `IMPLEMENTATION_PLAN_15MIN.md` - Detailed 10-phase plan
- ✅ `FACT_FINDING_15MIN.md` - Complete code analysis
- ✅ `GENERIC_NAMING_GUIDE.md` - Quick reference for developers
- ✅ `MIGRATION_SUMMARY.md` - This executive summary

---

## 🚀 Next Steps

### Ready to Implement
1. ✅ Planning complete
2. ✅ Architecture designed
3. ✅ Documentation created
4. ☐ **Get approval** from maintainer
5. ☐ **Start Phase 1:** Core constants & time handling
6. ☐ Test incrementally after each phase

### Expected Timeline
- **Phase 1-2:** 2-3 hours (Core infrastructure)
- **Phase 3:** 3-4 hours (API layer, most critical)
- **Phase 4-6:** 2-3 hours (Processing & display)
- **Phase 7-8:** 1-2 hours (Utilities & config)
- **Phase 9-10:** 2-3 hours (Testing & docs)
- **Total:** ~10-15 hours of focused development

### Success Criteria
- [ ] All 40+ files updated
- [ ] All 415+ variables renamed
- [ ] All tests passing (updated expectations)
- [ ] Integration works with real APIs
- [ ] Can switch between hourly/15-min by changing ONE constant
- [ ] Clean, maintainable code
- [ ] No backward compatibility needed (fresh start)

---

## 🎓 Key Learnings for Future

This migration establishes a **configuration-driven pattern** that makes the codebase resilient to future market changes:

- **5-minute intervals?** Change one constant.
- **30-minute intervals?** Change one constant.
- **Different intervals per region?** Extend the pattern.

The generic naming ensures the code reads naturally regardless of the interval duration, and the configuration-driven approach means we'll never need a migration of this scale again.

---

## 📞 Questions?

Review these documents in order:
1. This summary (overview)
2. `GENERIC_NAMING_GUIDE.md` (quick reference)
3. `IMPLEMENTATION_PLAN_15MIN.md` (detailed plan)
4. `FACT_FINDING_15MIN.md` (complete analysis)

**Ready to proceed with Phase 1!** 🚀
