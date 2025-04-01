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
    DISPLAY_UNITS,
    NORDPOOL_AREAS,
    ENERGI_DATA_AREAS,
    ENTSOE_AREAS,
    EPEX_AREAS,
    OMIE_AREAS,
    AEMO_AREAS,
)

_LOGGER = logging.getLogger(__name__)

class GSpotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Energy Prices integration."""

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
            
            # Set default title based on the source
            title = f"Energy Prices ({source.title()})"
            
            # Check for duplicate entries
            await self.async_set_unique_id(f"{source}_{user_input.get(CONF_AREA, '')}")
            self._abort_if_unique_id_configured()

            # Proceed to next step which is specific to the selected source
            return await getattr(self, f"async_step_{source}")(user_input)

        # Show source selection form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SOURCE): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": src, "label": src.replace("_", " ").title()} 
                                for src in SOURCES
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    def _common_schema(self, defaults):
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
        }

    async def async_step_energi_data_service(self, user_input):
        """Handle Energi Data Service configuration."""
        errors = {}

        if user_input is not None and CONF_AREA in user_input:
            # Update the stored data with area and other configs
            data = {**self._data, **user_input}
            _LOGGER.debug(f"Creating entry with data: {data}")
            
            # Save the config
            return self.async_create_entry(
                title=f"Energi Data Service - {ENERGI_DATA_AREAS[user_input[CONF_AREA]]}",
                data=data,
            )

        # Show area selection form
        schema_dict = {
            vol.Required(CONF_AREA, default="DK1"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": area, "label": name}
                        for area, name in ENERGI_DATA_AREAS.items()
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
        # Add common options
        schema_dict.update(self._common_schema({}))
        
        return self.async_show_form(
            step_id="energi_data_service",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_nordpool(self, user_input):
        """Handle Nordpool configuration."""
        errors = {}

        if user_input is not None and CONF_AREA in user_input:
            # Update the stored data with area and other configs
            data = {**self._data, **user_input}
            _LOGGER.debug(f"Creating entry with data: {data}")
            
            # Save the config
            return self.async_create_entry(
                title=f"Nordpool - {NORDPOOL_AREAS[user_input[CONF_AREA]]}",
                data=data,
            )

        # Show area selection form
        schema_dict = {
            vol.Required(CONF_AREA, default="Oslo"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": area, "label": name}
                        for area, name in NORDPOOL_AREAS.items()
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
        # Add common options
        schema_dict.update(self._common_schema({}))
        
        return self.async_show_form(
            step_id="nordpool",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_entso_e(self, user_input):
        """Handle ENTSO-E configuration."""
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
                    title=f"ENTSO-E - {ENTSOE_AREAS[user_input[CONF_AREA]]}",
                    data=data,
                )

        # Show area selection form
        schema_dict = {
            vol.Required(CONF_AREA, default="10YDK-1--------W"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": area, "label": name}
                        for area, name in ENTSOE_AREAS.items()
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required("api_key"): cv.string,
        }
        # Add common options
        schema_dict.update(self._common_schema({}))
        
        return self.async_show_form(
            step_id="entso_e",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_epex(self, user_input):
        """Handle EPEX configuration."""
        errors = {}

        if user_input is not None and CONF_AREA in user_input:
            # Update the stored data with area and other configs
            data = {**self._data, **user_input}
            _LOGGER.debug(f"Creating entry with data: {data}")
            
            # Save the config
            return self.async_create_entry(
                title=f"EPEX - {EPEX_AREAS[user_input[CONF_AREA]]}",
                data=data,
            )

        # Show area selection form
        schema_dict = {
            vol.Required(CONF_AREA, default="DE-LU"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": area, "label": name}
                        for area, name in EPEX_AREAS.items()
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
        # Add common options
        schema_dict.update(self._common_schema({}))
        
        return self.async_show_form(
            step_id="epex",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_omie(self, user_input):
        """Handle OMIE configuration."""
        errors = {}

        if user_input is not None and CONF_AREA in user_input:
            # Update the stored data with area and other configs
            data = {**self._data, **user_input}
            _LOGGER.debug(f"Creating entry with data: {data}")
            
            # Save the config
            return self.async_create_entry(
                title=f"OMIE - {OMIE_AREAS[user_input[CONF_AREA]]}",
                data=data,
            )

        # Show area selection form
        schema_dict = {
            vol.Required(CONF_AREA, default="ES"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": area, "label": name}
                        for area, name in OMIE_AREAS.items()
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
        # Add common options
        schema_dict.update(self._common_schema({}))
        
        return self.async_show_form(
            step_id="omie",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_aemo(self, user_input):
        """Handle AEMO configuration."""
        errors = {}

        if user_input is not None and CONF_AREA in user_input:
            # Update the stored data with area and other configs
            data = {**self._data, **user_input}
            _LOGGER.debug(f"Creating entry with data: {data}")
            
            # Save the config
            return self.async_create_entry(
                title=f"AEMO - {AEMO_AREAS[user_input[CONF_AREA]]}",
                data=data,
            )

        # Show area selection form
        schema_dict = {
            vol.Required(CONF_AREA, default="NSW1"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": area, "label": name}
                        for area, name in AEMO_AREAS.items()
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
        # Add common options
        schema_dict.update(self._common_schema({}))
        
        return self.async_show_form(
            step_id="aemo",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )


class GSpotOptionsFlow(config_entries.OptionsFlow):
    """Handle Energy Prices options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        super().__init__(config_entry)

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}
        
        if user_input is not None:
            # Update options
            return self.async_create_entry(title="", data=user_input)

        # Get the source from config data
        source = self.config_entry.data.get(CONF_SOURCE)
        
        # Common options for all sources
        schema = {
            vol.Optional(
                CONF_VAT, 
                default=self.config_entry.options.get(CONF_VAT, self.config_entry.data.get(CONF_VAT, DEFAULT_VAT))
            ): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
            vol.Optional(
                CONF_UPDATE_INTERVAL, 
                default=self.config_entry.options.get(CONF_UPDATE_INTERVAL, self.config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
            ): vol.All(vol.Coerce(int), vol.Range(min=15, max=1440)),
            vol.Optional(
                CONF_DISPLAY_UNIT,
                default=self.config_entry.options.get(CONF_DISPLAY_UNIT, self.config_entry.data.get(CONF_DISPLAY_UNIT, DEFAULT_DISPLAY_UNIT))
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": key, "label": value}
                        for key, value in DISPLAY_UNITS.items()
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
        
        # Add source-specific options
        if source == SOURCE_ENTSO_E:
            schema[vol.Optional(
                "api_key", 
                default=self.config_entry.options.get("api_key", self.config_entry.data.get("api_key", ""))
            )] = cv.string
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            errors=errors,
        )
