# Release Notes: GE-Spot v1.4.0

**Release Date:** October 12, 2025  
**Type:** Reliability & User Experience Release  
**Breaking Changes:** Yes (State Class Removal - see below)

---

## 🚨 BREAKING CHANGE: State Class Removed

### What Changed

As part of [PR #18](https://github.com/enoch85/ge-spot/pull/18) (merged in v1.3.4-beta4), we removed the `state_class` attribute from all price sensors to comply with Home Assistant's requirements for the `MONETARY` device class.

### What You'll See

After upgrading to v1.4.0, Home Assistant may show this notification for each price sensor:

![State Class Warning](screenshot_state_class_warning.png)

**Example message:**
```
The entity sensor.gespot_tomorrow_average_price_se3 no longer has a state class

We have generated statistics for 'GE-Spot Tomorrow Average Price SE3' 
(sensor.gespot_tomorrow_average_price_se3) in the past, but it no longer 
has a state class, therefore we cannot track long term statistics for 
it anymore.

Do you want to permanently delete the long term statistics of 
sensor.gespot_tomorrow_average_price_se3 from your database?
```

### What to Do

**Click "Delete"** for each sensor showing this warning. This is expected and safe.

**Why This Change?**
- Home Assistant's `MONETARY` device class is incompatible with `state_class` for statistical aggregation
- The previous setup caused validation warnings and potential issues with long-term statistics
- Your price history is still recorded (default: 10 days, configurable via `recorder.purge_keep_days`)
- This brings GE-Spot into compliance with [Home Assistant's sensor documentation](https://developers.home-assistant.io/docs/core/entity/sensor/)

**Impact:**
- ✅ Price history still available in dashboards
- ✅ Short-term trends still visible (configurable retention)
- ❌ Long-term statistical aggregation no longer tracked by HA

---

## ⚡ Reliability Improvements

### NEW: Grace Period After Restart (Immediate Data Recovery)

**The Problem We Solved:**

After Home Assistant restart or integration reload, sensors would show "unavailable" for up to 15 minutes due to rate limiting, even though this is a normal operation.

**The Solution:**

Implemented a **5-minute grace period** after coordinator creation that allows immediate data fetching:

```
BEFORE (without grace period):
00:00 - HA restarts
00:01 - First update: Rate limited (last fetch was 2 min ago) ❌
        Sensors show "unavailable" for 15 minutes

AFTER (with grace period):
00:00 - HA restarts
00:01 - First update: Grace period active, bypasses rate limit ✅
        Sensors show fresh data immediately
```

**Impact:**
- ✅ **Sensors show data within seconds** after HA restart
- ✅ **Better user experience** during common operations (restart/reload)
- ✅ **No error messages** during expected post-restart behavior
- ✅ **Automations see valid data** immediately, not "unavailable"
- ✅ **Configuration changes reflected instantly** (VAT, currency, etc.)

**Technical Details:**
- Grace period: 5 minutes after coordinator creation
- Only bypasses rate limiting, still respects data validity checks
- Documented in: `improvements/GRACE_PERIOD_MECHANISM.md`

---

## 🐛 Bug Fixes

### CRITICAL: Health Check Now Runs in Both Special Windows

**The Problem We Fixed:**

The health check system had a critical flaw: it only ran **once per day**, even though we have **two special windows**:
- **00:00-01:00** - For fetching today's new prices
- **13:00-15:00** - For fetching tomorrow's prices

**What This Meant:**
- If health check ran at 00:00, it **wouldn't run again** at 13:00 the same day
- Failed sources stayed disabled for **11+ hours** until the next day
- The critical 13:00-15:00 window (for tomorrow's data) couldn't recover failed sources
- Users missed tomorrow's prices from sources that had recovered

**The Solution:**

Health check now tracks **per-window** instead of **per-day**:

```
BEFORE (buggy behavior):
00:05 - Health check runs ✓
      - _last_check_date = today
13:00 - Health check skips ✗ (already ran today)
      - Failed sources NOT validated
      - Tomorrow's data unavailable
      
AFTER (fixed behavior):
00:05 - Health check runs ✓ (window 0)
      - _last_check_window = 0
13:10 - Health check runs ✓ (window 13)
      - _last_check_window = 13
      - Failed sources validated!
      - Tomorrow's data available
00:00 - Next day (window 0)
      - Compares: 13 != 0 → runs again ✓
```

**Impact:**
- ✅ Failed sources validated **twice daily** (in both special windows)
- ✅ Maximum **2-hour wait** for source recovery (was 11+ hours)
- ✅ Tomorrow's prices available from recovered sources
- ✅ Better source redundancy and reliability

**Technical Details:**
- Tracks last checked window start hour: `_last_check_window` (stores 0 or 13)
- Window comparison: `current_window_start != _last_check_window` allows both windows same day
- Reduced sleep interval to **15 minutes** (900s, was 3600s) for faster window detection
- Log messages now show which window is running
- Automatically resets for new day (window 0 != 13 comparison)

### MINOR: Removed Redundant Cache Lookup Logging

**The Problem We Fixed:**

Cache manager logged `"No specific source hit for 'None'"` on every cache retrieval when no source was specified. This was:
- Expected behavior (not an error)
- Logged **36 times per minute** per area
- Created log spam

**The Solution:**

Only log when actual fallback occurs (source was specified but not found).

**Impact:**
- ✅ Cleaner logs
- ✅ Easier debugging
- ✅ Same functionality

---

## 📊 Technical Details

### Modified Files

**Core Changes:**
- `custom_components/ge_spot/coordinator/unified_price_manager.py`
  - Added grace period mechanism (`is_in_grace_period()`)
  - Per-window health check tracking (`_last_check_window`)
  - 15-minute sleep interval for health check loop
  - Improved logging for post-restart scenarios
  - Fixed consecutive failures counter bug

- `custom_components/ge_spot/coordinator/fetch_decision.py`
  - Grace period parameter passed to rate limiter
  - Improved decision logging

- `custom_components/ge_spot/utils/rate_limiter.py`
  - Grace period bypass in rate limiting checks

- `custom_components/ge_spot/const/network.py`
  - Added `GRACE_PERIOD_MINUTES = 5` constant
  - Special hour windows: `[(0, 1), (13, 15)]`

- `custom_components/ge_spot/const/errors.py`
  - Added specific error codes and `ErrorDetails` helper class

- `custom_components/ge_spot/sensor/base.py`
  - Error codes exposed in sensor attributes

### New Features

**Grace Period Mechanism:**
- Tracks coordinator creation time (`_coordinator_created_at`)
- 5-minute window after restart/reload where rate limiting is bypassed
- Allows immediate data fetching after HA restart or config changes
- Only bypasses rate limiting, still respects data validity checks
- See: `improvements/GRACE_PERIOD_MECHANISM.md` for complete documentation

**Per-Window Health Checks:**
- Tracks last checked window start hour: `_last_check_window` (0 or 13)
- Window comparison logic allows both windows to run same day
- 15-minute sleep interval ensures windows aren't missed
- Better logging with window information

**Specific Error Types:**
- `NO_SOURCES_CONFIGURED` - Permanent configuration issue
- `ALL_SOURCES_DISABLED` - Temporary (all sources failed recently)
- `INVALID_AREA_CODE` - Invalid area configuration
- `VALIDATION_FAILED` - Data validation errors
- `INCOMPLETE_DATA` - Partial data received

### Backward Compatibility

✅ **No Breaking Changes (except state class from PR #18):**
- Grace period activates automatically on first coordinator creation
- Per-window health checks work with existing configuration
- No manual intervention required
- All existing automations continue to work

✅ **Configuration Changes:**
- VAT rate changes → Triggers new fetch during grace period
- Currency changes → Triggers new fetch during grace period
- Display unit changes → Triggers new fetch during grace period
- Area changes → Creates new coordinator with new grace period

---

## 🧪 Testing

All existing tests pass:
- ✅ **191 unit tests** (all passing after consecutive failures counter fix)
- ✅ Grace period mechanism tested (bypass rate limiting during 5-minute window)
- ✅ Per-window health check behavior verified (runs in both 0 and 13 windows)
- ✅ Error type system validated (specific error codes in sensor attributes)
- ✅ Config change behavior tested (new coordinator creation triggers grace period)

**Manual Testing:**
- ✅ Grace period activates immediately after HA restart
- ✅ Sensors show data within seconds of restart (not 15 minutes)
- ✅ Health check runs in both windows same day (00:00-01:00 and 13:00-15:00)
- ✅ Failed source recovery in second window verified
- ✅ Error codes properly exposed in sensor attributes
- ✅ Consecutive failures counter increments correctly

---

## 📝 Migration Guide

### Upgrading from v1.3.x

**Step 1: Backup (Optional but Recommended)**
```bash
# Backup your Home Assistant configuration
# (Standard HA backup process)
```

**Step 2: Upgrade**
```bash
# Via HACS:
1. Go to HACS → Integrations
2. Find "GE-Spot"
3. Click "Update"

# Or manually:
cd /config/custom_components/ge_spot
git pull
git checkout v1.4.0
```

**Step 3: Restart Home Assistant**
```bash
# Restart Home Assistant to load new version
```

**Step 4: Observe Grace Period in Action**

After restart, check your logs - you should see:
```
INFO: [SE1] Data will update within 15 minutes (rate limit protection 
      active after configuration reload)
```

Sensors will show fresh data within seconds, not minutes!

**Step 5: Handle State Class Warnings**

You'll see warnings like this for each price sensor:

```
The entity sensor.gespot_tomorrow_average_price_se3 no longer has a state class
```

**Click "Delete"** on each notification. This is expected and safe.

**Step 6: Verify**

Check logs for:
```
INFO: [SE1] Data will update within 15 minutes (rate limit protection 
      active after configuration reload)
INFO: [SE1] Daily health check starting in Xs (window: 00:00-01:00 OR 13:00-15:00)
DEBUG: Rate limiting [SE1]: ALLOWING fetch - Within grace period after 
       startup - bypassing rate limiting
```

You should see:
- ✅ Sensors showing data within seconds of restart
- ✅ Grace period logs during first 5 minutes after restart
- ✅ Health checks running in both daily windows
- ✅ Error codes in sensor attributes (Developer Tools → States)

**That's it!** The upgrade is automatic and all improvements activate immediately.

---

## 🎯 What Changed - User Experience

### Before v1.4.0
```
After HA Restart:
- Sensors: "unavailable" for up to 15 minutes ❌
- Reason: Rate limiting blocks immediate fetch
- User sees: Error messages, stale data

Health Checks:
- Frequency: Once per day
- Problem: Misses 13:00-15:00 window if ran at 00:00
- Failed Source Recovery: 11+ hours ❌

Error Messages:
- Generic: "Failed to fetch data" (not helpful)
- No error codes in attributes
```

### After v1.4.0
```
After HA Restart:
- Sensors: Fresh data within seconds ✅
- Reason: Grace period bypasses rate limiting for 5 minutes
- User sees: Immediate data recovery, INFO logs (not errors)

Health Checks:
- Frequency: Twice per day (00:00-01:00 AND 13:00-15:00)
- Tracks: Last window checked (0 or 13), not date
- Failed Source Recovery: Maximum 2 hours ✅

Error Messages:
- Specific: "All 2 API source(s) temporarily disabled..."
- Error codes: Exposed in sensor attributes for automation
- Distinguishes: Permanent vs temporary issues
```

---

## 📚 Related Documentation

- [Grace Period Mechanism](improvements/GRACE_PERIOD_MECHANISM.md) - Complete technical documentation
- [Daily Health Check Feature](improvements/DAILY_HEALTH_CHECK_FEATURE.md)
- [Implementation Plan](IMPLEMENTATION_PLAN_v1.4.0.md) - Original v1.4.0 planning
- [Home Assistant Sensor Documentation](https://developers.home-assistant.io/docs/core/entity/sensor/)
- [PR #18 - Daily Health Check](https://github.com/enoch85/ge-spot/pull/18)
- [PR #19 - Bug Fixes Issue 5-4-2](https://github.com/enoch85/ge-spot/pull/19)

---

## 🙏 Acknowledgments

Special thanks to:
- **@enoch85** for identifying the grace period need and health check issues through detailed testing
- All users who reported the state class warnings
- Home Assistant community for sensor device class documentation
- GitHub Copilot for assistance with code analysis and documentation

---

## 🐛 Known Issues

None currently identified.

If you encounter any issues, please report them at:
https://github.com/enoch85/ge-spot/issues

---

**Full Changelog:** https://github.com/enoch85/ge-spot/compare/v1.3.4...v1.4.0

---

## 📅 Next Release

**v1.5.0** (Planned Features):
- VIC1 timezone reference configuration fix
- Enhanced data validation
- Additional performance optimizations

---

**Full Changelog:** https://github.com/enoch85/ge-spot/compare/v1.3.4...v1.4.0
