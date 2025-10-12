# Runtime Testing Guide - Branch 1.4.1 PR #20

**Date:** 2025-10-12  
**Fixes Implemented:** Issues #1, #2, #4  
**Pending Investigation:** Issue #3

---

## Overview

Three critical fixes have been implemented and need runtime validation:

1. ✅ **Issue #1** - Stale cached data (DK2, PL) - Commit 0ba632f
2. ✅ **Issue #2** - Health check rate limit bypass (DK1, ES) - Commit f220245
3. ✅ **Issue #4** - Double rate-limit check removed (ES) - Commit f220245

**All 198 unit tests pass** - but runtime testing is required to validate real-world behavior.

---

## Pre-Testing Setup

### 1. Backup Current State
```bash
# Backup current cache
cp -r /config/.storage/ge_spot_cache /config/.storage/ge_spot_cache.backup

# Backup current config
cp /config/.storage/core.config_entries /config/.storage/core.config_entries.backup

# Note current sensor states
# In Home Assistant Developer Tools > States, save current values for:
# - sensor.electricity_price_dk1
# - sensor.electricity_price_dk2
# - sensor.electricity_price_es
# - sensor.electricity_price_pl
```

### 2. Enable Debug Logging
Add to `/config/configuration.yaml`:
```yaml
logger:
  default: warning
  logs:
    custom_components.ge_spot: debug
    custom_components.ge_spot.coordinator.data_processor: debug
    custom_components.ge_spot.coordinator.unified_price_manager: debug
    custom_components.ge_spot.coordinator.fetch_decision: debug
```

Restart Home Assistant after adding logging.

### 3. Clear Cache (Fresh Start)
```bash
# Remove all cache files
rm -f /config/.storage/ge_spot_cache_*.json

# Clear Python cache
find /config/custom_components/ge_spot -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
```

---

## Testing Phase 1: Issue #4 (Double Rate-Limit Check)

**Target:** ES area  
**Expected:** Fetch proceeds when fetch decision allows it  
**Timeline:** Immediate (can test during health check window 13:00-15:00)

### Test Steps

1. **Restart Home Assistant** with cleared cache
2. **Monitor logs immediately** after restart
3. **Look for:**
   ```
   ✅ GOOD: "Fetch decision approved. Proceeding with fetch."
   ✅ GOOD: "Successfully fetched data from omie for ES"
   ❌ BAD: "Rate limiting in effect for area ES... Next fetch in 840 seconds"
   ❌ BAD: "Rate limited for ES (after decision check)"
   ```

4. **Wait for health check window** (13:00-15:00 UTC or 00:00-01:00 UTC)
5. **Verify health check runs:**
   ```
   ✅ GOOD: "Starting health check for X sources"
   ✅ GOOD: "Health check bypass - validating source omie"
   ✅ GOOD: "Health check completed. Validated: ['omie', ...]"
   ❌ BAD: "Rate limiting: SKIPPING fetch - Last fetch was only X minutes ago"
   ```

### Success Criteria
- [ ] ES sensor shows price data within 5 minutes of restart
- [ ] No "after decision check" errors in logs
- [ ] Health check validates ES during window without rate limit blocks
- [ ] Logs show "Fetch decision approved" before successful fetches

---

## Testing Phase 2: Issue #2 (Health Check Rate Limit Bypass)

**Target:** DK1, ES areas  
**Expected:** Health check validates sources even if recently fetched  
**Timeline:** Wait for health check window (13:00-15:00 or 00:00-01:00 UTC)

### Test Steps

1. **Wait for health check window** to begin
2. **Monitor logs for health check start:**
   ```
   Daily health check starting in Xs
   Starting health check for X sources
   ```

3. **Verify bypass flag behavior:**
   ```
   ✅ GOOD: "Health check - bypassing rate limit for source energi_data_service"
   ✅ GOOD: "Health check - bypassing rate limit for source omie"
   ✅ GOOD: "Validated sources: ['energi_data_service', 'omie', ...]"
   ❌ BAD: "Rate limiting: SKIPPING fetch" (during health check)
   ❌ BAD: "Health check failed - sources rate limited"
   ```

4. **Check health check completes:**
   ```
   ✅ GOOD: "Health check completed. Validated: [list], Failed: []"
   ✅ GOOD: "Next health check scheduled for [time in next window]"
   ```

5. **Verify sensors update** if health check found new data

### Success Criteria
- [ ] Health check runs exactly once per window (not multiple times)
- [ ] Health check validates all sources without rate limit blocking
- [ ] Logs show "bypassing rate limit" during health check
- [ ] DK1 and ES sensors don't get stuck in "Unknown" state
- [ ] Normal fetches outside health check still respect rate limiting

