"""Price conversion utilities for energy APIs."""
import logging
from typing import Optional

from ...const import (
    CONF_DISPLAY_UNIT,
    DISPLAY_UNIT_CENTS,
    CURRENCY_SUBUNIT_NAMES,
)
from ...utils.currency_utils import async_convert_energy_price

_LOGGER = logging.getLogger(__name__)

class PriceConverter:
    """Handles price conversion consistently across API implementations."""

    def __init__(self, api_instance):
        """Initialize the price converter.

        Args:
            api_instance: The API instance that owns this converter
        """
        self.api = api_instance
        self.config = api_instance.config
        self.vat = api_instance.vat
        self._currency = api_instance._currency
        self.session = api_instance.session

    async def convert_price(self, price, from_currency="EUR", from_unit="MWh", to_subunit=None, exchange_rate=None):
        """Convert price using centralized conversion logic.

        Args:
            price: The price value to convert
            from_currency: Source currency code
            from_unit: Source energy unit (MWh, kWh)
            to_subunit: Whether to convert to currency subunit (cents, öre)
                        If None, uses config setting
            exchange_rate: Optional explicit exchange rate to use

        Returns:
            The converted price value
        """
        if price is None:
            return None

        # Determine if we should convert to subunit
        use_subunit = to_subunit
        if use_subunit is None:
            # First check display_unit setting (this is the primary setting)
            if CONF_DISPLAY_UNIT in self.config:
                use_subunit = self.config[CONF_DISPLAY_UNIT] == DISPLAY_UNIT_CENTS
            # Then fall back to price_in_cents if display_unit not available
            else:
                use_subunit = self.config.get("price_in_cents", False)

        # Perform conversion using the unified utility function
        converted_price = await async_convert_energy_price(
            price=price,
            from_unit=from_unit,
            to_unit="kWh",
            from_currency=from_currency,
            to_currency=self._currency,  # Always pass the target currency
            vat=self.vat,
            to_subunit=use_subunit,
            session=self.session,
            exchange_rate=exchange_rate
        )

        _LOGGER.debug(
            f"Price conversion: {price} {from_currency}/{from_unit} → "
            f"{converted_price} {self._currency}/kWh "
            f"(VAT: {self.vat:.2%}, subunit: {use_subunit})"
        )

        return converted_price

    def get_display_format(self):
        """Get information about the current display format."""
        use_subunit = self.config.get(CONF_DISPLAY_UNIT) == DISPLAY_UNIT_CENTS

        if use_subunit:
            subunit_name = CURRENCY_SUBUNIT_NAMES.get(self._currency, "cents")
            return {
                "unit": f"{subunit_name}/kWh",
                "is_subunit": True,
                "subunit_name": subunit_name
            }
        else:
            return {
                "unit": f"{self._currency}/kWh",
                "is_subunit": False,
                "subunit_name": None
            }
