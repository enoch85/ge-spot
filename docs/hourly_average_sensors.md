# Hourly Average Price Sensors

This document describes the hourly average price sensors available in GE-Spot. These sensors provide electricity prices averaged over each hour, calculated from the underlying 15-minute interval data.

## Overview

While GE-Spot fetches 15-minute interval prices for maximum accuracy, many electricity providers bill based on hourly averages. The hourly average sensors bridge this gap by automatically calculating and exposing hourly price averages.

## Use Cases

Hourly average sensors are useful for:

- **Provider Bill Matching** - Many providers bill based on hourly averages, even when 15-minute data is available
- **Legacy Integrations** - Existing automations and scripts that expect 24 hourly values instead of 96 intervals
- **Simplified Visualization** - Easier to display and understand 24 hourly values vs 96 quarter-hour values
- **Cost Forecasting** - Planning energy usage around predicted hourly costs

### Real-World Example: Belgium

Belgium enabled 15-minute pricing on October 1, 2025, but providers like Luminus continue to bill based on hourly averages calculated from the four 15-minute intervals. This transitional period requires both granular and aggregated data.

## Available Sensors

### Today's Hourly Average Price

**Entity ID**: `sensor.gespot_hourly_average_price_{area}`

Shows the average electricity price for the current hour, updated every 15 minutes as new interval data becomes available.

**State**: Current hour's average price (e.g., if it's 14:30, shows average of 14:00-14:59)  
**Unit**: Same as your configured display unit (EUR/kWh, cents/kWh, etc.)  
**Availability**: Available whenever interval price data exists

### Tomorrow's Hourly Average Price

**Entity ID**: `sensor.gespot_tomorrow_hourly_average_price_{area}`

Shows hourly average prices for tomorrow, typically available after 13:00 (varies by market).

**State**: First hour of tomorrow's average price (00:00-00:59)  
**Unit**: Same as your configured display unit  
**Availability**: Only available when tomorrow's data is valid (`tomorrow_valid = true`)

## Sensor Attributes

Both hourly average sensors provide comprehensive attributes with hourly aggregated data instead of 15-minute interval prices:

### Today's Hourly Prices

**Attribute**: `today_hourly_prices`

```python
[
  {"time": datetime(2025, 10, 22, 0, 0, tzinfo=...), "value": 13.45},
  {"time": datetime(2025, 10, 22, 1, 0, tzinfo=...), "value": 15.23},
  {"time": datetime(2025, 10, 22, 2, 0, tzinfo=...), "value": 12.87},
  ...
  {"time": datetime(2025, 10, 22, 23, 0, tzinfo=...), "value": 18.92}
]
```

### Tomorrow's Hourly Prices

**Attribute**: `tomorrow_hourly_prices`

```python
[
  {"time": datetime(2025, 10, 23, 0, 0, tzinfo=...), "value": 14.12},
  {"time": datetime(2025, 10, 23, 1, 0, tzinfo=...), "value": 16.05},
  ...
]
```

### Statistics Attributes

Both sensors include convenient statistics calculated from hourly averages:

- **`today_min_price`**: Lowest hourly average price today
- **`today_max_price`**: Highest hourly average price today
- **`today_avg_price`**: Average of all hourly prices today
- **`tomorrow_min_price`**: Lowest hourly average price tomorrow (when available)
- **`tomorrow_max_price`**: Highest hourly average price tomorrow (when available)
- **`tomorrow_avg_price`**: Average of all hourly prices tomorrow (when available)

**Format**:
- `time`: Python `datetime` object with timezone information
- `value`: Floating-point price rounded to 4 decimal places
- Statistics: Rounded to 5 decimal places for accuracy

### Differences from Standard Sensors

Unlike the standard price sensors which include `today_interval_prices` and `tomorrow_interval_prices` (96 entries per day), the hourly average sensors provide:

- **`today_hourly_prices`** and **`tomorrow_hourly_prices`** (24 entries per day)
- Statistics calculated from hourly averages (not 15-minute intervals)
- No 15-minute interval data in attributes (simplified for hourly use cases)

**Compatibility**:
- Home Assistant templates
- EV Smart Charging integration (expects datetime objects)
- Custom automations
- Energy dashboard
- Nordpool-compatible automations

## How It Works

### Calculation Method

Hourly averages are calculated by:

1. Grouping all 15-minute intervals by hour (e.g., 14:00, 14:15, 14:30, 14:45 → hour 14)
2. Averaging all interval prices within each hour
3. Storing the result with the hour key (e.g., "14:00")

