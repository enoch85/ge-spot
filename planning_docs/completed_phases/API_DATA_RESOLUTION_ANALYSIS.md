# API Data Resolution Analysis

## Purpose
This document analyzes what data resolution each API actually provides to determine the correct parser logic for 15-minute interval migration.

## Analysis by API Source

### 1. ENTSO-E ✅ CORRECT
**API Provides:** PT15M (15-minute), PT30M (30-minute), PT60M (hourly) - varies by region
**Current Code:** Already handles all resolutions correctly with resolution preference: ["PT15M", "PT30M", "PT60M"]
**Parser Logic:** Pass-through - stores whatever resolution the API provides
**Status:** ✅ **NO CHANGES NEEDED** - Already correct!
**Evidence:** Code explicitly checks for `resolution_elem.text == "PT15M"` and processes accordingly

---

### 2. Nord Pool ❓ NEEDS INVESTIGATION
**API Provides:** Historically hourly, but transitioning to 15-minute MTU
**Current Code:** Processes timestamps directly from API response
**Parser Logic:** Pass-through - stores whatever the API provides
**Key Finding:** Nord Pool announced "TRANSITION TO 15-MINUTE MARKET TIME UNIT (MTU)" on their website
**Status:** ⚠️ **MONITOR** - API may provide 15-min or hourly depending on rollout
**Action Needed:** 
- Check if API response already includes 15-minute intervals
- If still hourly, use `expand_to_intervals()` utility
- Document which markets/regions support 15-min

**Reference:** https://www.nordpoolgroup.com/en/trading/transition-to-15-minute-market-time-unit-mtu/

---

### 3. EPEX Spot ✅ PROVIDES 15-MINUTE
**API Provides:** 15-minute products available ("15-minute products in Market Coupling")
**Current Code:** Processes timestamps directly from API response
**Parser Logic:** Pass-through - stores whatever the API provides
**Status:** ✅ **LIKELY CORRECT** - EPEX supports 15-minute products
**Evidence:** EPEX website shows "15-minute products in Market Coupling" as an active feature
**Action Needed:** Verify current parser handles 15-minute timestamps correctly

**Reference:** https://www.epexspot.com/en/15-minute-products-market-coupling

---

### 4. OMIE (Iberian Market) ⏰ HOURLY ONLY
**API Provides:** Hourly data only
**Current Code:** Processes hourly timestamps
**Parser Logic:** Pass-through - stores hourly data
**Status:** 🔧 **NEEDS EXPANSION** - Use `expand_to_intervals()` in API layer
**Action Needed:**
- Call `expand_to_intervals()` in API implementation to duplicate hourly prices to 15-minute intervals
- Document that OMIE only provides hourly resolution
- Consider adding note about data granularity limitation

---

### 5. ComEd 🚨 **CRITICAL - AGGREGATION ISSUE**
**API Provides:** **5-minute interval data** via `5minutefeed` endpoint
**Current Code:** **INCORRECTLY aggregates 5-min data to hourly averages**
**Parser Logic:** Groups by hour using `timestamp.replace(minute=0, second=0, microsecond=0)`
**Status:** 🔴 **BROKEN LOGIC** - Must change aggregation to 15-minute intervals
**Code Issue:**
```python
# WRONG - Currently aggregates to hourly:
hour_dt = timestamp.replace(minute=0, second=0, microsecond=0)
hour_prices[interval_key].append(price)
avg_price = sum(prices) / len(prices)  # Averages all 5-min prices in hour
```

**Required Fix:**
```python
# CORRECT - Should aggregate to 15-minute intervals:
# Round to nearest 15-minute interval: 00, 15, 30, 45
minute_rounded = (timestamp.minute // 15) * 15
interval_dt = timestamp.replace(minute=minute_rounded, second=0, microsecond=0)
interval_prices[interval_key].append(price)
avg_price = sum(prices) / len(prices)  # Averages 3x 5-min prices per 15-min interval
```

**Evidence:** ComEd API has endpoint called "5minutefeed" and code comment says "hourly aggregation from 5-min data"

---

### 6. Stromligning (Denmark) ⏰ HOURLY ONLY
**API Provides:** Hourly data only
**Current Code:** Processes hourly timestamps with `.replace(minute=0, second=0, microsecond=0)`
**Parser Logic:** Pass-through hourly data
**Status:** 🔧 **NEEDS EXPANSION** - Use `expand_to_intervals()` in API layer
**Action Needed:**
- Call `expand_to_intervals()` in API implementation
- Document hourly-only limitation

---

### 7. Energi Data Service (Denmark) ⏰ HOURLY ONLY
**API Provides:** Hourly data (HourUTC / HourDK fields)
**Current Code:** Processes hourly timestamps
**Parser Logic:** Pass-through hourly data
**Status:** 🔧 **NEEDS EXPANSION** - Use `expand_to_intervals()` in API layer
**Action Needed:**
- Call `expand_to_intervals()` in API implementation
- Field names "HourUTC" and "HourDK" confirm hourly resolution

---

