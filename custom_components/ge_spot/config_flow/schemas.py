"""Form schemas for config flow."""
import logging
from typing import Dict, Any
import voluptuous as vol

from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from ..const import (
    Config,
    Defaults,
    Source,
    DISPLAY_UNIT_DECIMAL, 
    DISPLAY_UNIT_CENTS, 
    DISPLAY_UNITS, 
    UPDATE_INTERVAL_OPTIONS, 
    ENTSOE_AREA_MAPPING,
)
from ..utils.form_helper import FormHelper

_LOGGER = logging.getLogger(__name__)

def get_user_schema(available_regions):
    """Return schema for the user step."""
    return vol.Schema(
        {
            vol.Required(Config.AREA, default="SE4"): selector.SelectSelector(
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
            vol.Required(Config.SOURCE_PRIORITY, default=supported_sources): selector.SelectSelector(
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
            vol.Optional(Config.VAT, default=0): vol.All(
                vol.Coerce(float),
                vol.Range(min=0, max=100),
            ),
            vol.Optional(Config.UPDATE_INTERVAL, default=60): vol.In({
                60: "1 hour",
                360: "6 hours",
                720: "12 hours",
                1440: "24 hours"
            }),
            vol.Optional(Config.DISPLAY_UNIT, default=DISPLAY_UNIT_DECIMAL): selector.SelectSelector(
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
    field = vol.Optional(f"{Source.ENTSO_E}_api_key",
                        description=description,
                        default=existing_api_key)

    # Use the FormHelper to create the API key selector
    schema_dict[field] = FormHelper.create_api_key_selector()

    return vol.Schema(schema_dict)

def get_options_schema(defaults, supported_sources):
    """Return schema for options."""
    schema = {
        vol.Optional(Config.VAT, default=defaults.get(Config.VAT, 0) * 100): vol.All(
            vol.Coerce(float),
            vol.Range(min=0, max=100),
        ),
        vol.Optional(Config.UPDATE_INTERVAL, default=defaults.get(Config.UPDATE_INTERVAL, 60)): vol.In({
            60: "1 hour",
            360: "6 hours",
            720: "12 hours",
            1440: "24 hours"
        }),
        vol.Optional(Config.DISPLAY_UNIT, default=defaults.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT)): selector.SelectSelector(
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
    current_priority = defaults.get(Config.SOURCE_PRIORITY, supported_sources)
    schema[vol.Optional(
        Config.SOURCE_PRIORITY,
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
    if Source.ENTSO_E in supported_sources:
        # Show current API key status
        current_api_key = defaults.get(Config.API_KEY, "")
        api_key_status = "API key configured" if current_api_key else "No API key configured"
        # Add field for ENTSO-E API key with the current status shown
        schema[vol.Optional(
            f"{Source.ENTSO_E}_api_key",
            description=f"Current status: {api_key_status}"
        )] = FormHelper.create_api_key_selector()

    return vol.Schema(schema)

def get_default_values(options, data):
    """Get default values from options and data."""
    try:
        defaults = {}
        # VAT - convert from decimal to percentage
        vat_decimal = options.get(Config.VAT, data.get(Config.VAT, Defaults.VAT))
        defaults[Config.VAT] = vat_decimal

        # Update interval
        defaults[Config.UPDATE_INTERVAL] = options.get(
            Config.UPDATE_INTERVAL,
            data.get(Config.UPDATE_INTERVAL, Defaults.UPDATE_INTERVAL)
        )
        # Display unit
        defaults[Config.DISPLAY_UNIT] = options.get(
            Config.DISPLAY_UNIT,
            data.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT)
        )

        # Source priority
        if Config.SOURCE_PRIORITY in options:
            defaults[Config.SOURCE_PRIORITY] = options[Config.SOURCE_PRIORITY]
        elif Config.SOURCE_PRIORITY in data:
            defaults[Config.SOURCE_PRIORITY] = data[Config.SOURCE_PRIORITY]

        # API key (if present)
        if Config.API_KEY in options or Config.API_KEY in data:
            defaults[Config.API_KEY] = options.get(Config.API_KEY, data.get(Config.API_KEY, ""))

        return defaults
    except Exception as e:
        _LOGGER.error(f"Error getting default values: {e}")
        # Return minimal defaults
        return {
            Config.VAT: Defaults.VAT,
            Config.UPDATE_INTERVAL: Defaults.UPDATE_INTERVAL,
            Config.DISPLAY_UNIT: Defaults.DISPLAY_UNIT,
        }
