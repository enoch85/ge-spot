"""Utility functions for config flow."""
import logging
import voluptuous as vol
from homeassistant.helpers import selector

from ..const import (
    CONF_AREA,
    CONF_VAT,
    CONF_UPDATE_INTERVAL,
    CONF_DISPLAY_UNIT,
    CONF_SOURCE_PRIORITY,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_DISPLAY_UNIT,
    DEFAULT_VAT,
    DISPLAY_UNITS,
    UPDATE_INTERVAL_OPTIONS,
    NORDPOOL_AREAS,
    ENERGI_DATA_AREAS,
    ENTSOE_AREAS,
    EPEX_AREAS,
    OMIE_AREAS,
    AEMO_AREAS,
    ENTSOE_AREA_MAPPING,
    SOURCE_NORDPOOL,
    SOURCE_ENERGI_DATA_SERVICE,
    SOURCE_ENTSO_E,
    SOURCE_EPEX,
    SOURCE_OMIE,
    SOURCE_AEMO,
)
from ..api import get_sources_for_region, create_api

_LOGGER = logging.getLogger(__name__)

# Mapping of source to area dictionaries for convenience
SOURCE_AREA_MAPS = {
    SOURCE_NORDPOOL: NORDPOOL_AREAS,
    SOURCE_ENERGI_DATA_SERVICE: ENERGI_DATA_AREAS,
    SOURCE_ENTSO_E: ENTSOE_AREAS,
    SOURCE_EPEX: EPEX_AREAS,
    SOURCE_OMIE: OMIE_AREAS,
    SOURCE_AEMO: AEMO_AREAS,
}

# Define a list of API sources in priority order for UI display
API_SOURCE_PRIORITIES = [
    SOURCE_NORDPOOL,      # Highest priority
    SOURCE_ENTSO_E,
    SOURCE_ENERGI_DATA_SERVICE,
    SOURCE_EPEX,
    SOURCE_OMIE,
    SOURCE_AEMO           # Lowest priority
]

def get_user_schema(available_regions):
    """Return schema for the user step."""
    return vol.Schema(
        {
            vol.Required(CONF_AREA, default="SE4"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": area, "label": name}
                        for area, name in sorted(available_regions.items(), key=lambda x: x[1])
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )

def get_source_priority_schema(supported_sources):
    """Return schema for source priority step."""
    return vol.Schema(
        {
            vol.Required(CONF_SOURCE_PRIORITY, default=supported_sources): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": source, "label": source.replace("_", " ").title()}
                        for source in supported_sources
                    ],
                    mode=selector.SelectSelectorMode.LIST,
                    multiple=True,
                )
            ),
            # Add description text field (non-interactive) to explain how priority works
            vol.Optional("priority_info", default="Priority is determined by order: first selected = highest priority"): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEXT,
                    multiline=True,
                )
            ),
            vol.Optional(CONF_VAT, default=0): vol.All(
                vol.Coerce(float),
                vol.Range(min=0, max=100),
            ),
            vol.Optional(CONF_UPDATE_INTERVAL, default=60): vol.In({
                60: "1 hour",
                360: "6 hours",
                720: "12 hours",
                1440: "24 hours"
            }),
            vol.Optional(CONF_DISPLAY_UNIT, default=DEFAULT_DISPLAY_UNIT): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": key, "label": value}
                        for key, value in DISPLAY_UNITS.items()
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )

def get_api_keys_schema(area, existing_api_key=None):
    """Return schema for API keys step."""
    schema_dict = {}

    # Make API key optional if area is supported by ENTSO-E mapping
    is_supported = area in ENTSOE_AREA_MAPPING
    has_existing = existing_api_key is not None

    # Prepare field - optional for supported areas or if we have an existing key
    description = None
    if has_existing:
        description = "Leave empty to use existing key"

    # Create field with appropriate defaults and description
    field = vol.Optional(f"{SOURCE_ENTSO_E}_api_key",
                        description=description,
                        default=existing_api_key)

    # Use a text selector for the API key
    schema_dict[field] = selector.TextSelector(
        selector.TextSelectorConfig(
            type=selector.TextSelectorType.TEXT,
            autocomplete="off"
        )
    )

    return vol.Schema(schema_dict)

