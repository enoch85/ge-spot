# GE-Spot: Global Electricity Spot Prices Integration for Home Assistant

> *"Hit the right spot with your energy prices"*

This custom integration allows you to fetch day-ahead electricity spot prices from various trustworthy global sources for use in automations, dashboards, and energy monitoring within Home Assistant.

## Supported Price Sources

- **Energi Data Service** - Prices for Denmark
- **Nordpool** - Prices for Nordic and Baltic countries
- **ENTSO-E** - European Network of Transmission System Operators for Electricity (requires API key)
- **EPEX SPOT** - European Power Exchange for Central Europe
- **OMIE** - Iberian Electricity Market Operator for Spain and Portugal
- **AEMO** - Australian Energy Market Operator

## Features

- Simple configuration through the Home Assistant UI
- Region-specific setup options
- Five sensor types for each source:
  - Current hour price
  - Next hour price
  - Day average price
  - Peak price (highest of the day)
  - Off-peak price (lowest of the day)
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
3. Select the desired price source (Energi Data Service, Nordpool, etc.)
4. Choose your region/area
5. Set your preferred VAT rate and update interval
6. For ENTSO-E, you'll need to provide an API key

## Usage Examples

### Current Price in a Dashboard

Add the current price to your energy dashboard:

```yaml
type: entities
entities:
  - entity: sensor.nordpool_current_price
    name: Current Electricity Price
  - entity: sensor.nordpool_next_hour_price
    name: Next Hour Price
  - entity: sensor.nordpool_day_average_price
    name: Today's Average
```

### Using Prices in Automations

Example automation to turn on a device when prices are low:

```yaml
automation:
  - alias: Turn on water heater when prices are low
    trigger:
      - platform: state
        entity_id: sensor.nordpool_current_price
    condition:
      - condition: template
        value_template: "{{ states('sensor.nordpool_current_price')|float < states('sensor.nordpool_day_average_price')|float * 0.8 }}"
    action:
      - service: switch.turn_on
        entity_id: switch.water_heater
```

## Troubleshooting

If you experience issues:

- Check the Home Assistant logs for error messages related to `ge_spot`
- Verify that your selected region/area is correct
- For ENTSO-E, confirm your API key is entered correctly
- Try increasing the update interval if you're experiencing frequent timeouts

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This integration is licensed under the MIT License.
