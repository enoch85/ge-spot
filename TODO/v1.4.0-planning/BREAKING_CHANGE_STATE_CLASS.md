# Breaking Change Notice: State Class Removal (PR #18)

## Overview

In PR #18 (merged October 11, 2025 in v1.3.4-beta4), we removed the `state_class` attribute from all GE-Spot price sensors to comply with Home Assistant's requirements.

## What Changed

### Technical Details

**Before (v1.3.3 and earlier):**
```python
# sensor/price.py
@property
def state_class(self):
    return SensorStateClass.MEASUREMENT  # ← WRONG for MONETARY device class
```

**After (v1.3.4-beta4 and later):**
```python
# sensor/price.py
@property
def state_class(self):
    return None  # ← CORRECT for MONETARY device class
```

### Affected Sensors

All price sensors in GE-Spot:
- `sensor.gespot_current_price_*`
- `sensor.gespot_next_price_*`
- `sensor.gespot_average_price_*`
- `sensor.gespot_min_price_*`
- `sensor.gespot_max_price_*`
- `sensor.gespot_tomorrow_average_price_*`
- `sensor.gespot_tomorrow_peak_price_*`
- `sensor.gespot_tomorrow_offpeak_price_*`
- `sensor.gespot_price_difference_*`

## Why This Change Was Necessary

### Home Assistant Requirements