**Example**:
```
Quarter-hour prices:
  10:00 = 0.120 €/kWh
  10:15 = 0.125 €/kWh
  10:30 = 0.118 €/kWh
  10:45 = 0.122 €/kWh

Hourly average:
  10:00 = (0.120 + 0.125 + 0.118 + 0.122) / 4 = 0.121 €/kWh
```

### Partial Data Handling

The sensors gracefully handle incomplete data:

- **Missing 1 interval**: Averages the 3 available intervals
- **Missing 2 intervals**: Averages the 2 available intervals  
- **Missing 3 intervals**: Uses the single available interval
- **Missing all intervals**: Skips that hour (no average calculated)

This approach matches how providers calculate hourly rates when interval data is incomplete.

### DST Transitions

The sensors handle Daylight Saving Time transitions:

- **Spring Forward**: The skipped hour (typically 02:00) won't appear in hourly averages
- **Fall Back**: The repeated hour may have more than 4 intervals; all are averaged together

DST handling is performed by the underlying timezone converter before hourly averaging.

## Configuration

No additional configuration is required. The hourly average sensors are automatically created for your configured area when you restart Home Assistant.

**Example entity IDs**:
- Belgium: `sensor.gespot_hourly_average_price_be`
- Sweden SE3: `sensor.gespot_hourly_average_price_se3`
- Netherlands: `sensor.gespot_hourly_average_price_nl`

The sensors respect all your existing settings:
- Display unit (EUR/kWh or cents/kWh)
- VAT inclusion
- Currency conversion
- Precision settings

## Usage Examples

### Display Current Hourly Average

Show the current hour's average price on your dashboard:

```yaml
type: entity
entity: sensor.gespot_hourly_average_price_be
name: Current Hour Price
```

### Automation: Cheap Hour Notification

Get notified when electricity enters a cheap hour:

```yaml
automation:
  - alias: "Cheap Hour Alert"
    trigger:
      - platform: state
        entity_id: sensor.gespot_hourly_average_price_be
    condition:
      - condition: numeric_state
        entity_id: sensor.gespot_hourly_average_price_be
        below: 0.10
    action:
      - service: notify.mobile_app
        data:
          title: "⚡ Cheap Electricity"
          message: >
            Only {{ states('sensor.gespot_hourly_average_price_be') }} €/kWh 
            for the next hour!
```

### Template: Find Cheapest Hours Today

Create a sensor that finds the 3 cheapest hours:

```yaml
sensor:
  - platform: template
    sensors:
      cheapest_hours_today:
        friendly_name: "Cheapest 3 Hours Today"
        value_template: >
          {% set hourly = state_attr('sensor.gespot_hourly_average_price_be', 'hourly_prices') %}
          {% set sorted = hourly | sort(attribute='value') %}
          {% for hour in sorted[:3] %}
            {{ hour.time.hour }}:00 ({{ hour.value | round(3) }} €/kWh)
          {% endfor %}
```

### Template: Today's Price Range

Calculate the price range for today:

```yaml
sensor:
  - platform: template
    sensors:
      hourly_price_range:
        friendly_name: "Today's Price Range"
        value_template: >
          {% set hourly = state_attr('sensor.gespot_hourly_average_price_be', 'hourly_prices') %}
          {% set prices = hourly | map(attribute='value') | list %}
          {{ (prices | max - prices | min) | round(3) }} €/kWh
```

### Lovelace Card: Hourly Price List

Display all hourly prices in a markdown card:

```yaml
type: markdown
content: >
  ## Hourly Prices Today

  {% set hourly = state_attr('sensor.gespot_hourly_average_price_be', 'hourly_prices') %}
  {% for hour in hourly %}
  **{{ hour.time.hour }}:00** - {{ hour.value | round(3) }} €/kWh
  {% endfor %}
```

### Advanced: Schedule Device Based on Price

Run a device during the cheapest consecutive 3-hour block:

```yaml
automation:
  - alias: "Run Dishwasher During Cheap Hours"
    trigger:
      - platform: time_pattern
        hours: "*"
        minutes: 0
    condition:
      - condition: template
        value_template: >
          {% set hourly = state_attr('sensor.gespot_hourly_average_price_be', 'hourly_prices') %}
          {% set now_hour = now().hour %}
          {% set current_avg = hourly[now_hour].value %}
          {% set next_avg = hourly[now_hour + 1].value if now_hour < 23 else 999 %}
          {% set next2_avg = hourly[now_hour + 2].value if now_hour < 22 else 999 %}
          {% set block_avg = (current_avg + next_avg + next2_avg) / 3 %}
          {{ block_avg < 0.12 }}
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.dishwasher
```

## Frequently Asked Questions

### Why not fetch hourly prices directly from the API?

