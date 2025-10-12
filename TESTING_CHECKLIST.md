# Testing Checklist - Branch 1.4.1 PR #20

**Date:** 2025-10-12  
**Branch:** 1.4.1  
**PR:** #20 - Different fixes  
**Fixes:** Issues #1, #2, #4  
**Test Duration:** 24-48 hours recommended

---

## Pre-Deployment Checklist

### Code Quality
- [x] All 198 unit tests pass
- [x] No syntax errors (`python3 -m py_compile` on all files)
- [x] No import errors
- [x] Code follows project conventions
- [ ] Changes reviewed by maintainer

### Documentation
- [x] IMPLEMENTATION_PLAN.md reviewed
- [x] RUNTIME_TESTING_GUIDE.md created
- [x] ISSUE_3_INVESTIGATION.md created
- [x] Commit messages detailed and clear
- [ ] CHANGELOG.md updated (after successful testing)

### Deployment Prep
- [ ] Backup current production cache
- [ ] Backup current configuration
- [ ] Note current sensor states
- [ ] Enable debug logging
- [ ] Prepare rollback procedure

---

## Phase 1: Initial Deployment (0-30 minutes)

### Pre-Deployment
- [ ] Verify Git branch is 1.4.1
- [ ] Verify commits f220245 and 0ba632f are present
- [ ] Clear Python `__pycache__` directories
- [ ] Backup cache files

### Deployment
- [ ] Pull latest code to production
- [ ] Clear cache for affected areas (DK1, DK2, ES, PL)
- [ ] Restart Home Assistant
- [ ] Monitor startup logs for errors

### Immediate Validation (0-5 minutes)
- [ ] Home Assistant starts successfully
- [ ] GE-Spot integration loads without errors
- [ ] All sensors appear in entity list
- [ ] No critical errors in logs

---

## Phase 2: Issue #4 Testing (5-30 minutes)

**Target:** Double rate-limit check removed (ES area)

### Initial Fetch
- [ ] ES sensor attempts initial fetch
- [ ] Logs show "Fetch decision approved" (not "after decision check")
- [ ] ES successfully fetches from omie source
- [ ] ES sensor shows price data
- [ ] No "Rate limited for ES (after decision check)" errors

### Validation Points
```bash
# Search for the bad pattern (should NOT appear)
grep "after decision check" /config/home-assistant.log

# Search for success pattern (should appear)
grep "Fetch decision approved" /config/home-assistant.log | grep "ES"

# Check ES has data
grep "Successfully fetched data from" /config/home-assistant.log | grep "ES"
```

**Expected Results:**
- ✅ "Fetch decision approved" appears
- ✅ "Successfully fetched data from omie for ES" appears
- ❌ "after decision check" does NOT appear

---

## Phase 3: Issue #2 Testing (Wait for Health Check Window)

**Target:** Health check bypasses rate limiting (DK1, ES areas)  
**Timing:** 13:00-15:00 UTC or 00:00-01:00 UTC

### Before Health Check Window
- [ ] Note last fetch time for DK1 and ES
- [ ] Verify normal rate limiting is working (15-minute minimum)
- [ ] Confirm health check is scheduled

### During Health Check Window
- [ ] Health check starts (log: "Daily health check starting in...")
- [ ] Health check sets bypass flag (log: "Starting health check for X sources")
- [ ] DK1 validates without rate limit block
- [ ] ES validates without rate limit block
- [ ] Health check completes (log: "Health check completed")

### Validation Points
```bash
# Check health check execution
grep "Starting health check" /config/home-assistant.log

# Check bypass flag usage
grep "bypassing rate limit" /config/home-assistant.log

# Verify completion
grep "Health check completed" /config/home-assistant.log

# Should NOT see rate limiting during health check
grep "Health check" /config/home-assistant.log | grep "Rate limiting: SKIPPING"
```

**Expected Results:**
- ✅ Health check runs once per window
- ✅ "bypassing rate limit" appears for each source
- ✅ All sources validate successfully
- ❌ No rate limit blocks during health check
- ✅ Normal rate limiting resumes after health check

### After Health Check
- [ ] Normal fetches respect 15-minute rate limiting
- [ ] Health check scheduled for next window
- [ ] No infinite health check loops
- [ ] Sensors updated if health check found new data

---

## Phase 4: Issue #1 Testing (30+ minutes)

