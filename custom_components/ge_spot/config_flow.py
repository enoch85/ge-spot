"""Config flow for GE-Spot integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN, CONF_AREA, CONF_VAT, CONF_UPDATE_INTERVAL,
    CONF_DISPLAY_UNIT, CONF_ENABLE_FALLBACK, CONF_SOURCE_PRIORITY,
    NORDPOOL_AREAS, ENERGI_DATA_AREAS, ENTSOE_AREAS, EPEX_AREAS, OMIE_AREAS, AEMO_AREAS,
    DEFAULT_AREAS
)
from .config_utils import (
    common_schema, get_default_values
)
from .api import get_sources_for_region

_LOGGER = logging.getLogger(__name__)

# Combine all areas to create a unified region list
ALL_REGIONS = {}
ALL_REGIONS.update(NORDPOOL_AREAS)
ALL_REGIONS.update(ENERGI_DATA_AREAS)
ALL_REGIONS.update(ENTSOE_AREAS)
ALL_REGIONS.update(EPEX_AREAS)
ALL_REGIONS.update(OMIE_AREAS)
ALL_REGIONS.update(AEMO_AREAS)

class GSpotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GE-Spot integration."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize the config flow."""
        self._data = {}
        self._supported_sources = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return GSpotOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            # Store the area in our data
            area = user_input[CONF_AREA]
            self._data[CONF_AREA] = area
            
            # Get list of sources that support this area
            self._supported_sources = get_sources_for_region(area)
            
            if not self._supported_sources:
                errors[CONF_AREA] = "no_sources_for_region"
            else:
                # Check for duplicate entries
                await self.async_set_unique_id(f"gespot_{area}")
                self._abort_if_unique_id_configured()
                
                # Proceed to source priority step
                return await self.async_step_source_priority()

        # Get regions with at least one source
        available_regions = {}
        for region, name in sorted(ALL_REGIONS.items(), key=lambda x: x[1]):
            if get_sources_for_region(region):
                available_regions[region] = name

        # Show region selection form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_AREA, default="SE4"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": area, "label": name}
                                for area, name in available_regions.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_source_priority(self, user_input=None):
        """Handle setting source priorities."""
        errors = {}

        if user_input is not None:
            # Store source priority
            self._data[CONF_SOURCE_PRIORITY] = user_input[CONF_SOURCE_PRIORITY]
            
            # Add additional config
            self._data[CONF_VAT] = user_input.get(CONF_VAT, 0)
            self._data[CONF_UPDATE_INTERVAL] = user_input.get(CONF_UPDATE_INTERVAL, 60)
            self._data[CONF_DISPLAY_UNIT] = user_input.get(CONF_DISPLAY_UNIT, "decimal")
            self._data[CONF_ENABLE_FALLBACK] = user_input.get(CONF_ENABLE_FALLBACK, True)
            
            # Check if any source requires an API key
            requires_api_key = any(source == "entsoe" for source in self._data[CONF_SOURCE_PRIORITY])
            
            if requires_api_key:
                return await self.async_step_api_keys()
            else:
                # All done, create the config entry
                return self.async_create_entry(
                    title=f"GE-Spot - {ALL_REGIONS.get(self._data[CONF_AREA], self._data[CONF_AREA])}",
                    data=self._data,
                )

        # Create config schema for source priority
        schema_dict = {
            vol.Required(CONF_SOURCE_PRIORITY, default=self._supported_sources): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": source, "label": source.replace("_", " ").title()}
                        for source in self._supported_sources
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    multiple=True,
                )
            ),
        }
        
        # Add common options
        schema_dict.update(common_schema({}))

        return self.async_show_form(
            step_id="source_priority",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_api_keys(self, user_input=None):
        """Handle API key entry for sources that require it."""
        errors = {}

        if user_input is not None:
            # Store API keys in data
            for source, api_key in user_input.items():
                if api_key:  # Only store non-empty keys
                    self._data[f"{source}_api_key"] = api_key
            
            # Create the config entry
            return self.async_create_entry(
                title=f"GE-Spot - {ALL_REGIONS.get(self._data[CONF_AREA], self._data[CONF_AREA])}",
                data=self._data,
            )

        # Create schema for API key entry
        schema_dict = {}
        
        # Add fields for each source that requires an API key
        if "entsoe" in self._data[CONF_SOURCE_PRIORITY]:
            schema_dict[vol.Required("entsoe_api_key")] = cv.string

        return self.async_show_form(
            step_id="api_keys",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

class GSpotOptionsFlow(config_entries.OptionsFlow):
    """Handle GE-Spot options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.entry_id = config_entry.entry_id
        self._data = dict(config_entry.data)
        self._options = dict(config_entry.options)
        self._area = self._data.get(CONF_AREA)
        self._supported_sources = get_sources_for_region(self._area) if self._area else []

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}

        if user_input is not None:
            # Handle source priority updates if present
            if CONF_SOURCE_PRIORITY in user_input:
                updated_data = dict(self._data)
                updated_data[CONF_SOURCE_PRIORITY] = user_input[CONF_SOURCE_PRIORITY]
                
                # Update the config entry data
                self.hass.config_entries.async_update_entry(
                    self.hass.config_entries.async_get_entry(self.entry_id),
                    data=updated_data
                )
            
            # Handle normal options
            return self.async_create_entry(title="", data=user_input)

        defaults = get_default_values(self._options, self._data)

        # Common options schema
        schema = common_schema(defaults)
        
        # Add source priority selection
        current_priority = self._data.get(CONF_SOURCE_PRIORITY, self._supported_sources)
        schema[vol.Optional(
            CONF_SOURCE_PRIORITY,
            default=current_priority
        )] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": source, "label": source.replace("_", " ").title()}
                    for source in self._supported_sources
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
                multiple=True,
            )
        )

        # Add API key fields for sources that require it
        if "entsoe" in self._supported_sources:
            schema[vol.Optional(
                "entsoe_api_key",
                default=self._data.get("entsoe_api_key", "")
            )] = cv.string

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            errors=errors,
        )
