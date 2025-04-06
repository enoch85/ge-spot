"""Form schemas for config flow."""
import logging
from typing import Dict, Any
import voluptuous as vol

from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from ..const import (
    CONF_AREA, CONF_VAT, CONF_UPDATE_INTERVAL,
    CONF_DISPLAY_UNIT, CONF_SOURCE_PRIORITY, CONF_API_KEY,
    DISPLAY_UNIT_DECIMAL, DISPLAY_UNITS, SOURCE_ENTSO_E,
    UPDATE_INTERVAL_OPTIONS, ENTSOE_AREA_MAPPING,
    DEFAULT_VAT, DEFAULT_UPDATE_INTERVAL, DEFAULT_DISPLAY_UNIT,
)
from ..utils.form_helper import FormHelper

_LOGGER = logging.getLogger(__name__)

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
            vol.Optional(CONF_DISPLAY_UNIT, default=DISPLAY_UNIT_DECIMAL): selector.SelectSelector(
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

    # Use the FormHelper to create the API key selector
    schema_dict[field] = FormHelper.create_api_key_selector()

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
        vol.Optional(CONF_DISPLAY_UNIT, default=defaults.get(CONF_DISPLAY_UNIT, DISPLAY_UNIT_DECIMAL)): selector.SelectSelector(
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
        current_api_key = defaults.get(CONF_API_KEY, "")
        api_key_status = "API key configured" if current_api_key else "No API key configured"
        # Add field for ENTSO-E API key with the current status shown
        schema[vol.Optional(
            f"{SOURCE_ENTSO_E}_api_key",
            description=f"Current status: {api_key_status}"
        )] = FormHelper.create_api_key_selector()

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
        if CONF_API_KEY in options or CONF_API_KEY in data:
            defaults[CONF_API_KEY] = options.get(CONF_API_KEY, data.get(CONF_API_KEY, ""))

        return defaults
    except Exception as e:
        _LOGGER.error(f"Error getting default values: {e}")
        # Return minimal defaults
        return {
            CONF_VAT: DEFAULT_VAT,
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_DISPLAY_UNIT: DEFAULT_DISPLAY_UNIT,
        }