**Target:** Stale cached data fix (DK2, PL areas)

### First Fetch (Cache Empty)
- [ ] DK2 fetches fresh data from stromligning
- [ ] PL fetches fresh data from energy_charts
- [ ] Both parse and process successfully
- [ ] Both store processed data in cache
- [ ] Sensors show current date prices (2025-10-12)

### Second Update (Cache Hit)
**Wait 15-30 minutes for next coordinator update**

- [ ] DK2 uses cached data (log: "Processing cached data from source 'stromligning'")
- [ ] DK2 validates processed cache (log: "Using already-processed prices from cache")
- [ ] DK2 skips normalization (log: "Skipping normalization - using already-processed cache data")
- [ ] DK2 skips currency conversion (log: "Skipping currency conversion - using already-converted cache data")
- [ ] Same for PL

### Validation Points
```bash
# Check for processed cache usage (GOOD)
grep "Using already-processed prices from cache" /config/home-assistant.log

# Check for normalization skip (GOOD)
grep "Skipping normalization" /config/home-assistant.log

# Check for currency conversion skip (GOOD)
grep "Skipping currency conversion" /config/home-assistant.log

# Check for stale dates (BAD - should NOT appear)
grep "2025-10-11" /config/home-assistant.log | grep -E "(DK2|PL)"

# Check for wrong split (BAD - should NOT appear)
grep "Split prices into today (96 intervals) and tomorrow (0 intervals)" /config/home-assistant.log
```

**Expected Results:**
- ✅ "Using already-processed prices from cache" appears
- ✅ "Skipping normalization" appears
- ✅ "Skipping currency conversion" appears  
- ❌ No "2025-10-11" timestamps in logs after cache reuse
- ✅ Sensors show 2025-10-12 prices
- ✅ Tomorrow prices appear (if available from API)

### Sensor Attribute Validation
```bash
# In Home Assistant Developer Tools > States
# Check sensor.electricity_price_dk2 attributes:
```
- [ ] `today` attribute contains ~96 intervals with current date
- [ ] `tomorrow` attribute contains intervals (if API provides)
- [ ] `current_price` matches current interval in `today`
- [ ] Statistics (average, min, max) are reasonable
- [ ] No duplicate intervals
- [ ] No missing intervals

---

## Phase 5: Data Quality Validation (1-2 hours)

### All Areas Check
For each area (DK1, DK2, ES, PL, SE4, SA1):

#### Basic Functionality
- [ ] Sensor state shows numeric price
- [ ] Unit of measurement correct (e.g., "DKK/kWh")
- [ ] State not "Unknown" or "Unavailable"
- [ ] Last updated timestamp recent (<30 min)

#### Attributes Complete
- [ ] `current_price` present and numeric
- [ ] `next_interval_price` present (if available)
- [ ] `today` attribute contains intervals
- [ ] `tomorrow` attribute present (may be empty)
- [ ] `statistics` contains today's avg/min/max

#### Data Consistency
- [ ] Today's prices match expected market values
- [ ] No negative prices (unless market actually negative)
- [ ] No unrealistic values (e.g., 999999)
- [ ] Currency correct for area
- [ ] Timezone correct for area

### Cross-Area Validation
- [ ] DK1 and DK2 prices similar (same market)
- [ ] ES prices reasonable for Spanish market
- [ ] PL prices reasonable for Polish market
- [ ] All sensors update at appropriate intervals
- [ ] No sensor stuck in old state

---

## Phase 6: Cache Behavior (2-4 hours)

### Cache Hit Scenario
After initial fetch, wait for multiple coordinator updates:

**Update 1 (t=0):** Fresh fetch
- [ ] API call made
- [ ] Data parsed and processed
- [ ] Cached with current date

**Update 2 (t=15 min):** Cache hit
- [ ] No API call (rate limited)
- [ ] Cache loaded successfully
- [ ] Processed cache data used
- [ ] No re-normalization
- [ ] No re-conversion

**Update 3 (t=30 min):** Cache hit
- [ ] Same as Update 2
- [ ] Data still fresh and valid

**Update 4 (t=45 min):** Cache hit or new fetch
- [ ] Depends on special windows and rate limits
- [ ] Either cache or fetch, both should work

### Cache Miss Scenario
- [ ] Clear cache manually
- [ ] Coordinator update triggered
- [ ] Fresh fetch occurs
- [ ] New cache created
- [ ] Sensors update with new data