---

## Testing Phase 3: Issue #1 (Stale Cached Data)

**Target:** DK2, PL areas  
**Expected:** Cached data uses correct current date, not yesterday's date  
**Timeline:** 30+ minutes (need multiple coordinator updates to test cache reuse)

### Test Steps

1. **Initial fetch** (cache should be empty from pre-testing setup)
2. **Wait for successful data fetch:**
   ```
   ✅ GOOD: "Successfully fetched data from stromligning for DK2"
   ✅ GOOD: "Successfully fetched data from energy_charts for PL"
   ```

3. **Wait 15 minutes** for next coordinator update
4. **Monitor cache reuse:**
   ```
   ✅ GOOD: "Processing cached data from source 'stromligning'"
   ✅ GOOD: "Using already-processed prices from cache (today=96, tomorrow=96)"
   ✅ GOOD: "Skipping normalization - using already-processed cache data"
   ✅ GOOD: "Skipping currency conversion - using already-converted cache data"
   ❌ BAD: "Normalized ... timestamps: ['2025-10-11 00:00', '2025-10-11 00:15', ...]"
   ❌ BAD: "Split prices into today (96 intervals) and tomorrow (0 intervals)"
   ```

5. **Check sensor attributes:**
   ```bash
   # In Developer Tools > States > sensor.electricity_price_dk2
   # Check 'today' attribute contains prices with current date
   # Check 'tomorrow' attribute contains prices (should be 96 intervals if available)
   ```

6. **Verify statistics:**
   ```
   ✅ GOOD: Today's average/min/max show reasonable values
   ✅ GOOD: Tomorrow's prices appear (if API provides them)
   ❌ BAD: All prices in 'today' attribute but 'tomorrow' empty when API has future data
   ```

### Success Criteria
- [ ] DK2 and PL show current date prices (2025-10-12, not 2025-10-11)
- [ ] Logs show "Using already-processed prices from cache"
- [ ] Logs show "Skipping normalization" and "Skipping currency conversion"
- [ ] No re-normalization of cached raw data (no "2025-10-11" timestamps in logs)
- [ ] Tomorrow prices appear when available from API
- [ ] Statistics calculate correctly across multiple updates

---

## Testing Phase 4: Cache Migration (Midnight Rollover)

**Target:** All areas  
**Expected:** Tomorrow's prices become today's prices at midnight  
**Timeline:** Wait until midnight (00:00 local time)

### Test Steps

1. **Before midnight** (23:50), verify sensors have tomorrow data:
   ```bash
   # Check sensor.electricity_price_dk1 attributes
   # Verify 'tomorrow' contains 96 price entries
   ```

2. **At midnight** (00:00-00:10), monitor logs:
   ```
   ✅ GOOD: "Found yesterday's cached data from [source] with tomorrow's prices"
   ✅ GOOD: "Using it for today's prices after midnight transition"
   ✅ GOOD: "Migrated from tomorrow to today"
   ```

3. **After midnight** (00:15), verify:
   ```bash
   # Check sensor attributes
   # 'today' should contain the prices that were 'tomorrow' before midnight
   # 'tomorrow' should be empty (until new data fetched)
   ```

### Success Criteria
- [ ] Yesterday's tomorrow prices become today's today prices
- [ ] Cache migration logged clearly
- [ ] No data loss during transition
- [ ] Sensors update without showing "Unknown"

---

## Testing Phase 5: Regression Testing

**Target:** All areas  
**Expected:** No existing functionality broken  
**Timeline:** Full 24-hour cycle

### Areas to Monitor

1. **Normal Fetch Cycles**
   - [ ] 15-minute rate limiting still works
   - [ ] Fetches occur during interval boundaries
   - [ ] No infinite retry loops

2. **Currency Conversion**
   - [ ] Prices convert from source currency to target currency
   - [ ] ECB rates update correctly
   - [ ] VAT calculations accurate

3. **Timezone Handling**
   - [ ] Timestamps normalized to HA timezone
   - [ ] Current interval detection works
   - [ ] Next interval prediction accurate

4. **Statistics**
   - [ ] Today's average/min/max calculate correctly
   - [ ] Tomorrow's statistics appear when data available
   - [ ] Peak/off-peak calculations work

5. **Sensor Attributes**
   - [ ] `current_price` shows correct value for current time
   - [ ] `next_interval_price` shows next interval's price
   - [ ] `today` attribute contains all 96 intervals
   - [ ] `tomorrow` attribute populates when available

---

## Log Analysis Commands

### Monitor Live Logs
```bash
# Follow logs in real-time
tail -f /config/home-assistant.log | grep "ge_spot"

# Filter for specific area
tail -f /config/home-assistant.log | grep "DK1"

# Watch for errors only
tail -f /config/home-assistant.log | grep -E "(ERROR|WARNING)" | grep "ge_spot"
```

