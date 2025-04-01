# GE-Spot: Global Electricity Spot Prices Integration for Home Assistant

> *"Hit the right spot with your energy prices"*

This custom integration allows you to fetch day-ahead electricity spot prices from various trustworthy global sources for use in automations, dashboards, and energy monitoring within Home Assistant.

## Supported Price Sources

- **Nordpool** (🔥 Recommended) - Prices for Nordic and Baltic countries
- **Energi Data Service** - Prices for Denmark
- **ENTSO-E** - European Network of Transmission System Operators for Electricity (requires API key)
- **EPEX SPOT** - European Power Exchange for Central Europe
- **OMIE** - Iberian Electricity Market Operator for Spain and Portugal
- **AEMO** - Australian Energy Market Operator

## Features

- Simple configuration through the Home Assistant UI
- Region-specific setup options
- **NEW:** Source-agnostic sensors that provide consistent entity IDs regardless of data source
- **NEW:** Tomorrow's prices available after 13:00 CET (when published)
- **NEW:** Automatic fallback between data sources for the same region for increased reliability
- **NEW:** Timestamps in ISO format for compatibility with other systems
- Eight sensor types for each source:
  - Current hour price
  - Next hour price
  - Day average price
  - Peak price (highest of the day)
  - Off-peak price (lowest of the day)
  - Tomorrow average price
  - Tomorrow peak price (highest of tomorrow)
  - Tomorrow off-peak price (lowest of tomorrow)
- All hourly prices included as attributes
- VAT calculation
- Configurable update interval
- Robust error handling with caching for reliability

## Installation

### HACS Installation (Recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed
2. Add this repository as a custom repository in HACS:
   - Open HACS in Home Assistant
   - Go to "Integrations"
   - Click the three dots in the top-right corner
   - Select "Custom repositories"
   - Add the URL of this repository
   - Select "Integration" as the category
3. Click "Add"
4. Search for "GE-Spot: Global Electricity Spot Prices"
5. Click Install
6. Restart Home Assistant

### Manual Installation

1. Copy the `ge_spot` directory from this repository to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Setup & Configuration

After installation:

1. Go to Configuration → Integrations
2. Click "Add Integration" and search for "GE-Spot: Global Electricity Spot Prices"
3. Select the desired price source (Nordpool recommended)
4. Choose your region/area
5. Set your preferred VAT rate and update interval
6. For ENTSO-E, you'll need to provide an API key
7. Enable "Fallback" to automatically use alternative data sources if the primary source fails

## Usage Examples

### Current Price in a Dashboard

Add the current price to your energy dashboard:

```yaml
type: entities
entities:
  - entity: sensor.electricity_current
    name: Current Electricity Price
  - entity: sensor.electricity_next_hour
    name: Next Hour Price
  - entity: sensor.electricity_day_average
    name: Today's Average
  - entity: sensor.electricity_tomorrow_average
    name: Tomorrow's Average
```

### Using Prices in Automations

Example automation to turn on a device when prices are low:

```yaml
automation:
  - alias: Turn on water heater when prices are low
    trigger:
      - platform: state
        entity_id: sensor.electricity_current
    condition:
      - condition: template
        value_template: "{{ states('sensor.electricity_current')|float < states('sensor.electricity_day_average')|float * 0.8 }}"
    action:
      - service: switch.turn_on
        entity_id: switch.water_heater
```

## Source-Specific vs Generic Sensors

This integration provides two sets of sensors:

1. **Source-specific sensors** - include the source name (e.g., `sensor.nordpool_current_price`)
2. **Generic sensors** - source-agnostic with consistent names (e.g., `sensor.electricity_current`)

Using the generic sensors in your automations ensures they'll continue to work if you change your data source.

## Price Availability

Prices are typically available according to the following schedule:

- **Today's prices**: Available 24/7
- **Tomorrow's prices**: Available after 13:00 CET when published by exchanges
  - Nordpool publishes prices around 12:45-13:00 CET
  - Other exchanges may have different schedules

## Fallback System

When enabled, the fallback system allows the integration to automatically switch to an alternative data source if the primary source fails. This increases reliability by attempting to fetch data from compatible sources for your region.

For example, if you configure Nordpool for SE4 (Malmö) and the service is temporarily unavailable, the integration will automatically try ENTSO-E's data for the same region.

## Troubleshooting

If you experience issues:

- Check the Home Assistant logs for error messages related to `ge_spot`
- Verify that your selected region/area is correct
- For ENTSO-E, confirm your API key is entered correctly
- Try increasing the update interval if you're experiencing frequent timeouts
- Enable the fallback option for increased reliability
- Check sensor attributes to see if data is coming from a fallback source or cache

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This integration is licensed under the MIT License.