### Cache Validation
```bash
# Check cache files exist
ls -lh /config/.storage/ge_spot_cache_*.json

# Check cache age
stat /config/.storage/ge_spot_cache_DK1_*.json

# Verify cache contains processed data
cat /config/.storage/ge_spot_cache_DK1_*.json | grep "today_interval_prices"
cat /config/.storage/ge_spot_cache_DK1_*.json | grep "tomorrow_interval_prices"
```

---

## Phase 7: Midnight Rollover Testing

**Timing:** 23:50 - 00:30 local time

### Pre-Midnight (23:50-23:59)
- [ ] All sensors have today's prices
- [ ] Tomorrow's prices populated (if available)
- [ ] Cache contains both today and tomorrow data
- [ ] Note: Sample tomorrow prices for comparison

### At Midnight (00:00-00:10)
- [ ] Coordinator update triggers
- [ ] Cache migration occurs (log: "Found yesterday's cached data with tomorrow's prices")
- [ ] Yesterday's tomorrow becomes today's today
- [ ] Sensors update without showing "Unknown"
- [ ] New tomorrow data fetched (if available)

### Post-Midnight (00:10-00:30)
- [ ] Today's prices match pre-midnight's tomorrow prices
- [ ] New tomorrow prices appear (if API provides next day)
- [ ] No data loss during transition
- [ ] All sensors functional

### Validation Points
```bash
# Check for migration logs
grep "midnight transition" /config/home-assistant.log

# Check for migration success
grep "Using it for today's prices after midnight transition" /config/home-assistant.log

# Verify no errors during transition
grep "00:0[0-5]" /config/home-assistant.log | grep -E "(ERROR|WARNING)" | grep "ge_spot"
```

---

## Phase 8: Edge Cases & Stress Testing (4-24 hours)

### Rate Limiting Stress
- [ ] Multiple rapid coordinator updates → only one fetch per 15 min
- [ ] Special windows work (00:00-01:00, 13:00-15:00)
- [ ] Health check doesn't trigger rate limits
- [ ] No infinite retry loops

### Cache Corruption Recovery
- [ ] Delete cache file while HA running → fresh fetch succeeds
- [ ] Corrupt cache JSON → error handled, fresh fetch occurs
- [ ] Old cache format → migrated or refreshed

### API Failure Handling
- [ ] Simulate API timeout → fallback source used
- [ ] Simulate API error response → logged and handled
- [ ] All sources down → cached data used
- [ ] Recovery when API back online → fresh fetch resumes

### DST Transition (If Applicable)
- [ ] During DST spring forward → handles 92 intervals
- [ ] During DST fall back → handles 100 intervals  
- [ ] Interval count varies correctly
- [ ] No missing prices during transition

---

## Phase 9: Performance Metrics (24 hours)

### API Call Frequency
```bash
# Count API calls per source
grep "Successfully fetched data from" /config/home-assistant.log | cut -d' ' -f8 | sort | uniq -c

# Verify reasonable frequency (not too many)
# Expected: ~6-8 calls per source per day (depends on special windows)
```
- [ ] Each source called reasonable number of times
- [ ] No infinite fetch loops
- [ ] Rate limiting effective

### Cache Efficiency
```bash
# Cache hits
grep -c "Using already-processed prices from cache" /config/home-assistant.log

# Cache misses (fresh fetch)
grep -c "Processing fresh (non-cached) data" /config/home-assistant.log

# Calculate hit rate: hits / (hits + misses) * 100%
```
- [ ] Cache hit rate >70%
- [ ] Cache properly stores processed data
- [ ] Cache invalidation works (stale data refreshed)

### Health Check Efficiency
```bash
# Count health checks
grep -c "Starting health check" /config/home-assistant.log

# Expected: 2 per day (one per window)
```
- [ ] Health check runs 2 times per 24 hours
- [ ] No duplicate health checks in same window
- [ ] Health check completes in <60 seconds

### Error Rate
```bash
# Count errors
grep -c "ERROR.*ge_spot" /config/home-assistant.log

# Count warnings
grep -c "WARNING.*ge_spot" /config/home-assistant.log
```
- [ ] Error count minimal (<5 per 24 hours)
- [ ] Warnings reasonable and actionable
- [ ] No critical errors

---