### 8. Amber (Australia) ⏰ 30-MINUTE INTERVALS
**API Provides:** 30-minute intervals (follows NEM settlement periods)
**Current Code:** Processes timestamps directly from API (`startTime`, `nemTime`)
**Parser Logic:** Pass-through - stores whatever API provides (30-min intervals)
**Status:** ✅ **NO ACTION NEEDED** - 30-min is acceptable (can't split to 15-min without interpolation)
**Notes:** 
- Australian NEM uses 30-minute trading/settlement intervals
- Amber passes through wholesale prices at NEM's 30-minute resolution
- Cannot aggregate 30-min to 15-min (would require price interpolation which would be inaccurate)
- Document limitation: Amber provides 30-minute intervals only
**Reference:** Amber API documentation at https://app.amber.com.au/developers/documentation/

---

### 9. AEMO (Australia) 🚨 **5-MINUTE DATA - CRITICAL ISSUE**
**API Provides:** **5-minute dispatch intervals** (documented in aemo.py comment)
**Current Code:** Processes timestamps with `.replace(minute=0, second=0, microsecond=0)` - **DESTROYS DATA!**
**Parser Logic:** Currently rounds to hour (incorrect) - **loses all 5-minute granularity**
**Status:** 🔴 **BROKEN LOGIC** - Rounding to hour loses all 5-min interval data
**Issue:** API provides 5-minute real-time spot prices, but code rounds everything to the hour
**Required Fix:** 
- **Option 1 (Recommended):** Aggregate 5-min data to 15-min intervals (average 3 values per 15-min)
- **Option 2:** Keep native 5-min resolution (96 → 288 intervals per day)
- Remove `.replace(minute=0, second=0, microsecond=0)` logic that destroys timestamp precision

**Evidence:** Comment in aemo.py line 16-18: "AEMO provides real-time spot prices at 5-minute intervals"
**Reference:** AEMO NEM uses 5-minute dispatch intervals for spot pricing

---

## Summary Table

| API Source | Native Resolution | Current Parser | Required Action | Priority |
|------------|------------------|----------------|-----------------|----------|
| ENTSO-E | PT15M/PT30M/PT60M | ✅ Correct | None | ✅ Done |
| Nord Pool | Transitioning to 15-min | Pass-through | Verify API response | ⚠️ Medium |
| EPEX | 15-minute | Pass-through | Verify timestamps | ⚠️ Low |
| OMIE | Hourly | Pass-through | Add expansion | 🔧 Medium |
| ComEd | **5-minute** | 🔴 Hourly aggregation | **Fix: 5-min → 15-min aggregation** | 🔴 **Critical** |
| Stromligning | Hourly | Pass-through | Add expansion | 🔧 Medium |
| Energi Data | Hourly (HourUTC) | Pass-through | Add expansion | 🔧 Medium |
| Amber | 30-minute (NEM) | ✅ Pass-through | Document limitation | ✅ OK |
| AEMO | **5-minute** | 🔴 Hourly rounding | **Fix: 5-min → 15-min aggregation** | 🔴 **Critical** |

## Critical Issues Found

### 🔴 ComEd Parser - Losing 5-Minute Data
**Problem:** API provides 5-minute data, but parser aggregates to hourly, losing granularity
**Impact:** Users lose detailed price information
**Fix:** Change aggregation from hourly to 15-minute intervals (average 3x 5-min values)

### 🔴 AEMO Parser - Destroying Time Resolution
**Problem:** Parser rounds all timestamps to the hour with `.replace(minute=0, second=0, microsecond=0)`
**Impact:** Loses 30-minute or 5-minute interval data from API
**Fix:** Remove hour-rounding logic, process actual timestamps from API

## Action Plan

### Phase 1: Critical Fixes (Must Do)
1. ✅ Document actual API resolutions (this file)
2. 🔴 Fix ComEd: Change 5-min → 15-min aggregation (not 5-min → hourly)
3. 🔴 Fix AEMO: Remove hour-rounding, preserve actual intervals
4. ⚠️ Investigate Amber: Determine actual API resolution

### Phase 2: Expansions (Should Do)
5. 🔧 OMIE: Add `expand_to_intervals()` call in API layer
6. 🔧 Stromligning: Add `expand_to_intervals()` call in API layer
7. 🔧 Energi Data: Add `expand_to_intervals()` call in API layer

### Phase 3: Verifications (Nice to Have)
8. ✅ EPEX: Verify 15-minute timestamps work correctly
9. ⚠️ Nord Pool: Monitor MTU transition, verify 15-min support
10. ✅ ENTSO-E: Already correct, no changes needed

## Next Steps

1. **Investigate:** Check actual API responses for Amber and AEMO to confirm data resolution
2. **Fix Parsers:** Update ComEd and AEMO parsers with correct aggregation/rounding logic
3. **Expand APIs:** Add `expand_to_intervals()` calls in API implementations for hourly-only sources
4. **Test:** Verify all parsers handle their native resolutions correctly
5. **Document:** Update each parser's docstrings to reflect actual API resolution

## References

- ENTSO-E API Guide: https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html
- Nord Pool 15-min MTU: https://www.nordpoolgroup.com/en/trading/transition-to-15-minute-market-time-unit-mtu/
- EPEX 15-min Products: https://www.epexspot.com/en/15-minute-products-market-coupling
- ComEd Hourly Pricing: https://hourlypricing.comed.com/ (5-minute feed endpoint)
- AEMO NEM: Uses 5-minute dispatch, 30-minute trading intervals
