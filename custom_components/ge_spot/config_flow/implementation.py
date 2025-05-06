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
    get_stromligning_config_schema,  # Import new schema
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
        self._requires_api_key = False  # Track if API key is needed
        self._requires_stromligning_config = False  # Track if Stromligning config is needed

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
                        # Ensure display_unit is explicitly saved
                        self._data[key] = value

                # Log the display unit being saved
                _LOGGER.debug(f"Saving display_unit: {self._data.get(Config.DISPLAY_UNIT)}")

                selected_sources = self._data.get(Config.SOURCE_PRIORITY, [])

                # Check if ENTSOE requires an API key for this area
                self._requires_api_key = (
                    Source.ENTSOE in selected_sources and
                    self._data.get(Config.AREA) in AreaMapping.ENTSOE_MAPPING
                )

                # Check if Stromligning requires config
                self._requires_stromligning_config = Source.STROMLIGNING in selected_sources

                # Determine next step
                if self._requires_api_key:
                    return await self.async_step_api_keys()
                elif self._requires_stromligning_config:
                    return await self.async_step_stromligning_config()
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
                else:
                    # Handle case where key is required but not provided (shouldn't happen with schema, but good practice)
                    self._errors[f"{Source.ENTSOE}_api_key"] = "api_key_required"
                    return await self._show_api_keys_form()

                # Check if Stromligning config is needed next
                if self._requires_stromligning_config:
                    return await self.async_step_stromligning_config()
                else:
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

    async def async_step_stromligning_config(self, user_input=None) -> FlowResult:
        """Handle Stromligning supplier ID entry."""
        self._errors = {}

        if user_input is not None:
            try:
                supplier_id = user_input.get(Config.CONF_STROMLIGNING_SUPPLIER)
                if supplier_id:
                    self._data[Config.CONF_STROMLIGNING_SUPPLIER] = supplier_id
                    return self._create_entry()
                else:
                    # Handle case where supplier ID is required but not provided
                    self._errors[Config.CONF_STROMLIGNING_SUPPLIER] = "supplier_id_required"
                    return await self._show_stromligning_config_form()

            except Exception as e:
                _LOGGER.error(f"Error in async_step_stromligning_config: {e}")
                self._errors["base"] = "unknown"

        return await self._show_stromligning_config_form()

    async def _show_stromligning_config_form(self):
        """Show the Stromligning config form."""
        return self.async_show_form(
            step_id="stromligning_config",
            data_schema=get_stromligning_config_schema(),
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
        # Display unit is now required in schema
        if Config.TIMEZONE_REFERENCE not in self._data:
            self._data[Config.TIMEZONE_REFERENCE] = Defaults.TIMEZONE_REFERENCE

        # Ensure that any supplier_id settings are properly saved
        # This is crucial for Stromligning operation
        if self._requires_stromligning_config and Config.CONF_STROMLIGNING_SUPPLIER in self._data:
            _LOGGER.debug(f"Saving Stromligning supplier ID: {self._data[Config.CONF_STROMLIGNING_SUPPLIER]}")
        else:
            _LOGGER.debug(f"No Stromligning supplier needed or provided")

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
