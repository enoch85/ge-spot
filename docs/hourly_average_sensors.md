# Hourly Average Price Sensors

**Purpose:** Calculate hourly averages from 15-minute interval data for providers that bill hourly.

## Why Hourly Averages?

Many providers bill based on hourly averages despite 15-minute data availability. These sensors bridge the gap while maintaining GE-Spot's 15-minute granularity.

**Use cases:**
- Match provider billing (e.g., Belgian Luminus)
- Legacy automations expecting 24 values/day
- Simplified visualization
- Cost forecasting

## Available Sensors

| Sensor | Entity ID | State | Availability |
|--------|-----------|-------|--------------|
| **Today's Average** | `sensor.gespot_hourly_average_price_{area}` | Current hour average | When interval data exists |
| **Tomorrow's Average** | `sensor.gespot_tomorrow_hourly_average_price_{area}` | First hour tomorrow | When `tomorrow_valid = true` |

## Attributes

### Hourly Prices
```python
today_hourly_prices = [
  {"time": datetime(2025, 10, 22, 0, 0, tzinfo=...), "value": 13.45},
  {"time": datetime(2025, 10, 22, 1, 0, tzinfo=...), "value": 15.23},
  ...  # 24 entries
]
```

### Statistics
- `today_min_price` / `today_max_price` / `today_avg_price`
- `tomorrow_min_price` / `tomorrow_max_price` / `tomorrow_avg_price` (when available)

**Format:** `time` = datetime with timezone, `value` = float (4 decimals)

## Calculation

**Method:** Group 15-min intervals by hour → average all prices → store with hour key.

**Example:**
```
10:00 = 0.120, 10:15 = 0.125, 10:30 = 0.118, 10:45 = 0.122
→ Hourly average: 0.121 €/kWh
```

**Partial data:** Averages available intervals (3 intervals → avg of 3, 1 interval → uses that value, 0 → skip hour).

**DST transitions:** Spring forward skips hour, fall back includes all intervals (automatic via timezone converter).

## Usage Examples

### Cheap Hour Automation
```yaml
automation:
  - alias: "Cheap Hour Alert"
    trigger:
      platform: state
      entity_id: sensor.gespot_hourly_average_price_be
    condition:
      numeric_state:
        entity_id: sensor.gespot_hourly_average_price_be
        below: 0.10
    action:
      service: notify.mobile_app
      data:
        message: "Only {{ states('sensor.gespot_hourly_average_price_be') }} €/kWh!"
```

### Find Cheapest 3 Hours
```yaml
sensor:
  - platform: template
    sensors:
      cheapest_hours:
        value_template: >
          {% set hourly = state_attr('sensor.gespot_hourly_average_price_be', 'today_hourly_prices') %}
          {% set sorted = hourly | sort(attribute='value') %}
          {{ sorted[:3] | map(attribute='time.hour') | join(', ') }}
```

## FAQ

**Q: Why not fetch hourly prices directly?**  
A: Calculating from 15-min intervals ensures consistency and avoids duplicate data. One source, two views.

**Q: What if intervals are missing?**  
A: Averages available intervals (matches provider behavior). 0 intervals = skip hour.

**Q: Do these work with partial day data?**  
A: Yes! Calculates per-hour independently. Morning data = morning averages.

**Q: Compatible with EV Smart Charging?**  
A: Yes. Uses same `{time, value}` format as interval prices.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Sensor unavailable | Check `state_attr('sensor.gespot_current_price_{area}', 'today_interval_prices')` exists |
| Tomorrow sensor unavailable | Check `tomorrow_valid` attribute, data arrives after 13:00 |
| Missing hours | Normal for future hours, incomplete API data, or DST spring forward |
| Wrong average | Verify source intervals, check which intervals grouped per hour |

---

**No configuration needed** - sensors auto-created for your area. Respects display unit, VAT, currency settings.
