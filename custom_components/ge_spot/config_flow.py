"""Config flow for GE-Spot integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_SOURCE,
    CONF_AREA,
    CONF_VAT,
    CONF_UPDATE_INTERVAL,
    CONF_DISPLAY_UNIT,
    CONF_ENABLE_FALLBACK,
    SOURCES,
    SOURCE_ENERGI_DATA_SERVICE,
    SOURCE_NORDPOOL,
    SOURCE_ENTSO_E,
    SOURCE_EPEX,
    SOURCE_OMIE,
    SOURCE_AEMO,
    DEFAULT_VAT,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_DISPLAY_UNIT,
    DEFAULT_ENABLE_FALLBACK,
    DISPLAY_UNITS,
)

_LOGGER = logging.getLogger(__name__)

def _common_schema(defaults):
    """Return schema with common options."""
    return {
        vol.Optional(CONF_VAT, default=defaults.get(CONF_VAT, DEFAULT_VAT)): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=1)
        ),
        vol.Optional(CONF_UPDATE_INTERVAL, default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)): vol.All(
            vol.Coerce(int), vol.Range(min=15, max=1440)
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
        vol.Optional(CONF_ENABLE_FALLBACK, default=defaults.get(CONF_ENABLE_FALLBACK, DEFAULT_ENABLE_FALLBACK)): selector.BooleanSelector(),
    }


class GSpotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GE-Spot integration."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize the config flow."""
        self._data = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return GSpotOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            # Validate user input
            source = user_input[CONF_SOURCE]
            
            # Store the source type in our data
            self._data[CONF_SOURCE] = source
            
            _LOGGER.debug(f"Selected source: {source}")
            
            # Check for duplicate entries
            await self.async_set_unique_id(f"{source}_{user_input.get('area', '')}")
            self._abort_if_unique_id_configured()

            # Proceed to next step which is specific to the selected source
            step_method = getattr(self, f"async_step_{source}", None)
            if step_method:
                return await step_method(user_input)
            else:
                errors[CONF_SOURCE] = "unknown_source"

        # Reorder sources to put Nordpool first
        ordered_sources = [SOURCE_NORDPOOL]
        for src in SOURCES:
            if src != SOURCE_NORDPOOL:
                ordered_sources.append(src)

        # Show source selection form with Nordpool first
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SOURCE, default=SOURCE_NORDPOOL): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": src, "label": src.replace("_", " ").title()} 
                                for src in ordered_sources
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def _handle_area_config(self, user_input, source_name, areas_dict, default_area):
        """Generic handler for area configuration."""
        errors = {}

        if user_input is not None and CONF_AREA in user_input:
            # Update the stored data with area and other configs
            data = {**self._data, **user_input}
            _LOGGER.debug(f"Creating entry with data: {data}")
            
            # Save the config
            return self.async_create_entry(
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
        schema_dict.update(_common_schema({}))
        
        return self.async_show_form(
            step_id=source_name,
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def _handle_api_key_config(self, user_input, source_name, areas_dict, default_area):
        """Generic handler for API key configuration."""
        errors = {}

        if user_input is not None and CONF_AREA in user_input:
            # Validate API key
            if not user_input.get("api_key"):
                errors["api_key"] = "api_key_required"
            else:
                # Update the stored data with area and other configs
                data = {**self._data, **user_input}
                _LOGGER.debug(f"Creating entry with data: {data}")
                
                # Save the config
                return self.async_create_entry(
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
        schema_dict.update(_common_schema({}))
        
        return self.async_show_form(
            step_id=source_name,
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    # Source-specific step handlers using the generic methods
    async def async_step_energi_data_service(self, user_input):
        """Handle Energi Data Service configuration."""
        from .const import ENERGI_DATA_AREAS
        return await self._handle_area_config(user_input, "energi_data_service", ENERGI_DATA_AREAS, "DK1")

    async def async_step_nordpool(self, user_input):
        """Handle Nordpool configuration."""
        from .const import NORDPOOL_AREAS
        return await self._handle_area_config(user_input, "nordpool", NORDPOOL_AREAS, "Oslo")

    async def async_step_entsoe(self, user_input):
        """Handle ENTSO-E configuration."""
        from .const import ENTSOE_AREAS
        return await self._handle_api_key_config(user_input, "entsoe", ENTSOE_AREAS, "10YDK-1--------W")

    async def async_step_epex(self, user_input):
        """Handle EPEX configuration."""
        from .const import EPEX_AREAS
        return await self._handle_area_config(user_input, "epex", EPEX_AREAS, "DE-LU")

    async def async_step_omie(self, user_input):
        """Handle OMIE configuration."""
        from .const import OMIE_AREAS
        return await self._handle_area_config(user_input, "omie", OMIE_AREAS, "ES")

    async def async_step_aemo(self, user_input):
        """Handle AEMO configuration."""
        from .const import AEMO_AREAS
        return await self._handle_area_config(user_input, "aemo", AEMO_AREAS, "NSW1")


class GSpotOptionsFlow(config_entries.OptionsFlow):
    """Handle GE-Spot options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.entry_id = config_entry.entry_id
        self._data = dict(config_entry.data)
        self._options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}
        
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get the source from data
        source = self._data.get(CONF_SOURCE)
        
        # Common options for all sources, now including fallback option
        schema = {
            vol.Optional(
                CONF_VAT, 
                default=self._options.get(CONF_VAT, self._data.get(CONF_VAT, DEFAULT_VAT))
            ): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
            vol.Optional(
                CONF_UPDATE_INTERVAL, 
                default=self._options.get(CONF_UPDATE_INTERVAL, self._data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
            ): vol.All(vol.Coerce(int), vol.Range(min=15, max=1440)),
            vol.Optional(
                CONF_DISPLAY_UNIT,
                default=self._options.get(CONF_DISPLAY_UNIT, self._data.get(CONF_DISPLAY_UNIT, DEFAULT_DISPLAY_UNIT))
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": key, "label": value}
                        for key, value in DISPLAY_UNITS.items()
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_ENABLE_FALLBACK,
                default=self._options.get(CONF_ENABLE_FALLBACK, self._data.get(CONF_ENABLE_FALLBACK, DEFAULT_ENABLE_FALLBACK))
            ): selector.BooleanSelector(),
        }
        
        # Add source-specific options
        if source == SOURCE_ENTSO_E:
            schema[vol.Optional(
                "api_key", 
                default=self._options.get("api_key", self._data.get("api_key", ""))
            )] = cv.string
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            errors=errors,
        )
