"""Options flow for GE-Spot integration."""
import logging
import voluptuous as vol

from homeassistant.config_entries import OptionsFlow, ConfigEntry
from homeassistant.data_entry_flow import FlowResult

from ..const import DOMAIN
from ..const.config import Config
from ..const.sources import Source
from ..const.defaults import Defaults
from ..const.areas import AreaMapping
from ..const.time import TimezoneReference
from ..api import get_sources_for_region, create_api
from ..api import entsoe
from .schemas import (
    get_options_schema,
    get_default_values
)

_LOGGER = logging.getLogger(__name__)

class GSpotOptionsFlow(OptionsFlow):
    """Handle GE-Spot options."""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize options flow."""
        self.entry_id = config_entry.entry_id
        self._data = dict(config_entry.data)
        self._options = dict(config_entry.options)
        self._area = self._data.get(Config.AREA)
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
                # Find existing API key from this or other entries
                existing_api_key = await self._find_existing_api_key(Source.ENTSOE)

                # Handle API key updates if present
                if f"{Source.ENTSOE}_api_key" in user_input and user_input[f"{Source.ENTSOE}_api_key"]:
                    # If empty field but we have an existing key, use that
                    api_key = user_input[f"{Source.ENTSOE}_api_key"]
                    if not api_key and existing_api_key:
                        api_key = existing_api_key

                    # Only validate if key has changed
                    if api_key != self._data.get(Config.API_KEY, ""):
                        _LOGGER.debug(f"Validating updated ENTSO-E API key")

                        # Validate key directly using entsoe module
                        valid_key = await entsoe.validate_api_key(api_key, self._area)

                        if valid_key:
                            # Update the stored data with the new API key
                            updated_data = dict(self._data)
                            updated_data[Config.API_KEY] = api_key
                            # Update the config entry data
                            self.hass.config_entries.async_update_entry(
                                self.hass.config_entries.async_get_entry(self.entry_id),
                                data=updated_data
                            )
                        else:
                            self._errors[f"{Source.ENTSOE}_api_key"] = "invalid_api_key_in_options"
                            return await self._show_form()

                    # Remove the API key field from options to avoid duplication
                    if f"{Source.ENTSOE}_api_key" in user_input:
                        user_input.pop(f"{Source.ENTSOE}_api_key")

                # Convert VAT from percentage to decimal if present
                if Config.VAT in user_input:
                    user_input[Config.VAT] = user_input[Config.VAT] / 100

                # Handle source priority and timezone reference updates if present
                updated_data = None
                if Config.SOURCE_PRIORITY in user_input or Config.TIMEZONE_REFERENCE in user_input:
                    updated_data = dict(self._data)

                    if Config.SOURCE_PRIORITY in user_input:
                        updated_data[Config.SOURCE_PRIORITY] = user_input[Config.SOURCE_PRIORITY]
                        # Remove it from options to avoid duplication
                        user_input.pop(Config.SOURCE_PRIORITY)

                    if Config.TIMEZONE_REFERENCE in user_input:
                        updated_data[Config.TIMEZONE_REFERENCE] = user_input[Config.TIMEZONE_REFERENCE]
                        # Keep it in options as well since it's a valid option

                # Update the config entry data if needed
                if updated_data:
                    self.hass.config_entries.async_update_entry(
                        self.hass.config_entries.async_get_entry(self.entry_id),
                        data=updated_data
                    )

                # Remove non-option fields
                if "priority_info" in user_input:
                    user_input.pop("priority_info")

                # Handle clear cache action if present
                if "clear_cache" in user_input and user_input["clear_cache"]:
                    # Get the coordinator from hass data
                    coordinator = self.hass.data[DOMAIN].get(self.entry_id)
                    if coordinator and hasattr(coordinator, "clear_cache"):
                        try:
                            # Check if the clear_cache method is a coroutine function
                            import inspect
                            if inspect.iscoroutinefunction(coordinator.clear_cache):
                                await coordinator.clear_cache()
                            else:
                                # Call without await if it's not async
                                coordinator.clear_cache()
                                
                            self._errors["base"] = "cache_cleared"
                            return await self._show_form()
                        except Exception as e:
                            _LOGGER.error(f"Error clearing cache: {e}")
                            self._errors["base"] = "cache_clear_failed"
                            return await self._show_form()
                    else:
                        self._errors["base"] = "cache_clear_failed"
                        return await self._show_form()

                # If no errors, create the options entry
                if not self._errors:
                    # Remove action fields before saving
                    if "clear_cache" in user_input:
                        user_input.pop("clear_cache")

                    return self.async_create_entry(title="", data=user_input)
            except Exception as e:
                _LOGGER.error(f"Error in options flow init step: {e}")
                self._errors["base"] = "unknown"
                return await self._show_form()

        return await self._show_form()

    async def _show_form(self):
        """Show the options form."""
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
                description_placeholders={"data_description": "data_description"}
            )
        except Exception as e:
            _LOGGER.error(f"Failed to create options form: {e}")
            self._errors["base"] = "unknown"

            # Provide a fallback schema if needed
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({
                    vol.Optional(Config.VAT, default=0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                    vol.Optional(Config.UPDATE_INTERVAL, default=60): vol.Coerce(int),
                    vol.Optional(Config.TIMEZONE_REFERENCE, default=Defaults.TIMEZONE_REFERENCE): vol.In({
                        TimezoneReference.HOME_ASSISTANT: TimezoneReference.OPTIONS[TimezoneReference.HOME_ASSISTANT],
                        TimezoneReference.LOCAL_AREA: TimezoneReference.OPTIONS[TimezoneReference.LOCAL_AREA]
                    }),
                }),
                errors=self._errors,
                description_placeholders={"data_description": "data_description"}
            )

    async def _find_existing_api_key(self, source_type):
        """Find existing API key in this or other config entries."""
        # First check the current entry's data
        if Config.API_KEY in self._data and self._data.get(Config.API_KEY):
            return self._data.get(Config.API_KEY)

        # Then check other entries
        from ..const import DOMAIN
        existing_entries = self.hass.config_entries.async_entries(DOMAIN)
        for entry in existing_entries:
            if entry.entry_id == self.entry_id:
                continue  # Skip current entry

            if Config.API_KEY in entry.data and entry.data.get(Config.API_KEY):
                # Verify it's for the requested source type
                if source_type in entry.data.get(Config.SOURCE_PRIORITY, []):
                    return entry.data.get(Config.API_KEY)
        return None
