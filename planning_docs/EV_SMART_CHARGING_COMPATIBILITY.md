# EV Smart Charging Compatibility

## Overview
Added compatibility attributes to the GE-Spot integration to work with the [EV Smart Charging](https://github.com/jonasbkarlsson/ev_smart_charging) integration.

## Changes Made

### File: `custom_components/ge_spot/sensor/base.py`

Added three required attributes to the `current_price` sensor for EV Smart Charging compatibility:

1. **`current_price`** - The current electricity price as a float value
2. **`raw_today`** - Array of today's prices in the required format
3. **`raw_tomorrow`** - Array of tomorrow's prices (or `None` if not available)

## Data Format

The EV Smart Charging integration expects price data in this format:

```python
{
    "current_price": 1.234,  # Current price as float
    "raw_today": [
        {
            "start": datetime(2025, 10, 1, 0, 0, tzinfo=...),  # datetime object with timezone
            "end": datetime(2025, 10, 1, 0, 15, tzinfo=...),   # datetime object with timezone
            "value": 1.234                                      # Price as float
        },
        {
            "start": datetime(2025, 10, 1, 0, 15, tzinfo=...),
            "end": datetime(2025, 10, 1, 0, 30, tzinfo=...),
            "value": 1.456
        },
        # ... more intervals
    ],
    "raw_tomorrow": [
        # Same format as raw_today, or None if not available
    ]
}
```

**Important**: The `start` and `end` keys must contain Python `datetime` objects with timezone information, NOT ISO timestamp strings. The `value` key contains the price as a float.

## Implementation Details

The implementation converts the internal `interval_prices` and `tomorrow_interval_prices` dictionaries to the array format required by EV Smart Charging:

- **Conditional activation**: Attributes are only added when EV Smart Charging integration is detected in Home Assistant
- Uses `interval_prices` from coordinator data (supports 15-minute intervals)
- Uses `tomorrow_interval_prices` for next day's prices
- Converts ISO timestamp strings to Python `datetime` objects with timezone using `dt_util.as_local()`
- Calculates `end` time as `start` + 15 minutes for each interval
- Uses keys `start`, `end`, and `value` (matching Nordpool's format)
- Prices are rounded to 4 decimal places
- Only adds these attributes to the `current_price` sensor type

### Performance Optimization

The compatibility layer only activates when the EV Smart Charging integration (`ev_smart_charging`) is detected in Home Assistant's integration data. This means:
- Zero overhead for users who don't use EV Smart Charging
- Automatic activation when EV Smart Charging is installed
- Cleaner sensor attributes for non-EV charging users

## Usage with EV Smart Charging

You can now use your GE-Spot current price sensor directly in EV Smart Charging configuration:

1. In Home Assistant, go to **Settings** → **Devices & Services** → **EV Smart Charging**
2. Click **Options** on your EV Smart Charging configuration
3. Select your GE-Spot current price sensor (e.g., `sensor.gespot_current_price_se4`)

The integration will automatically detect the required attributes and use them for optimization.

## Benefits

- **15-minute interval support**: EV Smart Charging can now optimize using 15-minute price intervals instead of just hourly
- **Native compatibility**: No need for template sensors or workarounds
- **Automatic tomorrow prices**: When available, tomorrow's prices are automatically included

## Notes

- The attributes are only added to sensors with `_sensor_type == "current_price"`
- `raw_tomorrow` is set to `None` if tomorrow's prices aren't available yet (typically before 13:00 CET)
- All timestamps are in ISO format with timezone information
- Prices maintain the same unit as your configured display unit (cents/kWh or currency/kWh)
