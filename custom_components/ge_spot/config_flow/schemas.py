"""Form schemas for config flow."""
import logging
from typing import Dict, Any
import voluptuous as vol

from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from ..const.config import Config
from ..const.defaults import Defaults
from ..const.sources import Source
from ..const.display import DisplayUnit, UpdateInterval
from ..const.areas import AreaMapping
from ..const.time import TimezoneReference
from ..utils.form_helper import FormHelper
from ..api import get_sources_for_region

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
            vol.Required(Config.SOURCE_PRIORITY, default=supported_sources,
                         description="Priority is determined by order: first selected = highest priority"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": source, "label": Source.get_display_name(source)}
                        for source in supported_sources
                    ],
                    mode=selector.SelectSelectorMode.LIST,
                    multiple=True,
                )
            ),
            vol.Optional(Config.VAT, default=0): vol.All(
                vol.Coerce(float),
                vol.Range(min=0.0, max=100.0),
            ),
            # Make DISPLAY_UNIT required
            vol.Required(Config.DISPLAY_UNIT, default=DisplayUnit.DECIMAL): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": key, "label": value}
                        for key, value in DisplayUnit.OPTIONS.items()
                    ],
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        }
    )

def get_api_keys_schema(area, existing_api_key=None):
    """Return schema for API keys step."""
    schema_dict = {}

    # Check if area is supported by ENTSO-E mapping
    is_supported = area in AreaMapping.ENTSOE_MAPPING
    has_existing = existing_api_key is not None

    # Prepare field description
    description = None
    if has_existing:
        description = "Leave empty to use existing key"
    elif is_supported:
        description = "Required for ENTSO-E data source"

    # Create field - required for new setups, optional if we have an existing key
    if has_existing:
        # If we have an existing key, make it optional
        field = vol.Optional(f"{Source.ENTSOE}_api_key",
                            description=description,
                            default=existing_api_key)
    else:
        # For new setups, make it required
        field = vol.Required(f"{Source.ENTSOE}_api_key",
                            description=description)

    # Use the FormHelper to create the API key selector
    schema_dict[field] = FormHelper.create_api_key_selector()

    return vol.Schema(schema_dict)

# Add schema for Stromligning config step
def get_stromligning_config_schema(existing_supplier=None):
    """Return schema for Stromligning config step."""
    schema_dict = {}
    description = "Required for Strømligning data source. Complete list: https://github.com/enoch85/ge-spot/blob/main/docs/stromligning.md"

    # Create field - required for new setups
    field = vol.Required(Config.CONF_STROMLIGNING_SUPPLIER,
                        description=description)

    schema_dict[field] = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT))

    return vol.Schema(schema_dict)