### Search for Specific Patterns
```bash
# Check for stale date issues (Issue #1)
grep "2025-10-11" /config/home-assistant.log | grep "ge_spot"

# Check for rate limit conflicts (Issue #4)
grep "after decision check" /config/home-assistant.log

# Check health check execution (Issue #2)
grep "Health check" /config/home-assistant.log | grep "ge_spot"

# Check cache reuse
grep "already-processed prices" /config/home-assistant.log
```

### Extract Key Metrics
```bash
# Count successful fetches by source
grep "Successfully fetched data from" /config/home-assistant.log | cut -d' ' -f8 | sort | uniq -c

# Count cache hits vs misses
grep -c "Using already-processed prices from cache" /config/home-assistant.log
grep -c "Processing fresh (non-cached) data" /config/home-assistant.log

# Check health check frequency
grep "Starting health check" /config/home-assistant.log | awk '{print $1, $2}'
```

---

## Troubleshooting

### Problem: ES still shows "Rate limited after decision check"
**Cause:** Issue #4 fix not working  
**Action:**
1. Verify commit 0ba632f is deployed
2. Check unified_price_manager.py lines 559-600 don't re-check rate limiting
3. Clear Python cache: `find /config/custom_components/ge_spot -name "__pycache__" -type d -exec rm -rf {} +`
4. Restart Home Assistant

### Problem: DK2/PL still showing yesterday's dates
**Cause:** Issue #1 fix not working  
**Action:**
1. Verify commit f220245 is deployed
2. Check logs for "Using already-processed prices from cache"
3. If seeing "Using 'raw_interval_prices_original' from cache", investigate why validation failed
4. Clear cache: `rm -f /config/.storage/ge_spot_cache_*.json`
5. Restart Home Assistant

### Problem: Health check not bypassing rate limits
**Cause:** Issue #2 fix not working  
**Action:**
1. Verify commit f220245 is deployed
2. Check for "Health check - bypassing rate limit" in logs
3. Verify health check window (13:00-15:00 or 00:00-01:00 UTC)
4. Check `_health_check_in_progress` flag is set correctly

### Problem: Sensors stuck in "Unknown"
**Possible causes:**
1. Cache is corrupt → Clear cache and restart
2. API is down → Check API source status
3. Rate limiting too aggressive → Wait for health check window
4. Validation failing → Check logs for validation errors

**Action:**
1. Check debug logs for specific error
2. Verify API sources are accessible
3. Clear cache if corrupted
4. Wait for health check window to validate sources

---

## Success Metrics

### After 24 Hours of Runtime

**Critical Success:**
- [ ] All areas (DK1, DK2, ES, PL, SE4, SA1) show current prices
- [ ] No sensors stuck in "Unknown" state for >1 hour
- [ ] No "2025-10-11" timestamps in logs after 2025-10-12 00:00
- [ ] No "after decision check" rate limit errors

**Performance Success:**
- [ ] Cache hit rate >80% (using processed cache, not re-normalizing)
- [ ] Health check runs 2 times per day (once per window)
- [ ] Fetch count reasonable (not infinite loops)
- [ ] API call frequency within rate limits

**Data Quality Success:**
- [ ] Today prices: 92-100 intervals (accounting for DST)
- [ ] Tomorrow prices: 96 intervals when available
- [ ] Currency conversion accurate
- [ ] Statistics match manual calculations

---

## Rollback Procedure

If critical issues found:

```bash
# 1. Checkout previous working commit
git checkout f220245^  # Go back before Issue #1 fix

# 2. Or revert specific commits
git revert 0ba632f  # Revert Issue #1
git revert f220245  # Revert Issues #2 and #4

# 3. Push changes
git push

# 4. Restart Home Assistant
# (or wait for auto-reload if enabled)

# 5. Clear cache
rm -f /config/.storage/ge_spot_cache_*.json

# 6. Document what failed for analysis
```

---

## Next Steps After Successful Testing

1. **Document findings** - Create summary of test results
2. **Address Issue #3** - Requires runtime debugging (separate investigation)
3. **Monitor long-term** - Watch for edge cases over 1 week
4. **Merge to main** - If all tests pass and stable for 48+ hours
5. **Release notes** - Document fixes for users

---

## Issue #3 Investigation (Separate Task)

**Not included in current fixes** - requires runtime debugging first.

See `ISSUE_3_INVESTIGATION.md` for details on validation key format mismatch affecting DK1 energi_data_service.

**Action:** Do NOT attempt to fix without runtime logs showing actual key formats.