def get_options_schema(defaults, supported_sources):
    """Return schema for options."""
    schema = {
        vol.Optional(CONF_VAT, default=defaults.get(CONF_VAT, 0) * 100): vol.All(
            vol.Coerce(float),
            vol.Range(min=0, max=100),
        ),
        vol.Optional(CONF_UPDATE_INTERVAL, default=defaults.get(CONF_UPDATE_INTERVAL, 60)): vol.In({
            60: "1 hour",
            360: "6 hours",
            720: "12 hours",
            1440: "24 hours"
        }),
        vol.Optional(CONF_DISPLAY_UNIT, default=defaults.get(CONF_DISPLAY_UNIT, DEFAULT_DISPLAY_UNIT)): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": key, "label": value}
                    for key, value in DISPLAY_UNITS.items()
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }

    # Add source priority selection
    current_priority = defaults.get(CONF_SOURCE_PRIORITY, supported_sources)
    schema[vol.Optional(
        CONF_SOURCE_PRIORITY,
        default=current_priority
    )] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                {"value": source, "label": source.replace("_", " ").title()}
                for source in supported_sources
            ],
            mode=selector.SelectSelectorMode.LIST,
            multiple=True,
        )
    )

    # Add description text to explain priority
    schema[vol.Optional("priority_info", default="Priority is determined by order: first selected = highest priority")] = selector.TextSelector(
        selector.TextSelectorConfig(
            type=selector.TextSelectorType.TEXT,
            multiline=True,
        )
    )

    # Add API key fields for sources that require it
    if SOURCE_ENTSO_E in supported_sources:
        # Show current API key status
        current_api_key = defaults.get("api_key", "")
        api_key_status = "API key configured" if current_api_key else "No API key configured"
        # Add field for ENTSO-E API key with the current status shown
        schema[vol.Optional(
            f"{SOURCE_ENTSO_E}_api_key",
            description=f"Current status: {api_key_status}"
        )] = selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.TEXT,
                autocomplete="off"
            )
        )

    return vol.Schema(schema)

def get_default_values(options, data):
    """Get default values from options and data."""
    try:
        defaults = {}
        # VAT - convert from decimal to percentage
        vat_decimal = options.get(CONF_VAT, data.get(CONF_VAT, DEFAULT_VAT))
        defaults[CONF_VAT] = vat_decimal

        # Update interval
        defaults[CONF_UPDATE_INTERVAL] = options.get(
            CONF_UPDATE_INTERVAL,
            data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )
        # Display unit
        defaults[CONF_DISPLAY_UNIT] = options.get(
            CONF_DISPLAY_UNIT,
            data.get(CONF_DISPLAY_UNIT, DEFAULT_DISPLAY_UNIT)
        )

        # Source priority
        if CONF_SOURCE_PRIORITY in options:
            defaults[CONF_SOURCE_PRIORITY] = options[CONF_SOURCE_PRIORITY]
        elif CONF_SOURCE_PRIORITY in data:
            defaults[CONF_SOURCE_PRIORITY] = data[CONF_SOURCE_PRIORITY]

        # API key (if present)
        if "api_key" in options or "api_key" in data:
            defaults["api_key"] = options.get("api_key", data.get("api_key", ""))

        return defaults
    except Exception as e:
        _LOGGER.error(f"Error getting default values: {e}")
        # Return minimal defaults
        return {
            CONF_VAT: DEFAULT_VAT,
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_DISPLAY_UNIT: DEFAULT_DISPLAY_UNIT,
        }

def get_deduplicated_regions():
    """Get a deduplicated list of regions by display name."""
    # Create a mapping of display_name → list of region info tuples
    display_name_map = {}

    # First, collect all regions from all sources
    for source, area_dict in SOURCE_AREA_MAPS.items():
        source_priority = API_SOURCE_PRIORITIES.index(source) if source in API_SOURCE_PRIORITIES else 999
        for region_code, display_name in area_dict.items():
            # Normalize display name to handle different capitalizations
            normalized_name = display_name.lower()
            if normalized_name not in display_name_map:
                display_name_map[normalized_name] = []
            # Store tuple of (source_priority, region_code, display_name, source)
            display_name_map[normalized_name].append((
                source_priority, region_code, display_name, source
            ))

    # Now create a deduplicated regions dictionary
    deduplicated_regions = {}
    for name_variants in display_name_map.values():
        # Sort by source priority (lower number = higher priority)
        sorted_variants = sorted(name_variants)
        # Choose the preferred region code based on source priority
        for priority, region_code, display_name, source in sorted_variants:
            try:
                # Only include if the region is supported by at least one API
                supported_sources = get_sources_for_region(region_code)
                if supported_sources:
                    deduplicated_regions[region_code] = display_name
                    break
            except Exception as e:
                _LOGGER.error(f"Error checking sources for region {region_code}: {e}")
                # Continue to next variant rather than fail completely
                continue

    _LOGGER.debug(f"Deduplicated regions: {len(deduplicated_regions)} entries")
    return deduplicated_regions

async def validate_entso_e_api_key(api_key, area, session=None):
    """Validate an ENTSO-E API key by making a test request."""
    try:
        # Create a temporary API instance
        config = {
            "area": area,
            "api_key": api_key
        }
        api = create_api(SOURCE_ENTSO_E, config)

        # Use provided session if available
        if session and hasattr(api, "session"):
            api.session = session
            api._owns_session = False

        # Try to validate the API key
        if hasattr(api, "validate_api_key"):
            if api.__class__.__name__ == "EntsoEAPI":
                # For EntsoEAPI, call the static method with required arguments
                result = await api.__class__.validate_api_key(api_key, area, session)
            else:
                # For other API types that use the instance method
                result = await api.validate_api_key(api_key)
        else:
            # Fall back to fetching data as a validation test
            result = False
            data = await api.fetch_day_ahead_prices(area, "EUR", None)
            if data:
                result = True

        # Close session if we created one
        if hasattr(api, '_owns_session') and api._owns_session and hasattr(api, 'close'):
            await api.close()

        return result

    except Exception as e:
        _LOGGER.error(f"API key validation error: {e}")
        return False