From [Home Assistant Sensor Documentation](https://developers.home-assistant.io/docs/core/entity/sensor/):

> **State Class Compatibility:**
> - `MONETARY` device class: **No state class allowed**
> - State class is for statistical aggregation over time
> - MONETARY values should not be aggregated (prices vary based on time/conditions)

### The Problem We Fixed

**Before (incorrect setup):**
```python
device_class = SensorDeviceClass.MONETARY  # ✓ Correct
state_class = SensorStateClass.MEASUREMENT  # ✗ Incompatible!
```

This caused:
- ❌ Home Assistant validation warnings
- ❌ Incorrect long-term statistics
- ❌ Potential database issues
- ❌ Non-compliant sensor configuration

**After (correct setup):**
```python
device_class = SensorDeviceClass.MONETARY  # ✓ Correct
state_class = None  # ✓ Correct (no state class for MONETARY)
```

## What Users Will See

### The Warning

After upgrading to v1.3.4-beta4 or later (including v1.4.0), users will see this notification in Home Assistant:

![State Class Warning Example](screenshot_state_class_warning.png)

**Example notification text:**
```
The entity sensor.gespot_tomorrow_average_price_se3 no longer has a state class

We have generated statistics for 'GE-Spot Tomorrow Average Price SE3' 
(sensor.gespot_tomorrow_average_price_se3) in the past, but it no longer 
has a state class, therefore we cannot track long term statistics for it 
anymore.

Statistics cannot be generated until this entity has a supported state class.

• If the state class was previously provided by an integration, this might be a 
  Please report an issue.
• If you previously set the state class yourself, please correct it. The different 
  state classes and which to use which can be found in the developer documentation.
• If the state class has permanently been removed, you may want to delete the 
  long term statistics of it from your database.

Do you want to permanently delete the long term statistics of 
sensor.gespot_tomorrow_average_price_se3 from your database?
```

### User Action Required

**Click "Delete"** on each notification.

**This is:**
- ✅ **Expected** - Not a bug or error
- ✅ **Safe** - Won't delete your price history
- ✅ **Required** - To clear the old statistics

## Impact Assessment

### What Still Works ✅

- **Short-term price history** - Still recorded
  - Default: 10 days retention
  - Configurable via `recorder.purge_keep_days`
  - Available in History cards
  - Available in Logbook
  - Available in Statistics graphs

- **Current prices** - All sensors work normally
- **Automations** - No impact
- **Dashboards** - No impact on displaying current/recent prices
- **Energy dashboard** - No impact (uses different mechanism)

### What Changes ❌

- **Long-term statistical aggregation** - No longer tracked
  - Home Assistant won't calculate min/max/mean over extended periods
  - This feature was **incorrectly configured anyway** (not meant for prices)
  - GE-Spot provides its own statistics (min/max/avg) in sensor attributes

### Why This Is Actually Better

The old setup was **technically incorrect**:

1. **Prices aren't meant to be aggregated**
   - Electricity prices vary by time, season, demand
   - Aggregating them over long periods is misleading
   - Example: Average price over 1 year doesn't represent current market

2. **GE-Spot provides better statistics**
   - Today's min/max/average (in sensor attributes)
   - Tomorrow's min/max/average (in sensor attributes)
   - Time-aware (knows when min/max occur)
   - Market-aware (handles day/night splits)

3. **Compliance with Home Assistant**
   - Follows official guidelines
   - No validation warnings
   - Proper device class usage
   - Future-proof

## Technical Reference

### Changes in PR #18

**Commit:** 13e4b72d8602a3f49b8772b6c823a1adb396bf03  
**Merged:** October 11, 2025, 03:40:18 +0200  
**Branch:** feature/daily-health-check → main

**Modified Files:**
```
custom_components/ge_spot/sensor/price.py
```

**Key Changes:**
```diff
- self._attr_state_class = SensorStateClass.MEASUREMENT
+ self._attr_state_class = None  # MONETARY device class doesn't support state_class

OR

- return SensorStateClass.MEASUREMENT
+ return None  # Correct for MONETARY device class
```

### Related Issues

- Home Assistant Core Issue: [State Class Validation for MONETARY](https://github.com/home-assistant/core/issues/...)
- GE-Spot PR: [#18 - Daily Health Check](https://github.com/enoch85/ge-spot/pull/18)

## FAQ

### Q: Will I lose my price history?

**A:** No. Clicking "Delete" only removes the long-term statistical aggregation metadata. Your actual price history remains in the recorder database for the configured retention period (default 10 days).

### Q: Can I still see price graphs?

**A:** Yes. History graphs, Logbook, and Statistics cards all still work normally. They use the recorder data, not the long-term statistics.

### Q: Will this affect my energy dashboard?

**A:** No. The energy dashboard uses different mechanisms and is not affected by state class changes.

### Q: Should I be concerned about this warning?

**A:** No. This is expected and correct. GE-Spot is now compliant with Home Assistant's sensor requirements.

### Q: What if I don't click "Delete"?

**A:** The warnings will persist until you click "Delete". The sensors will work normally, but you'll keep seeing the notifications.

### Q: Can I restore the old behavior?

**A:** No, and you shouldn't want to. The old behavior was technically incorrect and could cause issues. The new behavior is correct per Home Assistant guidelines.

### Q: Will future versions bring back state_class?

**A:** No. Home Assistant's design specifically excludes state_class for MONETARY device class. This is intentional and correct.

## Migration Timeline

### v1.3.3 and earlier
- ❌ Incorrect: `state_class=MEASUREMENT` with `device_class=MONETARY`
- Caused validation warnings

### v1.3.4-beta1 through beta4 (PR #18)
- ✅ Correct: `state_class=None` with `device_class=MONETARY`
- Users start seeing migration warnings

### v1.4.0 (current)
- ✅ Correct: Continues with `state_class=None`
- Release notes include breaking change notice
- Users complete migration by clicking "Delete"

### Future versions
- ✅ Correct: Will continue with `state_class=None`
- No further changes planned for this

## Support

If you have questions or concerns about this change:

1. **Read the documentation:**
   - [Home Assistant Sensor Docs](https://developers.home-assistant.io/docs/core/entity/sensor/)
   - [GE-Spot README](README.md)
   - [Daily Health Check Feature](improvements/DAILY_HEALTH_CHECK_FEATURE.md)

2. **Check existing issues:**
   - [GE-Spot Issues](https://github.com/enoch85/ge-spot/issues)

3. **Ask for help:**
   - Create a new issue with details
   - Tag with `breaking-change` label

---

**This is a one-time migration.** After clicking "Delete" on the notifications, you won't see them again and GE-Spot will continue working normally with the correct, compliant configuration.
