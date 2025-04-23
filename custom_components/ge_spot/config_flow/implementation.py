"""Config flow implementation for GE-Spot integration."""
import logging
import voluptuous as vol
import hashlib

from homeassistant.config_entries import ConfigFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from ..const import DOMAIN
from ..const.config import Config
from ..const.sources import Source
from ..const.currencies import Currency, CurrencyInfo
from ..const.defaults import Defaults
from ..const.areas import AreaMapping
from ..api import get_sources_for_region
from ..api import entsoe
from ..utils.exchange_service import get_exchange_service

from .utils import (
    get_deduplicated_regions,
)
from .schemas import (
    get_source_priority_schema,
    get_api_keys_schema,
    get_user_schema,
    get_default_values,
)

_LOGGER = logging.getLogger(__name__)

class GSpotConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GE-Spot integration."""

    VERSION = 1
    CONNECTION_CLASS = "cloud_poll"

    def __init__(self):
        """Initialize the config flow."""
        self._data = {}
        self._supported_sources = []
        self._errors = {}

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle a flow initialized by the user."""
        self._errors = {}

        if user_input is not None:
            try:
                # Store the area in our data
                area = user_input.get(Config.AREA)
                if not area:
                    self._errors[Config.AREA] = "no_sources_for_region"
                    return await self._show_user_form()

                self._data[Config.AREA] = area

                # Get list of sources that support this area
                try:
                    self._supported_sources = get_sources_for_region(area)
                    _LOGGER.info(f"Supported sources for {area}: {self._supported_sources}")
                except Exception as e:
                    _LOGGER.error(f"Error getting sources for {area}: {e}")
                    self._errors[Config.AREA] = "error_sources_for_region"
                    self._supported_sources = []

                if not self._supported_sources and not self._errors:
                    self._errors[Config.AREA] = "no_sources_for_region"
                    return await self._show_user_form()

                # Check for duplicate entries
                await self.async_set_unique_id(f"gespot_{area}")
                self._abort_if_unique_id_configured()

                # Set default currency based on area
                self._data[Config.CURRENCY] = CurrencyInfo.REGION_TO_CURRENCY.get(area, Currency.EUR)

                # Proceed to source priority step
                return await self.async_step_source_priority()

            except Exception as e:
                _LOGGER.error(f"Unexpected error in async_step_user: {e}")
                self._errors["base"] = "unknown"
                return await self._show_user_form()

        return await self._show_user_form()

    async def _show_user_form(self):
        """Show the user selection form."""
        try:
            available_regions = get_deduplicated_regions()
            return self.async_show_form(
                step_id="user",
                data_schema=get_user_schema(available_regions),
                errors=self._errors,
                description_placeholders={"data_description": "data_description"}
            )
        except Exception as e:
            _LOGGER.error(f"Failed to create user form: {e}")
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({vol.Required(Config.AREA): str}),
                errors=self._errors,
                description_placeholders={"data_description": "data_description"}
            )

    async def async_step_source_priority(self, user_input=None) -> FlowResult:
        """Handle setting source priorities."""
        self._errors = {}

        if user_input is not None:
            try:
                # Store configurations
                for key, value in user_input.items():
                    if key != "priority_info":
                        # Convert VAT from percentage to decimal
                        if key == Config.VAT:
                            value = value / 100
                        self._data[key] = value

                # Check if ENTSOE requires an API key for this area
                requires_api_key = (
                    Source.ENTSOE in self._data.get(Config.SOURCE_PRIORITY, []) and
                    self._data.get(Config.AREA) in AreaMapping.ENTSOE_MAPPING
                )

                if requires_api_key:
                    return await self.async_step_api_keys()
                else:
                    return self._create_entry()

            except Exception as e:
                _LOGGER.error(f"Error in async_step_source_priority: {e}")
                self._errors["base"] = "unknown"

        return self.async_show_form(
            step_id="source_priority",
            data_schema=get_source_priority_schema(self._supported_sources),
            errors=self._errors,
            description_placeholders={"data_description": "data_description"}
        )

    async def async_step_api_keys(self, user_input=None) -> FlowResult:
        """Handle API key entry for sources that require it."""
        self._errors = {}

        if user_input is not None:
            try:
                # Validate ENTSOE API key if provided
                entsoe_key = user_input.get(f"{Source.ENTSOE}_api_key")
                if entsoe_key:
                    valid_key = await entsoe.validate_api_key(
                        entsoe_key,
                        self._data.get(Config.AREA)
                    )

                    if valid_key:
                        self._data[Config.API_KEY] = entsoe_key
                    else:
                        self._errors[f"{Source.ENTSOE}_api_key"] = "invalid_api_key"
                        return await self._show_api_keys_form()

                return self._create_entry()

            except Exception as e:
                _LOGGER.error(f"Error in async_step_api_keys: {e}")
                self._errors["base"] = "unknown"

        return await self._show_api_keys_form()

    async def _show_api_keys_form(self):
        """Show the API keys form."""
        return self.async_show_form(
            step_id="api_keys",
            data_schema=get_api_keys_schema(self._data.get(Config.AREA)),
            errors=self._errors,
            description_placeholders={"data_description": "data_description"}
        )

    def _create_entry(self) -> FlowResult:
        """Create the config entry."""
        # Determine region display name
        area = self._data.get(Config.AREA)
        region_name = self._get_region_name(area)

        # Set defaults if not provided
        if Config.VAT not in self._data:
            self._data[Config.VAT] = Defaults.VAT
        if Config.UPDATE_INTERVAL not in self._data:
            self._data[Config.UPDATE_INTERVAL] = Defaults.UPDATE_INTERVAL
        if Config.DISPLAY_UNIT not in self._data:
            self._data[Config.DISPLAY_UNIT] = Defaults.DISPLAY_UNIT
        if Config.TIMEZONE_REFERENCE not in self._data:
            self._data[Config.TIMEZONE_REFERENCE] = Defaults.TIMEZONE_REFERENCE

        return self.async_create_entry(
            title=f"GE-Spot - {region_name}",
            data=self._data,
        )

    def _get_region_name(self, region_code):
        """Get display name for a region code."""
        region_name = None
        for source, area_dict in AreaMapping.ALL_AREAS.items():
            if region_code in area_dict:
                region_name = area_dict[region_code]
                break

        return region_name or region_code

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        from .options import GSpotOptionsFlow
        return GSpotOptionsFlow(config_entry)
