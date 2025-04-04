"""Config flow for GE-Spot integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN, CONF_AREA, CONF_VAT, CONF_UPDATE_INTERVAL,
    CONF_DISPLAY_UNIT, CONF_SOURCE_PRIORITY, CONF_ENABLE_FALLBACK,
    NORDPOOL_AREAS, ENERGI_DATA_AREAS, ENTSOE_AREAS, EPEX_AREAS, OMIE_AREAS, AEMO_AREAS,
    DEFAULT_AREAS, SOURCE_NORDPOOL, SOURCE_ENERGI_DATA_SERVICE, SOURCE_ENTSO_E, 
    SOURCE_EPEX, SOURCE_OMIE, SOURCE_AEMO,
    DISPLAY_UNIT_DECIMAL, DISPLAY_UNIT_CENTS, DISPLAY_UNITS,
    UPDATE_INTERVAL_OPTIONS
)
from .config_utils import (
    common_schema, get_default_values
)
from .api import get_sources_for_region

_LOGGER = logging.getLogger(__name__)

# Define a list of API sources in priority order for UI display
API_SOURCE_PRIORITIES = [
    SOURCE_NORDPOOL,      # Highest priority
    SOURCE_ENTSO_E,
    SOURCE_ENERGI_DATA_SERVICE, 
    SOURCE_EPEX,
    SOURCE_OMIE,
    SOURCE_AEMO           # Lowest priority
]

# Mapping of source to area dictionaries
SOURCE_AREA_MAPS = {
    SOURCE_NORDPOOL: NORDPOOL_AREAS,
    SOURCE_ENERGI_DATA_SERVICE: ENERGI_DATA_AREAS,
    SOURCE_ENTSO_E: ENTSOE_AREAS,
    SOURCE_EPEX: EPEX_AREAS,
    SOURCE_OMIE: OMIE_AREAS,
    SOURCE_AEMO: AEMO_AREAS,
}

def get_deduplicated_regions():
    """Get a deduplicated list of regions by display name."""
    # 1. Create a mapping of display_name → list of region info tuples
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
    
    # 2. Now create a deduplicated regions dictionary
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
    
    _LOGGER.debug(f"Deduplicated regions: {deduplicated_regions}")
    return deduplicated_regions

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
            try:
                # Store the area in our data
                area = user_input[CONF_AREA]
                self._data[CONF_AREA] = area
                
                # Get list of sources that support this area
                try:
                    self._supported_sources = get_sources_for_region(area)
                    _LOGGER.info(f"Supported sources for {area}: {self._supported_sources}")
                except Exception as e:
                    _LOGGER.error(f"Error getting sources for {area}: {e}")
                    errors[CONF_AREA] = "error_sources_for_region"
                    self._supported_sources = []
                
                if not self._supported_sources and not errors:
                    errors[CONF_AREA] = "no_sources_for_region"
                else:
                    # Check for duplicate entries
                    await self.async_set_unique_id(f"gespot_{area}")
                    self._abort_if_unique_id_configured()
                    
                    # Proceed to source priority step
                    return await self.async_step_source_priority()
            except Exception as e:
                _LOGGER.error(f"Unexpected error in async_step_user: {e}")
                errors["base"] = "unknown"

        try:
            # Get regions with at least one source, properly deduplicated
            available_regions = get_deduplicated_regions()

            # Show region selection form
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
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
                ),
                errors=errors,
            )
        except Exception as e:
            _LOGGER.error(f"Failed to create form: {e}")
            errors["base"] = "unknown"
            # Provide a fallback form if we can't create the proper one
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({vol.Required(CONF_AREA): str}),
                errors=errors,
            )

    async def async_step_source_priority(self, user_input=None):
        """Handle setting source priorities."""
        errors = {}

        if user_input is not None:
            try:
                # Convert VAT from percentage to decimal if present
                if CONF_VAT in user_input:
                    user_input[CONF_VAT] = user_input[CONF_VAT] / 100
                    
                # Store source priority
                self._data[CONF_SOURCE_PRIORITY] = user_input[CONF_SOURCE_PRIORITY]
                
                # Add additional config
                self._data[CONF_VAT] = user_input.get(CONF_VAT, 0)
                self._data[CONF_UPDATE_INTERVAL] = user_input.get(CONF_UPDATE_INTERVAL, 60)
                self._data[CONF_DISPLAY_UNIT] = user_input.get(CONF_DISPLAY_UNIT, DISPLAY_UNIT_DECIMAL)
                
                # Always enable fallback
                self._data[CONF_ENABLE_FALLBACK] = True
                
                # Check if any source requires an API key - use SOURCE_ENTSO_E constant
                requires_api_key = any(source == SOURCE_ENTSO_E for source in self._data[CONF_SOURCE_PRIORITY])
                
                if requires_api_key:
                    return await self.async_step_api_keys()
                else:
                    # Get the display name for the region
                    region_code = self._data[CONF_AREA]
                    region_name = None
                    for source, area_dict in SOURCE_AREA_MAPS.items():
                        if region_code in area_dict:
                            region_name = area_dict[region_code]
                            break
                    
                    if not region_name:
                        region_name = region_code
                    
                    # All done, create the config entry
                    return self.async_create_entry(
                        title=f"GE-Spot - {region_name}",
                        data=self._data,
                    )
            except Exception as e:
                _LOGGER.error(f"Error in async_step_source_priority: {e}")
                errors["base"] = "unknown"

        # Create config schema for source priority
        try:
            # Convert values to strings for the selector
            string_update_interval_options = []
            for option in UPDATE_INTERVAL_OPTIONS:
                # Ensure value is a string
                new_option = option.copy()
                if "value" in new_option and not isinstance(new_option["value"], str):
                    new_option["value"] = str(new_option["value"])
                string_update_interval_options.append(new_option)

            # Create display unit options from DISPLAY_UNITS
            display_unit_options = []
            for key, label in DISPLAY_UNITS.items():
                display_unit_options.append({"value": key, "label": label})

            schema_dict = {
                vol.Required(CONF_SOURCE_PRIORITY, default=self._supported_sources): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": source, "label": source.replace("_", " ").title()}
                            for source in self._supported_sources
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                        multiple=True,
                    )
                ),
                # Add description text field (non-interactive) to explain how priority works
                vol.Optional("priority_info", default=""): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        multiline=True,
                        suffix="Priority is determined by order: first selected = highest priority",
                        readonly=True,
                    )
                ),
                vol.Optional(CONF_VAT, default=0): vol.All(
                    vol.Coerce(float), 
                    vol.Range(min=0, max=100),
                    msg="Enter VAT percentage (0-100)"
                ),
                vol.Optional(CONF_UPDATE_INTERVAL, default=60): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=string_update_interval_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_DISPLAY_UNIT, default=DISPLAY_UNIT_DECIMAL): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=display_unit_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        multiple=False,
                    )
                ),
            }

            return self.async_show_form(
                step_id="source_priority",
                data_schema=vol.Schema(schema_dict),
                errors=errors,
            )
        except Exception as e:
            _LOGGER.error(f"Failed to create source priority form: {e}")
            errors["base"] = "unknown"
            # Provide a fallback schema
            return self.async_show_form(
                step_id="source_priority",
                data_schema=vol.Schema({
                    vol.Required(CONF_SOURCE_PRIORITY): str,
                }),
                errors=errors,
            )

    async def async_step_api_keys(self, user_input=None):
        """Handle API key entry for sources that require it."""
        errors = {}

        if user_input is not None:
            try:
                # Store API keys in data
                for source, api_key in user_input.items():
                    if api_key:  # Only store non-empty keys
                        self._data[f"{source}_api_key"] = api_key
                
                # Get the display name for the region for the title
                region_code = self._data[CONF_AREA]
                region_name = None
                for source, area_dict in SOURCE_AREA_MAPS.items():
                    if region_code in area_dict:
                        region_name = area_dict[region_code]
                        break
                
                if not region_name:
                    region_name = region_code
                    
                # Create the config entry
                return self.async_create_entry(
                    title=f"GE-Spot - {region_name}",
                    data=self._data,
                )
            except Exception as e:
                _LOGGER.error(f"Error in async_step_api_keys: {e}")
                errors["base"] = "unknown"

        # Create schema for API key entry
        try:
            schema_dict = {}
            
            # Add fields for each source that requires an API key - use SOURCE_ENTSO_E constant
            if SOURCE_ENTSO_E in self._data[CONF_SOURCE_PRIORITY]:
                schema_dict[vol.Required(f"{SOURCE_ENTSO_E}_api_key")] = cv.string

            return self.async_show_form(
                step_id="api_keys",
                data_schema=vol.Schema(schema_dict),
                errors=errors,
            )
        except Exception as e:
            _LOGGER.error(f"Failed to create API keys form: {e}")
            errors["base"] = "unknown"
            return self.async_show_form(
                step_id="api_keys",
                data_schema=vol.Schema({vol.Optional("api_key"): str}),
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
        try:
            self._supported_sources = get_sources_for_region(self._area) if self._area else []
        except Exception as e:
            _LOGGER.error(f"Error getting sources for {self._area}: {e}")
            self._supported_sources = []

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}

        if user_input is not None:
            try:
                # Convert VAT from percentage to decimal if present
                if CONF_VAT in user_input:
                    user_input[CONF_VAT] = user_input[CONF_VAT] / 100
                    
                # Handle source priority updates if present
                if CONF_SOURCE_PRIORITY in user_input:
                    updated_data = dict(self._data)
                    updated_data[CONF_SOURCE_PRIORITY] = user_input[CONF_SOURCE_PRIORITY]
                    
                    # Update the config entry data
                    self.hass.config_entries.async_update_entry(
                        self.hass.config_entries.async_get_entry(self.entry_id),
                        data=updated_data
                    )
                
                # Always enable fallback
                user_input[CONF_ENABLE_FALLBACK] = True
                
                # Handle normal options
                return self.async_create_entry(title="", data=user_input)
            except Exception as e:
                _LOGGER.error(f"Error in options flow init step: {e}")
                errors["base"] = "unknown"

        try:
            defaults = get_default_values(self._options, self._data)

            # Get current display unit setting with fallback
            current_display_unit = self._options.get(
                CONF_DISPLAY_UNIT, 
                self._data.get(CONF_DISPLAY_UNIT, DISPLAY_UNIT_DECIMAL)
            )

            # Convert values to strings for the selector
            string_update_interval_options = []
            for option in UPDATE_INTERVAL_OPTIONS:
                # Ensure value is a string
                new_option = option.copy()
                if "value" in new_option and not isinstance(new_option["value"], str):
                    new_option["value"] = str(new_option["value"])
                string_update_interval_options.append(new_option)

            # Create display unit options from DISPLAY_UNITS
            display_unit_options = []
            for key, label in DISPLAY_UNITS.items():
                display_unit_options.append({"value": key, "label": label})

            # Create schema for options
            schema = {
                vol.Optional(CONF_VAT, default=defaults.get(CONF_VAT, 0) * 100): vol.All(
                    vol.Coerce(float), 
                    vol.Range(min=0, max=100),
                    msg="Enter VAT percentage (0-100)"
                ),
                vol.Optional(CONF_UPDATE_INTERVAL, default=defaults.get(CONF_UPDATE_INTERVAL, 60)): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=string_update_interval_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_DISPLAY_UNIT, default=current_display_unit): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=display_unit_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        multiple=False,
                    )
                ),
            }
            
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
                    mode=selector.SelectSelectorMode.LIST,
                    multiple=True,
                )
            )
            
            # Add description text to explain priority
            schema[vol.Optional("priority_info", default="")] = selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEXT,
                    multiline=True,
                    suffix="Priority is determined by order: first selected = highest priority",
                    readonly=True,
                )
            )

            # Add API key fields for sources that require it - use SOURCE_ENTSO_E constant
            if SOURCE_ENTSO_E in self._supported_sources:
                schema[vol.Optional(
                    f"{SOURCE_ENTSO_E}_api_key",
                    default=self._data.get(f"{SOURCE_ENTSO_E}_api_key", "")
                )] = cv.string

            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(schema),
                errors=errors,
            )
        except Exception as e:
            _LOGGER.error(f"Failed to create options form: {e}")
            errors["base"] = "unknown"
            # Provide a fallback schema
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({
                    vol.Optional(CONF_VAT, default=0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                    vol.Optional(CONF_UPDATE_INTERVAL, default=60): vol.Coerce(int),
                }),
                errors=errors,
            )
