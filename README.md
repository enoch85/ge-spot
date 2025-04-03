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
- Source-agnostic sensors that provide consistent entity IDs regardless of data source
- Tomorrow's prices available after 13:00 CET (when published)
- Automatic fallback between data sources for the same region for increased reliability
- Timestamps in ISO format for compatibility with other systems
- Robust currency and unit conversion with dynamic exchange rates
- Eight sensor types for each source:
  - Current hour price
  - Next hour price
  - Day average price
  - Peak price (highest of the day)
  - Off-peak price (lowest of the day)
  - Tomorrow average price
  - Tomorrow peak price (highest of tomorrow)
  - Tomorrow off-peak price (lowest of tomorrow)

## Price Conversion Logic

The integration implements a comprehensive price conversion system that ensures accurate pricing across all regions and currencies:

```mermaid
flowchart TD
    API[API Response] -->|Raw Data| Process
    
    subgraph Process["Process Data"]
        Extract[Extract Raw Price\ne.g. 158.67 EUR/MWh]
        Convert[Convert to Target Currency & Unit]
        Apply[Apply VAT]
        Store[Store in Standardized Format]
        
        Extract --> Convert
        Convert --> Apply
        Apply --> Store
    end
    
    Process --> Sensors[Home Assistant Sensors]
    
    subgraph Exchange["Exchange Rate Service"]
        ECB[ECB Exchange Rate API]
        Cache[Local Cache File]
        Fallback[Fallback Fixed Rates]
        
        ECB --> Cache
        Cache --> |If API fails| Fallback
    end
    
    Convert <-.->|Get rates| Exchange
    
    Config[User Configuration\nVAT, Currency, Display Unit] --> Apply
    RegionMap[Region to Currency Mapping] --> Convert
```

The conversion process follows these steps:

```mermaid
sequenceDiagram
    participant API as API Source
    participant Handler as API Handler
    participant Converter as Currency Utils
    participant Exchange as Exchange Service
    participant Cache as Exchange Rate Cache
    participant ECB as ECB API
    
    API->>Handler: Raw Price Data (e.g., 158.67 EUR/MWh)
    
    Handler->>Converter: convert_energy_price()
    
    Converter->>Exchange: Get exchange rates
    Exchange->>Cache: Check for cached rates
    
    alt Cache valid
        Cache-->>Exchange: Return cached rates
    else Cache invalid or missing
        Exchange->>ECB: Fetch current rates
        
        alt ECB API success
            ECB-->>Exchange: Current exchange rates
            Exchange->>Cache: Save to cache
        else ECB API fails
            Exchange->>Exchange: Use fallback rates
        end
        
        Exchange-->>Converter: Return rates
    end
    
    Note over Converter: Step 1: Convert Currency<br>(e.g., EUR → SEK using rate)
    Note over Converter: Step 2: Convert Energy Unit<br>(MWh → kWh, divide by 1000)
    Note over Converter: Step 3: Apply VAT<br>(if configured)
    Note over Converter: Step 4: Convert to Subunit<br>(e.g., SEK → öre, multiply by 100)
    
    Converter-->>Handler: Final Price
    Handler-->>Handler: Store price in standardized format
```

For example, converting from 69.16 EUR/MWh to öre/kWh for SE4 (with exchange rate 10.72):
1. EUR to SEK: 69.16 × 10.72 = 741.40 SEK/MWh
2. MWh to kWh: 741.40 ÷ 1000 = 0.7414 SEK/kWh
3. Apply VAT (if any): 0.7414 × (1 + VAT rate)
4. SEK to öre (if requested): 0.7414 × 100 = 74.14 öre/kWh

## Installation

### HACS Installation (Recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed
2. Add this repository as a custom repository in HACS
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
