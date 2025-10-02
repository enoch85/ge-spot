# TODO: Post 1.2.0 Release Items

This folder contains important findings and planned improvements to be implemented after the 1.2.0 release.

## 🐛 Critical Bug Fix: Attribute Reset Issue

**Priority:** HIGH  
**Estimated Time:** 1-2 hours  
**Impact:** Significantly improves user experience

### Issue
Home Assistant attributes reset/reload at random intervals (6-15 seconds), making it difficult for users to read attribute data.

### Root Cause Identified
Cache mutation bug where cached data is modified directly instead of working on copies, creating a feedback loop.

### Documentation
- **`ATTRIBUTE_RESET_BUG_FIX.md`** - Complete technical analysis and fix plan
- **`ATTRIBUTE_RESET_QUICK_FIX.md`** - Quick reference with exact code changes
- **`debug_attribute_reset.py`** - Diagnostic script to verify the issue

### Files to Modify (4 small changes)
1. `custom_components/ge_spot/coordinator/cache_manager.py` - Change shallow copy to deep copy
2. `custom_components/ge_spot/coordinator/unified_price_manager.py` - Remove 2 instances of direct cache mutation

### Implementation Steps
1. Apply deep copy fix in cache_manager.py
2. Replace cache mutations with copies in unified_price_manager.py  
3. Test timing pattern (should stabilize to ~15 minute intervals)
4. Verify attributes remain stable in UI

### Testing
Run `python3 TODO/debug_attribute_reset.py` before and after fixes to verify timing improvement.

---

## 📋 Other TODOs

Add additional post-release items here as needed.

---

**Created:** October 2, 2025  
**Target Release:** 1.2.1 or 1.3.0  
**Status:** Ready for implementation
