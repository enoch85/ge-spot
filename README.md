# GE-Spot: Global Electricity Spot Prices Integration for Home Assistant

![Version](https://img.shields.io/badge/version-1.5.2-blue.svg) ![Status](https://img.shields.io/badge/status-stable-green.svg)

> *"Hit the right spot with your energy prices"*

<img src="https://github.com/user-attachments/assets/7d765596-50b2-4d2a-926c-209da7120179" width="200" title="GE-Spot Logo" alt="GE-Spot Logo"/>

Home Assistant custom integration providing **electricity spot prices** from global markets with intelligent interval handling (15-minute, hourly, 5-minute) and automatic source fallback.

## Table of Contents

- [Installation](#installation)
- [Supported Price Sources & Regions](#supported-price-sources--regions)
- [Features](#features)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Usage Examples](#usage-examples)
- [Troubleshooting](#troubleshooting)
- [For Developers](#for-developers)
- [Contributing](#contributing)
- [Technical Architecture (Advanced)](#technical-architecture-advanced)

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

## Supported Price Sources & Regions

The integration supports multiple price data sources with automatic fallback capabilities:

- **Nordpool** - Nordic and Baltic countries
- **ENTSO-E** - European Network of Transmission System Operators (requires API key)
- **Energy-Charts** - European spot prices (Germany, France, Netherlands, Belgium, Austria, and more)
- **Energi Data Service** - Denmark
- **Stromligning** - Denmark  
- **OMIE** - Spain and Portugal
- **AEMO** - Australian Energy Market Operator
- **ComEd** - Chicago area real-time pricing
- **Amber** - Australian residential pricing

### Region Support Matrix

The table below shows which price sources support specific regions:

| Region | Description | Nordpool | ENTSO-E | Energy-Charts | Energi Data | Stromligning | OMIE | AEMO | ComEd | Amber |
|--------|-------------|:--------:|:-------:|:-------------:|:-----------:|:------------:|:----:|:----:|:-----:|:-----:|
| AT     | Austria | ✓ | ✓ | ✓ | | | | | | |
| BE     | Belgium | ✓ | ✓ | ✓ | | | | | | |
| BG     | Bulgaria | | ✓ | ✓ | | | | | | |
| CH     | Switzerland | | ✓ | ✓ | | | | | | |
| ComEd  | Chicago Area | | | | | | | | ✓ | |
| CZ     | Czech Republic | | ✓ | ✓ | | | | | | |
| DE     | Germany | ✓ | ✓ | ✓ | | | | | | |
| DE-LU  | Germany-Luxembourg | ✓ | ✓ | ✓ | | | | | | |
| DK1-2  | Denmark | ✓ | ✓ | ✓ | ✓ | ✓ | | | | |
| EE     | Estonia | ✓ | ✓ | ✓ | | | | | | |
| ES     | Spain | | ✓ | ✓ | | | ✓ | | | |
| FI     | Finland | ✓ | ✓ | ✓ | | | | | | |
| FR     | France | ✓ | ✓ | ✓ | | | | | | |
| GR     | Greece | | ✓ | ✓ | | | | | | |
| HR     | Croatia | | ✓ | ✓ | | | | | | |
| HU     | Hungary | | ✓ | ✓ | | | | | | |
| IT-Centre-North | Italy Centre-North | | | ✓ | | | | | | |
| IT-Centre-South | Italy Centre-South | | | ✓ | | | | | | |
| IT-North | Italy North | | ✓ | ✓ | | | | | | |
| IT-Sardinia | Italy Sardinia | | | ✓ | | | | | | |
| IT-Sicily | Italy Sicily | | | ✓ | | | | | | |
| IT-South | Italy South | | | ✓ | | | | | | |
| LT     | Lithuania | ✓ | ✓ | ✓ | | | | | | |
| LV     | Latvia | ✓ | | ✓ | | | | | | |
| ME     | Montenegro | | | ✓ | | | | | | |
| NL     | Netherlands | ✓ | ✓ | ✓ | | | | | | |
| NO1-5  | Norway | ✓ | ✓ | ✓ | | | | | | |
| NSW1   | Australia NSW | | | | | | | ✓ | | ✓ |
| PL     | Poland | ✓ | ✓ | ✓ | | | | | | |
| PT     | Portugal | | ✓ | ✓ | | | ✓ | | | |
| QLD1   | Australia Queensland | | | | | | | ✓ | | ✓ |
| RO     | Romania | | ✓ | ✓ | | | | | | |
| RS     | Serbia | | ✓ | ✓ | | | | | | |
| SA1    | Australia South | | | | | | | ✓ | | ✓ |
| SE1-4  | Sweden | ✓ | ✓ | ✓ | | | | | | |
| SI     | Slovenia | | ✓ | ✓ | | | | | | |
| SK     | Slovakia | | ✓ | ✓ | | | | | | |
| TAS1   | Australia Tasmania | | | | | | | ✓ | | ✓ |
| VIC1   | Australia Victoria | | | | | | | ✓ | | ✓ |

For complete area mappings, see [`const/areas.py`](custom_components/ge_spot/const/areas.py).

## Features

- **Flexible intervals** - Handles 15-min, hourly, and 5-min data from different markets
- **Unified output** - Standardizes to 15-minute intervals (96 data points per day)
- **Multi-source fallback** - Automatic switching between data sources
- **Global coverage** - Europe, Australia, and North America
- **Currency conversion** - Live ECB exchange rates
- **Timezone handling** - Consistent display regardless of API source
- **Tomorrow's prices** - Available after daily publication (typically 13:00 CET)
- **EV Smart Charging integration** - Native support for [EV Smart Charging](https://github.com/jonasbkarlsson/ev_smart_charging) via `today_interval_prices` and `tomorrow_interval_prices` attributes

### Sensors Created (per region)

- **Current Price** - Current 15-minute interval price
- **Next Interval Price** - Upcoming interval price  
- **Average Price** - Today's average
- **Peak/Off-Peak Price** - Today's high/low
- **Price Difference** - Current vs average (absolute)
- **Price Percentage** - Current vs average (relative)
- **Tomorrow prices** - Average, peak, and off-peak forecasts

## Configuration

After installation:

1. Go to Configuration → Integrations
2. Click "Add Integration" and search for "GE-Spot: Global Electricity Spot Prices"
3. Select your region/area from the dropdown
4. Configure settings:

### Basic Settings

- **Region/Area**: Select your electricity price area (e.g. SE4, DK1)
- **Source Priority**: Order of data sources to try (first = highest priority)
- **VAT Rate**: Set your applicable VAT percentage (e.g. 25 for 25%)

### Advanced Settings

- **Display Format**: Choose between decimal (e.g. 0.15 EUR/kWh) or subunit (e.g. 15 cents/kWh)
- **API Keys**: For ENTSO-E, you'll need to [register for an API key](https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html)
- **API Key Reuse**: The integration will reuse API keys across different regions using the same source

### Reliability Features

- **Rate limiting** - Minimum 15-minute intervals 
- **Automatic retries** - Exponential backoff for failed requests (2s → 6s → 18s)
- **Data caching** - Persistent storage with TTL
- **Source fallback** - Try all sources in priority order
- **Daily health check** - All configured sources validated once per day during special windows
- **Source health monitoring** - Track which sources are working vs failed, with retry schedules

## Architecture

**Data Flow:** API Client → Parser → Timezone Conversion → Currency Conversion → Cache → Sensors

**Three-Layer System:**
- **API Layer** - Source-specific clients (Nordpool, ENTSO-E, AEMO, etc.)
- **Coordinator Layer** - Unified manager with fallback and caching  
- **Sensor Layer** - Home Assistant entities with consistent IDs

### Timezone & Interval Handling

- **Source timezone detection** - Each API has known timezone behavior
- **DST transitions** - Handles 92-100 intervals on transition days  
- **15-minute alignment** - All data normalized to :00, :15, :30, :45 boundaries
- **Home Assistant integration** - Displays in your configured timezone

### Price Processing

**Conversion Pipeline:** Raw API Data → Currency Conversion → Unit Conversion → VAT Application → Display Formatting

**Currency handling:**
- Live ECB exchange rates (24h cache)
- Automatic currency detection by region
- Display in main units (EUR/kWh) or subunits (cents/kWh)

### Data Source Differences

Different sources include different price components:

| Source | Price Components |
|--------|------------------|
| Nordpool/ENTSO-E/OMIE | Raw spot price |
| Stromligning | Spot + grid fees + taxes (Denmark) |
| AEMO | Pre-dispatch trading prices (30-min intervals) |
| ComEd | Real-time market pricing (5-min dispatch) |
| Amber | Spot + network + carbon costs |

### Interval Resolution

GE-Spot intelligently handles different native resolutions from APIs:

| Source | Native Data | GE-Spot Processing |
|--------|-------------|-------------------|
| ENTSO-E | 15/30/60 min | Uses native 15-min when available, expands others |
| Nordpool | 15/60 min | Uses native 15-min, expands hourly to 15-min |
| Energy-Charts | 15 min | Uses native 15-min data (96 intervals/day) |
| OMIE/Stromligning | 60 min | Expands hourly to 15-min (duplicates across 4 intervals) |
| AEMO | 30 min trading | Expands to 15-min (duplicates across 2 intervals) |
| ComEd | 5 min dispatch | Aggregates to 15-min (averages 3 values per interval) |
| Amber | 30 min | Expands to 15-min (duplicates across 2 intervals) |

**Strategy**: All sources output 96 intervals per day (15-minute granularity) for consistent automation timing.

## Usage Examples

### Basic Dashboard Card

```yaml
type: entities
entities:
  - entity: sensor.gespot_current_price_se4
    name: Current Electricity Price (15-min interval)
  - entity: sensor.gespot_next_interval_price_se4
    name: Next Interval Price
  - entity: sensor.gespot_day_average_price_se4
    name: Today's Average
  - entity: sensor.gespot_tomorrow_average_price_se4
    name: Tomorrow's Average
```

### Price Graph Card

<img width="403" height="286" alt="image" src="https://github.com/user-attachments/assets/4b8e23ee-6efd-4502-9091-bfa1f36cd6f9" />

```yaml
type: custom:apexcharts-card
now:
  show: true
  label: ""
graph_span: 2d
span:
  start: day
apex_config:
  chart:
    height: 300px
  legend:
    show: false
  xaxis:
    labels:
      format: HH:mm
  grid:
    borderColor: "#e0e0e0"
    strokeDashArray: 3
  tooltip:
    x:
      format: HH:mm
  annotations:
    yaxis:
      - "y": 0
        yAxisIndex: 0
        strokeDashArray: 0
        borderColor: rgba(128, 128, 128, 0.8)
        borderWidth: 2
        opacity: 1
yaxis:
  - id: watts
    decimals: 0
  - id: price
    decimals: 0
    opposite: true
experimental:
  color_threshold: true
series:
  - entity: sensor.gespot_current_price_se4
    name: Price (öre)
    type: area
    curve: stepline
    yaxis_id: price
    extend_to: now
    stroke_width: 0
    opacity: 0.7
    data_generator: |
      return [
        ...(entity.attributes.today_interval_prices || []).map(item => [new Date(item.time), item.value]),
        ...(entity.attributes.tomorrow_interval_prices || []).map(item => [new Date(item.time), item.value])
      ];
    color_threshold:
      - value: -50
        color: cyan
      - value: 0
        color: green
      - value: 40
        color: orange
      - value: 100
        color: red
      - value: 200
        color: magenta
      - value: 500
        color: black
  - entity: sensor.YOUR_ENERGY_METER
    name: Watts
    type: line
    curve: smooth
    yaxis_id: watts
    color: "#FF0000"
    stroke_width: 2
    opacity: 0.5
    extend_to: false
    group_by:
      func: avg
      duration: 5min
update_interval: 300s
```

### Sensor Attributes

The price sensors expose interval prices through attributes in a standardized format compatible with various integrations:

**Attribute Format:**
```json
{
  "today_interval_prices": [
    {"time": "2025-10-14T00:00:00+02:00", "value": 0.0856},
    {"time": "2025-10-14T00:15:00+02:00", "value": 0.0842},
    ...
  ],
  "tomorrow_interval_prices": [
    {"time": "2025-10-15T00:00:00+02:00", "value": 0.0891},
    ...
  ]
}
```

**Key Points:**
- Each price entry contains a `time` (ISO 8601 datetime string) and `value` (float)
- Times are in your Home Assistant's configured timezone
- List contains 96 entries for a normal day (15-minute intervals)
- During DST transitions: 92 entries (spring) or 100 entries (fall)
- Compatible with EV Smart Charging, ApexCharts, and custom automations

**Using in Templates:**
```yaml
# Get price at 14:00
{{ state_attr('sensor.gespot_current_price_se3', 'today_interval_prices') 
   | selectattr('time', 'search', 'T14:00') 
   | map(attribute='value') 
   | first }}

# Get all prices above 0.10
{{ state_attr('sensor.gespot_current_price_se3', 'today_interval_prices') 
   | map(attribute='value') 
   | select('>', 0.10) 
   | list }}

# Count hours with negative prices
{{ state_attr('sensor.gespot_current_price_se3', 'today_interval_prices') 
   | map(attribute='value') 
   | select('<', 0) 
   | list 
   | length }}
```

### Price-Based Automation

```yaml
automation:
  - alias: Turn on water heater when prices are low
    trigger:
      - platform: state
        entity_id: sensor.gespot_current_price_se4
    condition:
      - condition: template
        value_template: "{{ states('sensor.gespot_current_price_se4')|float < states('sensor.gespot_day_average_price_se4')|float * 0.8 }}"
    action:
      - service: switch.turn_on
        entity_id: switch.water_heater
```

### Energy Dashboard Integration

To integrate GE-Spot with the Energy Dashboard, you can create template sensors:

```yaml
template:
  - sensor:
      - name: "Energy Cost Sensor"
        unit_of_measurement: "SEK/kWh"
        state: "{{ states('sensor.gespot_current_price_se4') }}"
```

Then set this sensor as your energy cost sensor in the Energy Dashboard settings.

## Troubleshooting

**Common Issues:**
- **No data** - Check area is supported by selected source
- **API key errors** - Verify ENTSO-E API key if using that source  
- **Missing tomorrow prices** - Available after 13:00 CET daily
- **96 data points** - Correct! 15-minute intervals = 96 per day

**Source Health Monitoring:**

Check sensor attributes for source health information:

```yaml
sensor.gespot_current_price_se4:
  attributes:
    source_info:
      active_source: "nordpool"           # Currently used source
      validated_sources:                   # Sources that are working
        - "nordpool"
        - "entsoe"
      failed_sources:                      # Sources that failed (if any)
        - source: "energy_charts"
          failed_at: "2025-10-10T17:36:42+02:00"
          retry_at: "2025-10-11T13:00:00+02:00"
```

- **validated_sources**: List of sources that have been tested and are working
- **failed_sources**: List of sources that failed, with timestamps and retry schedule
- **active_source**: The source currently providing data

**Diagnostics:**
- Check sensor attributes: `data_source`, `active_source`, `using_cached_data`
- Review Home Assistant logs for `ge_spot` errors
- Configure multiple sources for better reliability

## For Developers

### Project Structure

```
custom_components/ge_spot/
├── __init__.py           # Integration setup and coordinator registration
├── config_flow.py        # Configuration flow handler
├── manifest.json         # Integration manifest and dependencies
├── api/                  # API clients for different price sources
│   ├── __init__.py       # API client factory and source mapping
│   ├── base/             # Base classes and shared functionality
│   │   ├── api_client.py       # HTTP client wrapper with retry logic
│   │   ├── base_price_api.py   # Abstract base for all price APIs
│   │   └── error_handler.py    # Error handling and retry mechanisms
│   ├── parsers/          # Data parsers for each API source
│   │   ├── nordpool_parser.py    # Nord Pool price data parser
│   │   ├── entsoe_parser.py      # ENTSO-E XML response parser
│   │   ├── aemo_parser.py        # AEMO market data parser
│   │   └── ...                   # Other source-specific parsers
│   ├── nordpool.py       # Nord Pool API client
│   ├── entsoe.py         # ENTSO-E API client
│   ├── energy_charts.py  # Energy-Charts API client
│   ├── aemo.py           # AEMO API client
│   ├── omie.py           # OMIE API client
│   ├── stromligning.py   # Strømligning API client
│   ├── energi_data.py    # Energi Data Service API client
│   ├── comed.py          # ComEd API client
│   ├── amber.py          # Amber Electric API client
│   └── utils.py          # API utility functions
├── config_flow/          # Configuration flow logic
│   ├── __init__.py       # Config flow exports
│   ├── implementation.py # Main configuration steps
│   ├── options.py        # Options flow for reconfiguration
│   ├── schemas.py        # Voluptuous schemas for validation
│   ├── utils.py          # Config flow utility functions
│   └── validators.py     # Custom validation logic
├── const/                # Constants and configuration
│   ├── __init__.py       # Constants exports
│   ├── api.py            # API-specific constants
│   ├── areas.py          # Area codes and mappings
│   ├── attributes.py     # Sensor attribute constants
│   ├── config.py         # Configuration keys
│   ├── currencies.py     # Currency codes and mappings
│   ├── defaults.py       # Default configuration values
│   ├── display.py        # Display format constants
│   ├── energy.py         # Energy unit constants
│   ├── errors.py         # Error message constants
│   ├── intervals.py      # Interval-related constants
│   ├── network.py        # Network and timeout constants
│   ├── sensors.py        # Sensor type constants
│   ├── sources.py        # Source definitions and mappings
│   └── time.py           # Time and timezone constants
├── coordinator/          # Data coordination and management
│   ├── __init__.py       # Coordinator exports
│   ├── unified_price_manager.py  # Main price data orchestrator
│   ├── fallback_manager.py       # Source fallback logic
│   ├── data_processor.py         # Raw data processing
│   ├── cache_manager.py          # Data caching with TTL
│   ├── fetch_decision.py         # Fetch timing decisions
│   ├── data_validity.py          # Data validation logic
│   └── api_key_manager.py        # API key management
├── price/                # Price data processing
│   ├── __init__.py       # Price processing exports
│   ├── currency_converter.py # Currency and unit conversion
│   ├── currency_service.py   # ECB exchange rate service
│   ├── formatter.py          # Price display formatting
│   └── statistics.py         # Price statistics calculation
├── sensor/               # Home Assistant sensor entities
│   ├── __init__.py       # Sensor exports
│   ├── base.py           # Base sensor class
│   ├── electricity.py    # Main sensor setup
│   └── price.py          # Individual price sensor types
├── timezone/             # Timezone handling
│   ├── __init__.py           # Timezone exports
│   ├── converter.py          # Main timezone conversion
│   ├── dst_handler.py        # DST transition handling
│   ├── interval_calculator.py # 15-min interval calculations
│   ├── parser.py             # Timestamp parsing
│   ├── service.py            # Timezone service orchestrator
│   ├── source_tz.py          # Source-specific timezone logic
│   ├── timezone_converter.py # Core timezone conversion
│   ├── timezone_provider.py  # Timezone provider interface
│   └── timezone_utils.py     # Timezone utility functions
├── translations/         # UI translations
│   ├── en.json           # English translations
│   └── strings.json      # Translation strings
└── utils/                # Utility functions
    ├── __init__.py       # Utilities exports
    ├── advanced_cache.py # Advanced caching implementation
    ├── data_validator.py # Data validation helpers
    ├── date_range.py     # Date range utilities
    ├── debug_utils.py    # Debugging helpers
    ├── exchange_service.py # ECB exchange rate fetching
    ├── form_helper.py    # Configuration form helpers
    ├── parallel_fetcher.py # Parallel API fetching
    ├── rate_limiter.py   # API rate limiting
    ├── timezone_converter.py # Timezone conversion utilities
    ├── unit_conversion.py    # Unit conversion helpers
    └── validation/       # Validation modules
```

### Adding New Price Sources

1. **Create API Client**: Extend `BasePriceAPI` in `api/new_source.py`
2. **Create Parser**: Add `api/parsers/new_source_parser.py` for data parsing
3. **Register Source**: 
   - Add to `const/sources.py` (source constants and mappings)
   - Update `const/areas.py` (supported regions)
4. **Update Config Flow**: Enable source selection in configuration
5. **Add Tests**: Unit and integration tests for reliability

### Testing

- **Unit Tests**: `pytest tests/pytest/unit/`
- **Integration Tests**: `pytest tests/pytest/integration/`  
- **Manual Testing**: `python -m tests.manual.integration.source_test AREA`

### Contributing

Want to help improve GE-Spot? Check out the **[TODO folder](/TODO)** for a list of tasks!

We've organized contribution opportunities into categories:
- **Testing** - Add tests for better reliability
- **Code Quality** - Improve maintainability
- **Documentation** - Help new contributors
- **Enhancements** - Add monitoring and features
- **Future Features** - Long-term ideas

Pick something that interests you, no deadlines or pressure. See the [TODO/README.md](/TODO/README.md) for details.

---

## Technical Architecture (Advanced)

### 1. Data Flow Architecture

```mermaid
flowchart TD
    Config["User Configuration"] --> Coord["UnifiedPriceCoordinator"]
    Coord --> UPM["UnifiedPriceManager"]
    
    UPM --> LoadCache["Load Cached Data<br/>(with DataValidity)"]
    LoadCache --> ExtractValidity["Extract DataValidity"]
    ExtractValidity --> FetchDecision["FetchDecisionMaker<br/>(DataValidity-driven)"]
    
    FetchDecision --> |"Should fetch"| FilterSources["Pre-filter Failed Sources<br/>(skip sources with failure timestamp)"]
    FetchDecision --> |"Rate limited or<br/>data still valid"| UseCache["Use Cached Data"]
    
    FilterSources --> FallbackMgr["FallbackManager<br/>(Exponential Backoff:<br/>2s → 6s → 18s)"]
    
    FallbackMgr --> |"Try source 1"| API1["API Client 1<br/>(attempt 1-3)"]
    FallbackMgr --> |"Try source 2"| API2["API Client 2<br/>(attempt 1-3)"] 
    FallbackMgr --> |"Try source N"| APIN["API Client N<br/>(attempt 1-3)"]
    
    API1 --> |"Success"| Parser1["Parser 1"]
    API2 --> |"Success"| Parser2["Parser 2"]
    APIN --> |"Success"| ParserN["Parser N"]
    
    API1 --> |"Failed"| MarkFailed1["Mark source 1 failed<br/>(timestamp = now)"]
    API2 --> |"Failed"| MarkFailed2["Mark source 2 failed"]
    APIN --> |"Failed"| MarkFailedN["Mark source N failed"]
    
    MarkFailed1 -.-> HealthCheckBG["Continuous Health Check Task<br/>(running in background)"]
    MarkFailed2 -.-> HealthCheckBG
    MarkFailedN -.-> HealthCheckBG
    
    HealthCheckBG -.-> |"Every 15 min check<br/>for special windows<br/>(00:00-01:00 or 13:00-15:00)"| HealthCheck["Validate ALL sources<br/>(during window)"]
    HealthCheck --> UpdateAllStatus["Update all source statuses"]
    UpdateAllStatus -.-> FilterSources
    
    Parser1 --> Validate["Validate Parsed Data"]
    Parser2 --> Validate
    ParserN --> Validate
    
    Validate --> |"Valid"| ClearFailed["Clear failure status<br/>(timestamp = None)"]
    ClearFailed --> RawData["Raw Standardized Data"]
    
    RawData --> DataProcessor["DataProcessor"]
    
    subgraph DataProcessor["Data Processing Pipeline"]
        direction TB
        TZ["Timezone Conversion"] --> Currency["Currency Conversion"]
        Currency --> VAT["VAT Application"]
        VAT --> Stats["Statistics Calculation"]
        Stats --> CalcValidity["Calculate DataValidity"]
    end
    
    DataProcessor --> CacheStore["CacheManager.store()<br/>(with DataValidity)"]
    CacheStore --> Sensors["Home Assistant Sensors"]
    
    UseCache --> Sensors
```

### 2. Fetch Decision Logic

```mermaid
flowchart TD
    Start["Coordinator Update Trigger"] --> LoadCache["Load Cache + DataValidity"]
    LoadCache --> CheckCurrent{"DataValidity:<br/>has_current_interval?"}
    
    CheckCurrent --> |"FALSE<br/>(CRITICAL)"| RateLimitCritical{"Rate Limited?"}
    CheckCurrent --> |"TRUE"| CheckInitial{"First fetch ever?"}
    
    RateLimitCritical --> |"Yes"| UseCache["Use Cached Data<br/>(if available)"]
    RateLimitCritical --> |"No"| FetchNow["FETCH IMMEDIATELY<br/>(no current data)"]
    
    CheckInitial --> |"Yes (never fetched)"| FetchNow
    CheckInitial --> |"No"| CheckBuffer{"DataValidity:<br/>intervals_remaining<br/>< 8 intervals?"}
    
    CheckBuffer --> |"Yes<br/>(running low)"| RateLimitBuffer{"Rate Limited?"}
    CheckBuffer --> |"No"| CheckTomorrowWindow{"In tomorrow window?<br/>(13:00-15:00)"}
    
    RateLimitBuffer --> |"Yes"| UseCache
    RateLimitBuffer --> |"No"| FetchNow
    
    CheckTomorrowWindow --> |"Yes"| CheckTomorrowData{"DataValidity:<br/>tomorrow_interval_count<br/>< 76?"}
    CheckTomorrowWindow --> |"No"| CheckRateLimit{"Rate Limited?<br/>(< 15 min)"}
    
    CheckTomorrowData --> |"Yes<br/>(need tomorrow)"| RateLimitTomorrow{"Rate Limited?"}
    CheckTomorrowData --> |"No<br/>(have tomorrow)"| CheckRateLimit
    
    RateLimitTomorrow --> |"Yes"| UseCache
    RateLimitTomorrow --> |"No"| FetchNow
    
    CheckRateLimit --> |"Yes"| UseCache
    CheckRateLimit --> |"No"| FetchNow
    
    FetchNow --> PreFilter["Pre-filter Failed Sources<br/>(before FallbackManager)"]
    PreFilter --> CheckAvailable{"Any sources<br/>available?"}
    
    CheckAvailable --> |"No"| UseCache
    CheckAvailable --> |"Yes"| FallbackMgr["FallbackManager<br/>(try each source)"]
    
    FallbackMgr --> Attempt1{"Source 1<br/>Attempt 1 (2s)"}
    Attempt1 --> |"Success"| Success["Parse & Validate Data"]
    Attempt1 --> |"Fail"| Attempt2{"Source 1<br/>Attempt 2 (6s)"}
    Attempt2 --> |"Success"| Success
    Attempt2 --> |"Fail"| Attempt3{"Source 1<br/>Attempt 3 (18s)"}
    Attempt3 --> |"Success"| Success
    Attempt3 --> |"Fail"| NextSource{"More sources?"}
    
    NextSource --> |"Yes"| Attempt1
    NextSource --> |"No"| AllFailed["All Sources Failed"]
    
    AllFailed --> UseCache
    
    Success --> ClearFailed["Clear failure status<br/>(timestamp = None)"]
    ClearFailed --> ProcessData["Process & Cache<br/>(with new DataValidity)"]
    ProcessData --> UpdateSensors["Update Sensors"]
    
    UseCache --> UpdateSensors
    UpdateSensors --> End["Wait for Next Update"]
```

### 3. Cache and Rate Limiter

```mermaid
flowchart TD
    subgraph CacheManager["Cache Manager"]
        direction TB
        CacheGet["get(area, target_date, source)"] --> CacheCheck{"Cache exists & valid?"}
        CacheCheck --> |"Yes"| CacheHit["Return cached data<br/>(with DataValidity)<br/>(deep copy to prevent mutation)"]
        CacheCheck --> |"No"| CacheMiss["Return None"]
        
        CacheStore["store(area, source, data, timestamp, target_date)"] --> Serialize["Serialize data<br/>(includes DataValidity)"]
        Serialize --> WriteFile["Write to .storage/"]
        
        CacheCleanup["cleanup()"] --> FindExpired["Find expired entries"]
        FindExpired --> DeleteExpired["Delete expired files"]
    end
    
    subgraph RateLimiter["Rate Limiter"]
        direction TB
        RLCheck["should_skip_fetch()"] --> GracePeriod{"In grace period?<br/>(startup/reload)"}
        GracePeriod --> |"Yes"| AllowFetch["Allow Fetch<br/>(bypass rate limit)"]
        GracePeriod --> |"No"| LastFetch{"Last fetch time"}
        LastFetch --> |"< 15 min ago"| Blocked["Rate Limited<br/>(use cache)"]
        LastFetch --> |"≥ 15 min ago"| AllowFetch
        
        RLUpdate["update_last_fetch(source, area)"] --> StoreTime["Store current timestamp"]
    end
    
    subgraph FailedSourceTracking["Source Health & Validation"]
        direction TB
        FailedDict["self._failed_sources<br/>Dict[str, Optional[datetime]]"] --> CheckStatus{"Check source status"}
        CheckStatus --> |"timestamp = None"| SourceOK["Source validated<br/>(include in fetch)"]
        CheckStatus --> |"timestamp exists"| SourceDisabled["Source disabled<br/>(skip until health check)"]
        
        OnSuccess["On API success"] --> ClearTimestamp["Set timestamp = None"]
        OnFailure["On API failure"] --> SetTimestamp["Set timestamp = now()"]
        
        HealthCheckTask["Health Check Background Task<br/>(started at init, runs continuously)"] --> CheckLoop["Sleep 15 minutes"]
        CheckLoop --> InWindow{"In special window?<br/>(00:00-01:00 or 13:00-15:00)"}
        InWindow --> |"No"| CheckLoop
        InWindow --> |"Yes"| CheckLastWindow{"Last window hour checked<br/>!= current window hour?"}
        CheckLastWindow --> |"Same window"| CheckLoop
        CheckLastWindow --> |"Different window"| RandomDelay["Random delay 0-3600s<br/>(spread load)"]
        RandomDelay --> ValidateAll["Validate ALL sources<br/>(not just failed ones)"]
        ValidateAll --> UpdateStatus["Update all source statuses<br/>(clear or set timestamps)"]
        UpdateStatus --> MarkWindow["Mark window hour checked<br/>(0 or 13)"]
        MarkWindow --> CheckLoop
    end
    
    subgraph Integration["Integration Flow"]
        FetchRequest["Fetch Request"] --> RLCheck
        Blocked --> CacheGet
        AllowFetch --> PreFilter["Pre-filter disabled sources<br/>(sources with failure timestamp)"]
        PreFilter --> APICall["API Call with<br/>Exponential Backoff"]
        APICall --> |"Success"| OnSuccess
        APICall --> |"Failure (all attempts)"| OnFailure
        OnSuccess --> CacheStore
        OnFailure --> CacheGet
        RLUpdate --> CacheStore
    end
```

### 4. Fallback System

```mermaid
flowchart TD
    FallbackStart["FallbackManager.fetch_with_fallback()"] --> GetSources["Get enabled API instances<br/>(already pre-filtered)"]
    GetSources --> SourceLoop{"More sources to try?"}
    
    SourceLoop --> |"Yes"| NextSource["Get next source"]
    SourceLoop --> |"No"| FallbackFail["All sources failed"]
    
    NextSource --> RetryLoop["Exponential Backoff Retry Loop"]
    
    subgraph RetryLoop["Retry with Exponential Backoff"]
        direction TB
        Try1["Attempt 1: timeout=2s"] --> Check1{"Success?"}
        Check1 --> |"Yes"| Success1["✓ Return data"]
        Check1 --> |"No"| Try2["Attempt 2: timeout=6s"]
        Try2 --> Check2{"Success?"}
        Check2 --> |"Yes"| Success2["✓ Return data"]
        Check2 --> |"No"| Try3["Attempt 3: timeout=18s"]
        Try3 --> Check3{"Success?"}
        Check3 --> |"Yes"| Success3["✓ Return data"]
        Check3 --> |"No"| Failed["✗ Source failed"]
    end
    
    Success1 --> ValidateData{"Data valid?"}
    Success2 --> ValidateData
    Success3 --> ValidateData
    
    ValidateData --> |"Valid"| ParseData["Parse with source parser"]
    ValidateData --> |"Invalid"| LogError["Log error"]
    
    ParseData --> |"Success"| MarkWorking["Clear failure status<br/>(self._failed_sources[source] = None)"]
    ParseData --> |"Parse Error"| LogError
    
    MarkWorking --> FallbackSuccess["Return parsed data"]
    
    Failed --> MarkFailed["Mark source as failed<br/>(self._failed_sources[source] = now)"]
    MarkFailed --> LogError
    
    LogError --> SourceLoop
    
    FallbackSuccess --> End["Success - data ready for processing"]
    FallbackFail --> End2["Failure - use cache or empty result"]
    
    subgraph HealthCheckValidation["Continuous Health Check (Background Task)"]
        direction TB
        BGTask["Health check task runs continuously<br/>(started at initialization)"] --> Sleep["Sleep 15 minutes"]
        Sleep --> WindowCheck{"In special window?<br/>(00:00-01:00 or 13:00-15:00)"}
        WindowCheck --> |"No"| Sleep
        WindowCheck --> |"Yes, new window"| RandomDelay["Random delay (0-3600s)"]
        RandomDelay --> ValidateAllSources["Validate ALL sources<br/>(failed + working)"]
        ValidateAllSources --> UpdateStatuses["Update all source statuses:<br/>• Success → timestamp = None<br/>• Failure → timestamp = now"]
        UpdateStatuses --> Sleep
    end
    
    subgraph SourcePriority["Source Priority Example"]
        direction TB
        SE4["SE4 (Sweden)"] --> |"1st"| Nordpool["Nord Pool"]
        SE4 --> |"2nd"| EnergyCharts["Energy-Charts"]
        SE4 --> |"3rd"| ENTSOE["ENTSO-E"]
        
        DK1["DK1 (Denmark)"] --> |"1st"| NordpoolDK["Nord Pool"]
        DK1 --> |"2nd"| EnergyChartsDK["Energy-Charts"]
        DK1 --> |"3rd"| ENTSODK["ENTSO-E"] 
        DK1 --> |"4th"| EnergiData["Energi Data Service"]
        DK1 --> |"5th"| Stromligning["Strømligning"]
    end
```

## License

This integration is licensed under the MIT License.
