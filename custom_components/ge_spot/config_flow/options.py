"""Options flow for GE-Spot integration."""
import logging
from typing import Dict, Any, Optional

from homeassistant.config_entries import OptionsFlow, ConfigEntry
import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult

from ..const import (
    CONF_AREA,
    CONF_VAT,
    CONF_UPDATE_INTERVAL,
    CONF_DISPLAY_UNIT,
    CONF_API_KEY,
    CONF_SOURCE_PRIORITY,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_DISPLAY_UNIT,
    DEFAULT_VAT,
    SOURCE_ENTSO_E,
)
from ..api import get_sources_for_region, create_api
from .schemas import get_options_schema, get_default_values
from .validators import validate_entso_e_api_key

_LOGGER = logging.getLogger(__name__)

class GSpotOptionsFlow(OptionsFlow):
    """Handle GE-Spot options."""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize options flow."""
        self.entry_id = config_entry.entry_id
        self._data = dict(config_entry.data)
        self._options = dict(config_entry.options)
        self._area = self._data.get(CONF_AREA)
        self._errors = {}

        try:
            self._supported_sources = get_sources_for_region(self._area) if self._area else []
        except Exception as e:
            _LOGGER.error(f"Error getting sources for {self._area}: {e}")
            self._supported_sources = []

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options."""
        self._errors = {}

        if user_input is not None:
            try:
                # Handle API key updates if present
                if f"{SOURCE_ENTSO_E}_api_key" in user_input and user_input[f"{SOURCE_ENTSO_E}_api_key"]:
                    # Validate and store API key
                    api_key = user_input[f"{SOURCE_ENTSO_E}_api_key"]
                    valid_key = True

                    # Only validate if key has changed
                    if api_key != self._data.get(CONF_API_KEY, ""):
                        _LOGGER.debug(f"Validating updated ENTSO-E API key")

                        valid_key = await validate_entso_e_api_key(
                            api_key,
                            self._area,
                            None  # No existing session
                        )

                        if valid_key:
                            # Update the stored data with the new API key
                            updated_data = dict(self._data)
                            updated_data[CONF_API_KEY] = api_key
                            # Update the config entry data
                            self.hass.config_entries.async_update_entry(
                                self.hass.config_entries.async_get_entry(self.entry_id),
                                data=updated_data
                            )
                        else:
                            self._errors[f"{SOURCE_ENTSO_E}_api_key"] = "invalid_api_key"

                    # Remove the API key field from options to avoid duplication
                    if valid_key and f"{SOURCE_ENTSO_E}_api_key" in user_input:
                        user_input.pop(f"{SOURCE_ENTSO_E}_api_key")

                # Convert VAT from percentage to decimal if present
                if CONF_VAT in user_input:
                    user_input[CONF_VAT] = user_input[CONF_VAT] / 100

                # Handle source priority updates if present
                if CONF_SOURCE_PRIORITY in user_input:
                    updated_data = dict(self._data)
                    updated_data[CONF_SOURCE_PRIORITY] = user_input[CONF_SOURCE_PRIORITY]
                    self.hass.config_entries.async_update_entry(
                        self.hass.config_entries.async_get_entry(self.entry_id),
                        data=updated_data
                    )
                    # Remove it from options to avoid duplication
                    user_input.pop(CONF_SOURCE_PRIORITY)

                # Remove non-option fields
                if "priority_info" in user_input:
                    user_input.pop("priority_info")

                # If no errors, create the options entry
                if not self._errors:
                    return self.async_create_entry(title="", data=user_input)
            except Exception as e:
                _LOGGER.error(f"Error in options flow init step: {e}")
                self._errors["base"] = "unknown"

        try:
            # Get default values from existing data
            defaults = get_default_values(self._options, self._data)

            # Build schema for options form
            schema = get_options_schema(defaults, self._supported_sources)

            # Show options form
            return self.async_show_form(
                step_id="init",
                data_schema=schema,
                errors=self._errors,
            )
        except Exception as e:
            _LOGGER.error(f"Failed to create options form: {e}")
            self._errors["base"] = "unknown"

            # Provide a fallback schema
            return self.async_show_form(
                step_id="init",
                data_schema=cv.Schema({
                    cv.Optional(CONF_VAT, default=0): cv.All(cv.Coerce(float), cv.Range(min=0, max=100)),
                    cv.Optional(CONF_UPDATE_INTERVAL, default=60): cv.Coerce(int),
                }),
                errors=self._errors,
            )
