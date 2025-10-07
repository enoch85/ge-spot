# User-Defined Alerts

Let users configure price alerts.

## Why

Proactive notifications.

## What to Create

`custom_components/ge_spot/alerts/manager.py`

## Alert Types

- Threshold: "Notify when price < X"
- Comparative: "Notify when 20% below average"
- Window: "Notify during cheapest 3-hour window"

## Integration

- Config flow for setup
- Home Assistant notify service
- Persistent notifications