## Phase 10: Regression Testing (24-48 hours)

### Existing Features Still Work
- [ ] Currency conversion functioning
- [ ] VAT calculations correct
- [ ] Timezone conversions accurate
- [ ] Statistics calculations correct
- [ ] Sensor attributes complete
- [ ] Frontend displays correct data

### Integration Points
- [ ] Energy dashboard shows correct prices
- [ ] Automations trigger correctly
- [ ] Template sensors work
- [ ] Lovelace cards display data
- [ ] History graphs accurate

### Configuration Flow
- [ ] Can add new area via config flow
- [ ] Can modify existing area options
- [ ] Can remove area
- [ ] Settings persist across restarts

---

## Success Criteria Summary

### Critical (Must Pass)
- [x] All 198 unit tests pass ✅
- [ ] No sensor stuck in "Unknown" for >1 hour
- [ ] No "2025-10-11" dates after 2025-10-12 00:00
- [ ] No "after decision check" rate limit errors
- [ ] Health check runs successfully
- [ ] Cache reuse works without re-normalization
- [ ] Midnight rollover successful

### Important (Should Pass)
- [ ] Cache hit rate >70%
- [ ] API call frequency reasonable
- [ ] No infinite loops or excessive retries
- [ ] All areas show current prices
- [ ] Tomorrow prices appear when available
- [ ] Statistics accurate

### Nice to Have (Performance)
- [ ] Cache hit rate >80%
- [ ] Health check completes <30 seconds
- [ ] Coordinator updates <5 seconds
- [ ] Memory usage stable

---

## Failure Handling

### If Critical Test Fails

**Immediate Actions:**
1. Capture full debug logs
2. Note which specific test failed
3. Check error messages
4. Verify which commit introduced issue

**Investigation:**
1. Review commit that should fix the issue
2. Verify code is deployed correctly
3. Check for conflicting changes
4. Look for edge case not covered

**Decision Tree:**
- **Minor fix possible?** → Implement quick patch, test again
- **Major issue?** → Rollback commit, document issue, investigate offline
- **Cannot reproduce?** → Monitor longer, may be intermittent

### Rollback Triggers

Execute rollback if:
- [ ] Sensors stuck in "Unknown" for >2 hours
- [ ] Critical errors every update cycle
- [ ] Data corruption detected
- [ ] Cache issues cause system instability
- [ ] Any data safety concern

### Rollback Procedure
```bash
# Method 1: Revert commits
git revert 0ba632f  # Revert Issue #1
git revert f220245  # Revert Issues #2, #4
git push

# Method 2: Checkout previous commit
git checkout <previous-working-commit>
git push -f

# Method 3: Restore from backup
cp /config/.storage/ge_spot_cache.backup/* /config/.storage/
# Restore code from backup
```

---

## Sign-Off Checklist

After 24-48 hours of successful testing:

### Code Quality
- [ ] All critical tests passed
- [ ] All important tests passed
- [ ] Performance acceptable
- [ ] No regressions detected

### Documentation
- [ ] Test results documented
- [ ] Issues found documented
- [ ] Fixes verified
- [ ] CHANGELOG.md updated

### Deployment
- [ ] Changes stable for 48+ hours
- [ ] No critical errors
- [ ] User feedback positive (if applicable)
- [ ] Ready for merge to main

### Next Steps
- [ ] Merge PR #20 to main branch
- [ ] Tag release (if appropriate)
- [ ] Update issue tracking
- [ ] Plan for Issue #3 investigation (separate task)

---

## Notes Section

### Test Results Summary
*Document findings here after testing:*

**Issue #1 (Stale Cache):**
- [ ] PASS / FAIL
- Notes:

**Issue #2 (Health Check):**
- [ ] PASS / FAIL
- Notes:

**Issue #4 (Double Rate Limit):**
- [ ] PASS / FAIL
- Notes:

**Overall:**
- [ ] APPROVED FOR MERGE
- [ ] NEEDS FIXES
- [ ] ROLLBACK REQUIRED

### Issues Discovered
*List any new issues found during testing:*

1. 
2. 
3. 

### Performance Notes
*Document any performance observations:*

- Cache hit rate:
- API call frequency:
- Health check duration:
- Memory usage:

---

**Testing completed by:** _________________  
**Date:** _________________  
**Approval:** [ ] APPROVED [ ] REJECTED  
**Next action:** _________________
