"""Utility functions for config flows."""
import logging
import voluptuous as vol
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_VAT, CONF_UPDATE_INTERVAL, CONF_DISPLAY_UNIT,
    DEFAULT_VAT, DEFAULT_UPDATE_INTERVAL, DEFAULT_DISPLAY_UNIT,
    DISPLAY_UNITS, UPDATE_INTERVAL_OPTIONS
)

_LOGGER = logging.getLogger(__name__)

def common_schema(defaults):
    """Return schema with common options."""
    return {
        vol.Optional(CONF_VAT, default=defaults.get(CONF_VAT, DEFAULT_VAT) * 100): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=100),
            description={
                "suggested_value": defaults.get(CONF_VAT, DEFAULT_VAT) * 100,
                "suffix": "%", 
                "name": "VAT Rate",
                "description": "Value added tax (VAT) to apply to prices (0-100%)"
            }
        ),
        vol.Optional(CONF_UPDATE_INTERVAL, default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=UPDATE_INTERVAL_OPTIONS,
                mode=selector.SelectSelectorMode.DROPDOWN,
                translation_key="update_interval",
            )
        ),
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

async def handle_area_config(flow, user_input, source_name, areas_dict, default_area):
    """Generic handler for area configuration."""
    errors = {}

    if user_input is not None and CONF_AREA in user_input:
        # Convert VAT from percentage to decimal
        if CONF_VAT in user_input:
            user_input[CONF_VAT] = user_input[CONF_VAT] / 100
            
        # Update the stored data with area and other configs
        data = {**flow._data, **user_input}
        _LOGGER.debug(f"Creating entry with data: {data}")

        # Save the config
        return flow.async_create_entry(
            title=f"{source_name.replace('_', ' ').title()} - {areas_dict[user_input[CONF_AREA]]}",
            data=data,
        )

    # Show area selection form
    schema_dict = {
        vol.Required(CONF_AREA, default=default_area): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": area, "label": name}
                    for area, name in areas_dict.items()
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }
    # Add common options
    schema_dict.update(common_schema({}))

    return flow.async_show_form(
        step_id=source_name,
        data_schema=vol.Schema(schema_dict),
        errors=errors,
    )

async def handle_api_key_config(flow, user_input, source_name, areas_dict, default_area):
    """Generic handler for API key configuration."""
    errors = {}

    if user_input is not None and CONF_AREA in user_input:
        # Validate API key
        if not user_input.get("api_key"):
            errors["api_key"] = "api_key_required"
        else:
            # Convert VAT from percentage to decimal
            if CONF_VAT in user_input:
                user_input[CONF_VAT] = user_input[CONF_VAT] / 100
                
            # Update the stored data with area and other configs
            data = {**flow._data, **user_input}
            _LOGGER.debug(f"Creating entry with data: {data}")

            # Save the config
            return flow.async_create_entry(
                title=f"{source_name.replace('_', ' ').title()} - {areas_dict[user_input[CONF_AREA]]}",
                data=data,
            )

    # Show area selection form
    schema_dict = {
        vol.Required(CONF_AREA, default=default_area): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": area, "label": name}
                    for area, name in areas_dict.items()
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required("api_key"): cv.string,
    }
    # Add common options
    schema_dict.update(common_schema({}))

    return flow.async_show_form(
        step_id=source_name,
        data_schema=vol.Schema(schema_dict),
        errors=errors,
    )

def get_default_values(options, data):
    """Get default values from options and data."""
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
    
    # API key (if present)
    if "api_key" in options or "api_key" in data:
        defaults["api_key"] = options.get("api_key", data.get("api_key", ""))

    return defaults
