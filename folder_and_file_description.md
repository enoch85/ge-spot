custom_components/ge_spot/
│
├── __init__.py                   # Main integration entry point
├── manifest.json                 # Integration manifest
├── config_flow.py                # Config flow redirector
│
├── api/                          # API interfaces for different services
│   ├── __init__.py               # API registry and utilities
│   ├── aemo.py                   # Australian Energy Market Operator API
│   ├── base/                     # Base API implementation
│   │   ├── __init__.py           # Base energy API class
│   │   ├── data_fetch.py         # Data fetching utilities
│   │   ├── price_conversion.py   # Price conversion utilities
│   │   └── session_manager.py    # Session management
│   ├── energi_data.py            # Energi Data Service API
│   ├── entsoe.py                 # ENTSO-E API
│   ├── epex.py                   # EPEX SPOT API
│   ├── nordpool.py               # Nordpool API
│   ├── nordpool_utils.py         # Utilities for Nordpool API
│   └── omie.py                   # OMIE API
│
├── config_flow/                  # Config flow functionality
│   ├── __init__.py               # Config flow exports
│   ├── implementation.py         # Config flow implementation
│   ├── options.py                # Options flow
│   ├── schemas.py                # Form schemas
│   ├── utils.py                  # Config flow utilities
│   └── validators.py             # Validation functions
│
├── const/                        # Constants
│   ├── __init__.py               # Main constants exports
│   ├── areas.py                  # Area constants
│   ├── attributes.py             # Attribute constants
│   ├── config.py                 # Configuration constants
│   ├── currencies.py             # Currency constants
│   ├── defaults.py               # Default values
│   ├── display.py                # Display constants
│   ├── errors.py                 # Error message constants
│   ├── precision.py              # Precision constants
│   ├── sensors.py                # Sensor constants
│   └── sources.py                # Energy price sources
│
├── coordinator/                  # Coordinator functionality
│   ├── __init__.py               # Coordinator exports
│   └── region.py                 # Regional price coordinator
│
├── price/                        # All price-related functionality
│   ├── __init__.py               # Price functionality exports
│   ├── adapter.py                # Price adapter
│   ├── conversion.py             # Core conversion logic
│   ├── currency.py               # Currency-specific logic
│   ├── energy.py                 # Energy unit conversions
│   └── statistics.py             # Statistics calculation
│
├── sensor/                       # Sensor definitions
│   ├── __init__.py               # Sensor exports
│   ├── base.py                   # Base sensor implementation
│   ├── electricity.py            # Electricity price sensors setup
│   └── price.py                  # Price-specific sensor implementations
│
├── timezone/                     # Timezone handling
│   ├── __init__.py               # Timezone exports
│   ├── converters.py             # Timezone conversion utilities
│   └── parsers.py                # Date/time parsing utilities
│
├── translations/                 # Translations
│   └── strings.json              # String translations
│
└── utils/                        # General utilities
    ├── __init__.py               # Utilities exports
    ├── api_client.py             # API client utilities
    ├── api_validator.py          # API validation utilities
    ├── debug_utils.py            # Debug utilities
    ├── error_handler.py          # Error handling utilities
    ├── exchange_service.py       # Currency exchange service
    └── form_helper.py            # Form helper utilities
