"""Base classes for config flow."""
import logging
from typing import Dict, Any, Optional

from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from ..const import (
    DOMAIN,
    CONF_AREA,
    CONF_VAT,
    CONF_API_KEY,
    SOURCE_ENTSO_E,
)
from ..api import get_sources_for_region, create_api
from .utils import get_deduplicated_regions
from .schemas import get_user_schema, get_source_priority_schema, get_api_keys_schema
from .validators import validate_entso_e_api_key, get_entso_e_api_key_description

_LOGGER = logging.getLogger(__name__)

class GSpotConfigFlowBase:
    """Base class for GE-Spot config flows."""

    def __init__(self):
        """Initialize the base config flow."""
        self._data = {}
        self._supported_sources = []
        self._errors = {}

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle a flow initialized by the user."""
        self._errors = {}

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
                    self._errors[CONF_AREA] = "error_sources_for_region"
                    self._supported_sources = []

                if not self._supported_sources and not self._errors:
                    self._errors[CONF_AREA] = "no_sources_for_region"
                else:
                    # Check for duplicate entries
                    await self.async_set_unique_id(f"gespot_{area}")
                    self._abort_if_unique_id_configured()
                    # Proceed to source priority step
                    return await self.async_step_source_priority()
            except Exception as e:
                _LOGGER.error(f"Unexpected error in async_step_user: {e}")
                self._errors["base"] = "unknown"

        try:
            # Get regions with at least one source, properly deduplicated
            available_regions = get_deduplicated_regions()

            # Show region selection form
            return self.async_show_form(
                step_id="user",
                data_schema=get_user_schema(available_regions),
                errors=self._errors,
            )
        except Exception as e:
            _LOGGER.error(f"Failed to create form: {e}")
            self._errors["base"] = "unknown"
            # Provide a fallback form if we can't create the proper one
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({vol.Required(CONF_AREA): str}),
                errors=self._errors,
            )

    async def async_step_source_priority(self, user_input=None) -> FlowResult:
        """Handle setting source priorities."""
        self._errors = {}

        if user_input is not None:
            try:
                # Convert VAT from percentage to decimal if present
                if CONF_VAT in user_input:
                    user_input[CONF_VAT] = user_input[CONF_VAT] / 100

                # Store configurations
                for key in user_input:
                    if key != "priority_info":  # Skip the info text field
                        self._data[key] = user_input[key]

                # Check if ENTSO-E requires an API key for this area
                area = self._data.get(CONF_AREA)
                requires_api_key = False
                if SOURCE_ENTSO_E in self._data.get("source_priority", []):
                    # Always go to API keys step when ENTSO-E is selected
                    requires_api_key = True

                if requires_api_key:
                    return await self.async_step_api_keys()
                else:
                    # Complete setup
                    return self._create_entry()
            except Exception as e:
                _LOGGER.error(f"Error in async_step_source_priority: {e}")
                self._errors["base"] = "unknown"

        # Show source priority form
        return self.async_show_form(
            step_id="source_priority",
            data_schema=get_source_priority_schema(self._supported_sources),
            errors=self._errors,
        )

    async def async_step_api_keys(self, user_input=None) -> FlowResult:
        """Handle API key entry for sources that require it."""
        self._errors = {}

        if user_input is not None:
            try:
                # Store API keys in data
                for source, api_key in user_input.items():
                    if source == f"{SOURCE_ENTSO_E}_api_key" and api_key:
                        # Validate the ENTSO-E API key if provided
                        _LOGGER.debug(f"Validating ENTSO-E API key: {api_key[:5]}...")

                        valid_key = await validate_entso_e_api_key(
                            api_key,
                            self._data.get(CONF_AREA),
                            None  # No existing session
                        )

                        if valid_key:
                            # Store the API key in correct format
                            self._data[CONF_API_KEY] = api_key
                        else:
                            self._errors[f"{SOURCE_ENTSO_E}_api_key"] = "invalid_api_key"

                # If no errors, proceed with config entry creation
                if not self._errors:
                    return self._create_entry()
            except Exception as e:
                _LOGGER.error(f"Error in async_step_api_keys: {e}")
                self._errors["base"] = "unknown"

        # Get description for API key entry
        area = self._data.get(CONF_AREA)
        description = get_entso_e_api_key_description(area)

        # Show API key form
        return self.async_show_form(
            step_id="api_keys",
            data_schema=get_api_keys_schema(area),
            errors=self._errors,
            description_placeholders={"description": description}
        )

    def _create_entry(self) -> FlowResult:
        """Create the config entry."""
        # Get region name for entry title
        area = self._data.get(CONF_AREA)
        region_name = self._get_region_name(area)

        return self.async_create_entry(
            title=f"GE-Spot - {region_name}",
            data=self._data,
        )

    def _get_region_name(self, region_code):
        """Get display name for a region code."""
        from .utils import SOURCE_AREA_MAPS

        region_name = None
        for source, area_dict in SOURCE_AREA_MAPS.items():
            if region_code in area_dict:
                region_name = area_dict[region_code]
                break

        return region_name or region_code