Most European electricity markets now provide 15-minute interval data. Fetching hourly data separately would:
- Duplicate data storage
- Risk inconsistencies between hourly and interval prices
- Miss the opportunity to use already-validated, currency-converted data

By calculating from intervals, you get both granular and aggregated views from a single source.

### What happens if an interval is missing?

The sensor averages whatever intervals are available for that hour. For example:
- 4 intervals present → average of 4
- 3 intervals present → average of 3
- 1 interval present → uses that single value
- 0 intervals present → hour is skipped

This matches how electricity providers calculate hourly rates when data is incomplete.

### Do hourly sensors work with partial day data?

Yes! Unlike the statistics sensors (which require 80% of the day's data), hourly average sensors calculate per-hour independently. If you only have morning data, you'll get hourly averages for the morning hours.

### How accurate are the hourly averages?

Hourly averages maintain full floating-point precision during calculation. The final values are rounded to 4 decimal places for display, which is more than sufficient for billing accuracy (typically 2-3 decimals).

### Can I use these with EV Smart Charging?

Yes! The `hourly_prices` attribute uses the same format as the standard interval prices (list of dicts with `time` and `value`), making it compatible with integrations expecting this format.

### What about DST transitions?

DST handling is automatic:
- **Spring forward**: The skipped hour won't appear in hourly data
- **Fall back**: The repeated hour includes all available intervals in its average

The underlying timezone converter handles all DST complexity before hourly calculation.

## Performance & Reliability

### Calculation Performance

- **Speed**: O(n) complexity where n ≈ 96 intervals per day (< 1ms)
- **Memory**: Minimal overhead - just groups existing data
- **Database**: Hourly attributes are 75% smaller than interval attributes (24 vs 96 entries)

### Update Frequency

Hourly average sensors update whenever the coordinator fetches new data:
- Typically every 15 minutes
- State changes when transitioning to a new hour
- Attributes update as new intervals arrive

### Error Handling

The sensors are designed to be resilient:
- Invalid interval keys are logged and skipped
- Missing data doesn't prevent calculation of available hours
- Malformed data is caught and handled gracefully
- Partial data is preferred over no data

## Troubleshooting

### Sensor shows "unavailable"

**For today's sensor:**
- Check that interval price data exists: `state_attr('sensor.gespot_current_price_be', 'today_interval_prices')`
- Verify the coordinator is updating successfully

**For tomorrow's sensor:**
- Check `tomorrow_valid` attribute on any GE-Spot sensor
- Tomorrow data typically arrives after 13:00 (varies by market)
- Not all markets provide next-day data

### Hourly average seems wrong

1. Check the source interval prices:
   ```yaml
   {{ state_attr('sensor.gespot_current_price_be', 'today_interval_prices') }}
   ```

2. Verify which intervals are included in the hour:
   ```yaml
   {% set hourly = state_attr('sensor.gespot_hourly_average_price_be', 'hourly_prices') %}
   {{ hourly[14] }}  {# Hour 14 (2:00 PM) #}
   ```

3. Calculate manually to confirm:
   ```yaml
   {% set intervals = state_attr('sensor.gespot_current_price_be', 'today_interval_prices') %}
   {% set h14 = [intervals['14:00'], intervals['14:15'], intervals['14:30'], intervals['14:45']] %}
   {{ (h14 | sum) / (h14 | length) }}
   ```

### Some hours are missing

This is normal and can happen when:
- The day is just starting (future hours don't exist yet)
- API data is incomplete (occasional interval failures)
- DST spring forward (hour 2:00-2:59 is skipped)

Hours with at least one interval will appear in the results.

## Technical Details

### Implementation

The hourly average sensors are implemented in:
- `custom_components/ge_spot/sensor/price.py` - `HourlyAverageSensor` class
- `custom_components/ge_spot/sensor/electricity.py` - Sensor registration

### Testing

Comprehensive test suite with 15 tests covering:
- Basic hourly averaging (complete and partial data)
- Edge cases (midnight, DST, missing data)
- Error handling (invalid keys, empty data)
- Precision maintenance

All tests pass on Python 3.12+ with Home Assistant 2025.x.

## Related Documentation

- [Main README](../README.md) - Integration overview
- [Nordpool Implementation](https://github.com/custom-components/nordpool/issues/496) - Similar approach
- [Issue #26](https://github.com/enoch85/ge-spot/issues/26) - Original feature request

## Support

If you encounter issues with hourly average sensors:

1. Check this documentation for troubleshooting steps
2. Verify your interval prices are working correctly
3. Open an issue on [GitHub](https://github.com/enoch85/ge-spot/issues) with:
   - Debug logs showing interval data
   - Expected vs actual hourly averages
   - Your configuration (area, display unit, etc.)
