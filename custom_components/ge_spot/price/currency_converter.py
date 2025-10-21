"""Currency conversion utilities."""

import logging
from typing import Any, Dict, Optional, Tuple

from ..const.currencies import Currency
from ..const.energy import EnergyUnit
from ..const.defaults import Defaults
from ..const.config import Config
from ..const.display import DisplayUnit
from ..utils.exchange_service import ExchangeRateService
from ..utils.unit_conversion import convert_energy_price, get_display_unit_multiplier

_LOGGER = logging.getLogger(__name__)


class CurrencyConverter:
    """Handles currency conversion, unit conversion, and VAT application."""

    def __init__(
        self,
        exchange_service: ExchangeRateService,
        target_currency: str,
        display_unit: str,  # e.g. 'kWh' or 'MWh' or 'cents'
        include_vat: bool,
        vat_rate: float,  # VAT rate as a decimal (e.g. 0.25 for 25%)
        additional_tariff: float = 0.0,  # Additional tariff/fees per kWh
        energy_tax: float = 0.0,  # Fixed energy tax per kWh
    ):
        """Initialize the CurrencyConverter."""
        self._exchange_service = exchange_service
        self.target_currency = target_currency
        self.display_unit = display_unit
        self.include_vat = include_vat
        self.vat_rate = vat_rate
        self.additional_tariff = additional_tariff
        self.energy_tax = energy_tax
        # Use cents display format when explicitly set to DisplayUnit.CENTS
        self.use_subunit = display_unit == DisplayUnit.CENTS
        _LOGGER.debug(
            "CurrencyConverter initialized with display_unit=%s, use_subunit=%s",
            display_unit,
            self.use_subunit,
        )

    async def convert_interval_prices(
        self,
        interval_prices: Dict[str, float],  # Prices in source currency/unit
        source_currency: str,
        source_unit: str = EnergyUnit.MWH,  # Assume MWh default if not specified
    ) -> Tuple[Dict[str, float], Optional[float], Optional[str]]:
        """Converts a dictionary of interval prices to the target currency and display unit.

        Args:
            interval_prices: Dict of {'HH:MM': price} in source currency/unit.
            source_currency: The currency code of the source prices (e.g. 'EUR').
            source_unit: The energy unit of the source prices (e.g. 'MWh').

        Returns:
            A tuple containing:
            - Dictionary of converted interval prices {'HH:MM': converted_price}.
            - The exchange rate used (or None if no conversion needed).
            - The timestamp of the exchange rate used.
        """
        if not interval_prices:
            return {}, None, None

        _LOGGER.debug(
            "Converting %d prices from %s/%s to %s/%s (VAT included: %s, Rate: %.2f%%, Additional tariff: %.4f, Energy tax: %.4f, Use Subunit/Cents: %s)",
            len(interval_prices),
            source_currency,
            source_unit,
            self.target_currency,
            f"{'cents' if self.use_subunit else 'units'} per {EnergyUnit.KWH}",  # Clarify target unit
            self.include_vat,
            self.vat_rate * 100,
            self.additional_tariff,
            self.energy_tax,
            self.use_subunit,
        )

        converted_prices = {}
        exchange_rate = None
        rate_timestamp = None

        # Determine if currency conversion is needed
        needs_currency_conversion = source_currency != self.target_currency

        if needs_currency_conversion:
            try:
                # Initialize rates if needed
                rates = await self._exchange_service.get_rates()

                # Ensure both currencies exist in the rates dictionary
                if source_currency in rates and self.target_currency in rates:
                    # Calculate the exchange rate (source to target)
                    # ECB rates are EUR-based: 1 EUR = X Currency
                    # So we calculate: source_amount * (target_rate / source_rate)
                    source_rate = rates[source_currency]
                    target_rate = rates[self.target_currency]
                    exchange_rate = target_rate / source_rate

                    _LOGGER.debug(
                        "Using exchange rate %s -> %s: %.6f",
                        source_currency,
                        self.target_currency,
                        exchange_rate,
                    )

                    # Use current timestamp for rate information
                    rate_timestamp = self._exchange_service.last_update
                else:
                    _LOGGER.error(
                        "Could not retrieve exchange rate for %s -> %s. Cannot convert currency.",
                        source_currency,
                        self.target_currency,
                    )
                    return {}, None, None
            except Exception as e:
                _LOGGER.error("Error getting exchange rate: %s", e, exc_info=True)
                return {}, None, None
        else:
            _LOGGER.debug(
                "Source and target currency (%s) are the same. No exchange rate needed.",
                source_currency,
            )

        # Determine display unit multiplier (e.g. cents/øre if requested)
        display_unit_multiplier = (
            get_display_unit_multiplier(self.display_unit) if self.use_subunit else 1
        )

        for interval_key, price in interval_prices.items():
            if price is None:
                converted_prices[interval_key] = None
                continue

            try:
                # Handle price if it's a dictionary (e.g. {'price': 8.06})
                if isinstance(price, dict) and "price" in price:
                    price = price["price"]

                # Apply currency conversion if needed
                converted_value = price
                if needs_currency_conversion and exchange_rate is not None:
                    converted_value = price * exchange_rate

                # Use a central conversion function to handle unit conversion and VAT
                converted_price = convert_energy_price(
                    price=converted_value,
                    source_unit=source_unit,
                    target_unit=EnergyUnit.KWH,
                    vat_rate=self.vat_rate if self.include_vat else 0.0,
                    display_unit_multiplier=display_unit_multiplier,
                    additional_tariff=self.additional_tariff,
                    energy_tax=self.energy_tax,
                    tariff_in_subunit=self.use_subunit,  # Tariff matches display format
                )
                converted_prices[interval_key] = converted_price

            except Exception as e:
                _LOGGER.error(
                    "Error converting price for interval %s (Value: %s): %s",
                    interval_key,
                    price,
                    e,
                    exc_info=True,
                )
                converted_prices[interval_key] = None  # Mark as None on conversion error

        _LOGGER.debug(
            "Conversion complete. Example converted price for first interval: %s",
            next(iter(converted_prices.items())) if converted_prices else "N/A",
        )

        return converted_prices, exchange_rate, rate_timestamp
