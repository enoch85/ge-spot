# EV Smart Charging Compatibility

## Overview
**IMPLEMENTATION STATUS: NOT WORKING** ❌

This document describes the attempted compatibility implementation with the [EV Smart Charging](https://github.com/jonasbkarlsson/ev_smart_charging) integration in `custom_components/ge_spot/sensor/base.py`.

**Current Status:** The implementation exists in the code but does not work with EV Smart Charging in practice. Needs investigation and fixing.

**Important:** EV Smart Charging **already supports 15-minute intervals**. We don't need to add 15-minute support to their integration - we only need to expose our 15-minute price data in a format they can properly consume and recognize.

## Current Implementation (Not Working!)

The current implementation attempts to use the **Generic/ENTSOE format** which EV Smart Charging theoretically supports:

```python
{
    "current_price": 1.234,  # Current price as float
    "raw_today": [
        {
            "time": "2025-10-01T00:00:00+02:00",  # ISO string with timezone
            "price": 1.234
        },
        # ... 96 intervals for 15-minute data
    ],
    "raw_tomorrow": [...]  # or None
}
```

This format works because:
1. **`"time"` key** - Supported by EV Smart Charging (`start_keys = ["time", "start", "hour", ...]`)
2. **`"price"` key** - Supported by EV Smart Charging (`value_keys = ["price", "value", ...]`)
3. **ISO string format** - Automatically converted by EV Smart Charging using `datetime.fromisoformat()`
4. **No `end` key needed** - EV Smart Charging calculates it automatically based on interval length
5. **15-minute support** - EV Smart Charging already handles 15-minute intervals (detects from data)

**However, this implementation does NOT work in practice and needs to be fixed.**

## Problem to Investigate

According to EV Smart Charging's source code, the Generic/ENTSOE format with ISO strings should work, but it doesn't. EV Smart Charging already supports 15-minute intervals, so the issue is not about adding 15-minute support to their integration - it's about making our sensor properly recognized and consumed.

Possible issues:

1. **Validation failure** - EV Smart Charging may reject the sensor during validation
2. **String format issue** - ISO string might not parse correctly
3. **Missing detection** - Integration may not recognize our sensor as a valid price source
4. **Timezone issue** - Timezone handling might be incorrect
5. **15-minute interval handling** - While EV Smart Charging supports 15-minute data, there may be specific formatting expectations
6. **Unknown requirements** - There may be additional requirements not in the documentation

## Next Steps

1. Test with actual EV Smart Charging installation using 15-minute GE Spot data
2. Check EV Smart Charging logs for error messages during sensor detection
3. Compare our 15-minute interval attributes with working integrations (Nordpool, ENTSOE)
4. Verify EV Smart Charging properly recognizes and processes our 15-minute intervals
5. Test that charging optimization uses all 96 intervals per day (not just hourly)
6. May need to switch to Nordpool format with datetime objects if Generic format fails
7. Consider adding integration detection to only activate when EV Smart Charging is present

## Implementation That Needs Fixing

## How EV Smart Charging Processes Our Data

From the EV Smart Charging codebase (`helpers/coordinator.py`):

```python
class PriceFormat:
    def __init__(self, platform: str = None):
        if platform in [PLATFORM_ENTSOE, PLATFORM_GENERIC]:
            self.start = "time"
            self.value = "price"
            self.start_is_string = True  # ISO strings supported!

def convert_raw_item(item: dict[str, Any], price_format: PriceFormat) -> dict[str, Any]:
    try:
        item_new = {}
        item_new["value"] = item[price_format.value]  # Extracts "price"
        if price_format.start_is_string:
            item_new["start"] = datetime.fromisoformat(item[price_format.start])  # Converts ISO string!
        else:
            item_new["start"] = item[price_format.start]
        item_new["end"] = item_new["start"] + timedelta(minutes=15)  # Auto-calculates end
    except (KeyError, ValueError, TypeError):
        return None
```

**Detection Logic:**
```python
start_keys = ["time", "start", "hour", "start_time", "datetime"]
value_keys = ["price", "value", "price_ct_per_kwh", "electricity_price"]
```

Our attributes use `"time"` and `"price"` which are both in the supported lists!

## Changes Made

### File: `custom_components/ge_spot/sensor/base.py`

Added three attributes to the `current_price` sensor for EV Smart Charging compatibility:

1. **`current_price`** - The current electricity price as a float value ✅
2. **`raw_today`** - Array of today's prices in Generic/ENTSOE format ✅
3. **`raw_tomorrow`** - Array of tomorrow's prices (or `None` if not available) ✅

**Implementation (lines ~195-232):**
```python
# Add EV Smart Charging compatibility attributes
if self._sensor_type == "current_price":
    if self.native_value is not None:
        attrs["current_price"] = self.native_value

    # Convert interval_prices to raw_today array
    if "interval_prices" in self.coordinator.data:
        interval_prices = self.coordinator.data["interval_prices"]
        if isinstance(interval_prices, dict):
            raw_today = []
            for timestamp_str, price in sorted(interval_prices.items()):
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(timestamp_str)
                    raw_today.append({
                        "time": timestamp_str,  # ISO string
                        "price": round(price, 4)
                    })
                except (ValueError, TypeError):
                    continue
            if raw_today:
                attrs["raw_today"] = raw_today

    # Convert tomorrow_interval_prices to raw_tomorrow array
    if "tomorrow_interval_prices" in self.coordinator.data:
        tomorrow_interval_prices = self.coordinator.data["tomorrow_interval_prices"]
        if isinstance(tomorrow_interval_prices, dict) and tomorrow_interval_prices:
            raw_tomorrow = []
            for timestamp_str, price in sorted(tomorrow_interval_prices.items()):
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(timestamp_str)
                    raw_tomorrow.append({
                        "time": timestamp_str,  # ISO string
                        "price": round(price, 4)
                    })
                except (ValueError, TypeError):
                    continue
            if raw_tomorrow:
                attrs["raw_tomorrow"] = raw_tomorrow
            else:
                attrs["raw_tomorrow"] = None
        else:
            attrs["raw_tomorrow"] = None
    else:
        attrs["raw_tomorrow"] = None
```

## Implementation Details

- **Format**: Generic/ENTSOE (ISO strings with `time` + `price` keys)
- **Activation**: Always active for `current_price` sensor (no detection needed)
- **Data source**: Uses `interval_prices` and `tomorrow_interval_prices` from coordinator
- **Timezone handling**: ISO strings preserve timezone information (`2025-10-01T00:00:00+02:00`)
- **Interval support**: Designed for 15-minute intervals (96 per day) - EV Smart Charging already supports this
- **Precision**: Prices rounded to 4 decimal places
- **Tomorrow prices**: Set to `None` when unavailable (typically before 13:00 CET)

## Usage with EV Smart Charging (When Fixed)

Once fixed, users will be able to configure EV Smart Charging to use GE-Spot sensors with 15-minute optimization:

1. In Home Assistant, go to **Settings** → **Devices & Services** → **EV Smart Charging**
2. Click **Options** on your EV Smart Charging configuration
3. Select your GE-Spot current price sensor (e.g., `sensor.gespot_current_price_se4`)

EV Smart Charging will automatically detect the 15-minute intervals from the data and use them for optimization (no configuration needed on their side).

## Benefits (When Fixed)

- **15-minute interval optimization**: EV Smart Charging **already supports 15-minute intervals** - users would get optimized charging schedules based on granular GE Spot pricing
- **Native compatibility**: No need for template sensors or workarounds  
- **Automatic tomorrow prices**: When available, tomorrow's prices would be automatically included
- **Minimal overhead**: Simple ISO string conversion from internal format
- **No refactoring needed**: Can use our existing ISO timestamp strings (if Generic format works)

## Testing Checklist (For Future Fix)

- [ ] Verify EV Smart Charging detects the sensor as valid
- [ ] Check EV Smart Charging logs for errors
- [ ] Test validation with `PriceAdaptor.validate_price_entity()`
- [ ] Compare attributes with working Nordpool integration
- [ ] Verify `raw_today` format matches expectations
- [ ] Verify `raw_tomorrow` is `None` when unavailable
- [ ] Test actual charging schedule optimization
- [ ] Consider switching to Nordpool format if Generic doesn't work

## Alternative Formats (Not Used)

EV Smart Charging also supports:

### Nordpool Format (datetime objects):
```python
{
    "start": datetime(...),
    "end": datetime(...),
    "value": price
}
```

### Energi Data Service Format:
```python
{
    "hour": datetime(...),
    "price": price
}
```

**Why we use Generic format:**
- No need to convert ISO strings to datetime objects
- No major refactoring required
- Fully supported and tested by EV Smart Charging
- Works identically to ENTSOE integration

## References

- [EV Smart Charging GitHub](https://github.com/jonasbkarlsson/ev_smart_charging)
- [PriceAdaptor Source](https://github.com/jonasbkarlsson/ev_smart_charging/blob/main/custom_components/ev_smart_charging/helpers/price_adaptor.py)
- [Coordinator Conversion Logic](https://github.com/jonasbkarlsson/ev_smart_charging/blob/main/custom_components/ev_smart_charging/helpers/coordinator.py#L52-L72)
- [Generic Format Tests](https://github.com/jonasbkarlsson/ev_smart_charging/blob/main/tests/helpers/helpers.py#L220-L247)

## Notes

- Current implementation uses Generic/ENTSOE format which is fully supported
- ISO string format is converted internally by EV Smart Charging
- No need to change our internal representation
- The `end` key is calculated automatically (not needed in attributes)
- All prices maintain the same unit as configured display unit (cents/kWh or currency/kWh)

## Changes Made

### File: `custom_components/ge_spot/sensor/base.py`

**ATTEMPTED** to add three required attributes to the `current_price` sensor for EV Smart Charging compatibility:

1. **`current_price`** - The current electricity price as a float value ✅ (works)
2. **`raw_today`** - Array of today's prices ❌ (wrong format)
3. **`raw_tomorrow`** - Array of tomorrow's prices ❌ (wrong format)

**Current implementation is non-functional due to wrong data format.**