def get_options_schema(defaults, supported_sources, area):
    """Return schema for options."""
    # Price calculation follows EU tax standards:
    # Final Price = (Spot Price + Additional Tariff + Energy Tax) × (1 + VAT%)
    # VAT is applied to the total of all costs, as per standard EU practice.
    schema = {
        vol.Optional(Config.VAT, default=defaults.get(Config.VAT, 0) * 100): vol.All(
            vol.Coerce(float),
            vol.Range(min=0.0, max=100.0),
        ),
        vol.Optional(
            Config.ADDITIONAL_TARIFF,
            default=defaults.get(Config.ADDITIONAL_TARIFF, Defaults.ADDITIONAL_TARIFF),
            description="Additional transfer/grid fees from your provider. Use same unit as Price Display Format (e.g. 0.05 if decimal, or 5 if cents)"
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.0,
                max=1000.0,
                step=0.001,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            Config.ENERGY_TAX,
            default=defaults.get(Config.ENERGY_TAX, Defaults.ENERGY_TAX),
            description="Fixed energy tax per kWh (e.g. government levy). Use same unit as Price Display Format. Applied before VAT."
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.0,
                max=1000.0,
                step=0.001,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(Config.DISPLAY_UNIT, default=defaults.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT)): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": key, "label": value}
                    for key, value in DisplayUnit.OPTIONS.items()
                ],
                mode=selector.SelectSelectorMode.LIST,
            )
        ),
        vol.Optional(Config.TIMEZONE_REFERENCE, default=defaults.get(Config.TIMEZONE_REFERENCE, TimezoneReference.DEFAULT)): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": key, "label": value}
                    for key, value in TimezoneReference.OPTIONS.items()
                ],
                mode=selector.SelectSelectorMode.LIST,
            )
        ),
    }

    # Add source priority selection with header
    current_priority = defaults.get(Config.SOURCE_PRIORITY, supported_sources)
    schema[vol.Optional(
        Config.SOURCE_PRIORITY,
        default=current_priority,
        description="Priority is determined by order: first selected = highest priority"
    )] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                {"value": source, "label": Source.get_display_name(source)}
                for source in supported_sources
            ],
            mode=selector.SelectSelectorMode.LIST,
            multiple=True,
        )
    )

    # Add API key fields for sources that require it
    if Source.ENTSOE in supported_sources:
        current_api_key = defaults.get(Config.API_KEY, "")
        schema[vol.Optional(
            f"{Source.ENTSOE}_api_key",
            default=current_api_key,
            description=f"{'API key configured' if current_api_key else 'Enter API key for ENTSO-E'}"
        )] = FormHelper.create_api_key_selector()

    # Add Stromligning Supplier Field Conditionally, after ENTSO-E API key
    selected_sources = defaults.get(Config.SOURCE_PRIORITY, [])
    if Source.STROMLIGNING in selected_sources:
        schema[vol.Optional(
            Config.CONF_STROMLIGNING_SUPPLIER,
            default=defaults.get(Config.CONF_STROMLIGNING_SUPPLIER, "")
        )] = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT))

    # Add Clear Cache button
    schema[vol.Optional("clear_cache", default=False)] = selector.BooleanSelector(
        selector.BooleanSelectorConfig()
    )

    return vol.Schema(schema)

def get_default_values(options, data):
    """Get default values from options and data."""
    try:
        defaults = {}
        # VAT - convert from decimal to percentage
        vat_decimal = options.get(Config.VAT, data.get(Config.VAT, Defaults.VAT))
        defaults[Config.VAT] = vat_decimal

        # Additional tariff
        defaults[Config.ADDITIONAL_TARIFF] = options.get(
            Config.ADDITIONAL_TARIFF,
            data.get(Config.ADDITIONAL_TARIFF, Defaults.ADDITIONAL_TARIFF)
        )

        # Energy tax
        defaults[Config.ENERGY_TAX] = options.get(
            Config.ENERGY_TAX,
            data.get(Config.ENERGY_TAX, Defaults.ENERGY_TAX)
        )

        # Display unit
        defaults[Config.DISPLAY_UNIT] = options.get(
            Config.DISPLAY_UNIT,
            data.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT)
        )

        # Timezone reference
        defaults[Config.TIMEZONE_REFERENCE] = options.get(
            Config.TIMEZONE_REFERENCE,
            data.get(Config.TIMEZONE_REFERENCE, TimezoneReference.DEFAULT)
        )

        # Source priority
        if Config.SOURCE_PRIORITY in options:
            defaults[Config.SOURCE_PRIORITY] = options[Config.SOURCE_PRIORITY]
        elif Config.SOURCE_PRIORITY in data:
            defaults[Config.SOURCE_PRIORITY] = data[Config.SOURCE_PRIORITY]

        # API key (if present)
        if Config.API_KEY in options or Config.API_KEY in data:
            defaults[Config.API_KEY] = options.get(Config.API_KEY, data.get(Config.API_KEY, ""))

        # Stromligning Supplier (from data, not options)
        if Config.CONF_STROMLIGNING_SUPPLIER in data:
            defaults[Config.CONF_STROMLIGNING_SUPPLIER] = data.get(Config.CONF_STROMLIGNING_SUPPLIER, "")

        return defaults
    except Exception as e:
        _LOGGER.error(f"Error getting default values: {e}")
        # Return minimal defaults
        return {
            Config.VAT: Defaults.VAT,
            Config.DISPLAY_UNIT: Defaults.DISPLAY_UNIT,
        }
