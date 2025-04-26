"""Currency conversion utilities."""
import logging
from typing import Any, Dict, Optional, Tuple

from ..const.currencies import Currency
from ..const.energy import EnergyUnit
from ..const.defaults import Defaults
from ..const.config import Config
from .exchange_service import ExchangeRateService
from .unit_conversion import convert_energy_price, get_display_unit_multiplier # Corrected import path again

_LOGGER = logging.getLogger(__name__)

class CurrencyConverter:
    """Handles currency conversion, unit conversion, and VAT application."""

    def __init__(
        self,
        exchange_service: ExchangeRateService,
        target_currency: str,
        display_unit: str, # e.g., 'kWh' or 'MWh' or 'cents'
        include_vat: bool,
        vat_rate: float # VAT rate as a decimal (e.g., 0.25 for 25%)
    ):
        """Initialize the CurrencyConverter."""
        self._exchange_service = exchange_service
        self.target_currency = target_currency
        self.display_unit = display_unit
        self.include_vat = include_vat
        self.vat_rate = vat_rate
        self.use_subunit = display_unit == Defaults.CURRENCY_SUBUNIT # Check if using cents/øre

    async def convert_hourly_prices(
        self,
        hourly_prices: Dict[str, float], # Prices in source currency/unit
        source_currency: str,
        # Use EnergyUnit.MWH instead of EnergyUnit.MEGA_WATT_HOUR
        source_unit: str = EnergyUnit.MWH # Assume MWh default if not specified
    ) -> Tuple[Dict[str, float], Optional[float], Optional[str]]:
        """Converts a dictionary of hourly prices to the target currency and display unit.

        Args:
            hourly_prices: Dict of {'HH:00': price} in source currency/unit.
            source_currency: The currency code of the source prices (e.g., 'EUR').
            source_unit: The energy unit of the source prices (e.g., 'MWh').

        Returns:
            A tuple containing:
            - Dictionary of converted hourly prices {'HH:00': converted_price}.
            - The exchange rate used (or None if no conversion needed).
            - The timestamp of the exchange rate used.
        """
        if not hourly_prices:
            return {}, None, None

        _LOGGER.debug(
            "Converting %d prices from %s/%s to %s/%s (VAT included: %s, Rate: %.2f%%)",
            len(hourly_prices),
            source_currency,
            source_unit,
            self.target_currency,
            self.display_unit,
            self.include_vat,
            self.vat_rate * 100
        )

        converted_prices = {}
        exchange_rate = None
        rate_timestamp = None

        # Determine if currency conversion is needed
        needs_currency_conversion = source_currency != self.target_currency

        if needs_currency_conversion:
            try:
                # Get the exchange rate (Source -> Target)
                # The exchange service might need adjustment if it only handles EUR base
                # Assuming get_rate can handle Source -> Target or uses EUR as intermediary
                rate_info = await self._exchange_service.get_rate(source_currency, self.target_currency)
                if rate_info:
                    exchange_rate = rate_info["rate"]
                    rate_timestamp = rate_info["timestamp"]
                    _LOGGER.debug("Using exchange rate %s -> %s: %.6f (Updated: %s)",
                                  source_currency, self.target_currency, exchange_rate, rate_timestamp)
                else:
                    _LOGGER.error("Could not retrieve exchange rate for %s -> %s. Cannot convert currency.",
                                  source_currency, self.target_currency)
                    # Return original prices or empty? Let's return empty for now to signal failure.
                    return {}, None, None
            except Exception as e:
                _LOGGER.error("Error getting exchange rate: %s", e, exc_info=True)
                return {}, None, None
        else:
            _LOGGER.debug("Source and target currency (%s) are the same. No exchange rate needed.", source_currency)


        # Determine target unit and multiplier for display (e.g., kWh or cents/kWh)
        target_unit_of_measurement = EnergyUnit.KWH # Default target unit
        # Multiplier to potentially convert to cents/øre if requested
        subunit_multiplier = get_display_unit_multiplier(self.target_currency) if self.use_subunit else 1

        for hour_key, price in hourly_prices.items():
            if price is None:
                converted_prices[hour_key] = None
                continue

            try:
                # Use a central conversion function (assumed to exist in utils.unit_conversion)
                converted_price = convert_energy_price(
                    price=price,
                    source_unit=source_unit,
                    target_unit=target_unit_of_measurement,
                    exchange_rate=exchange_rate, # Pass rate if conversion needed
                    vat_rate=self.vat_rate if self.include_vat else 0.0,
                    subunit_multiplier=subunit_multiplier # Apply cents/øre multiplier
                )
                converted_prices[hour_key] = converted_price

            except Exception as e:
                _LOGGER.error("Error converting price for hour %s (Value: %s): %s", hour_key, price, e, exc_info=True)
                converted_prices[hour_key] = None # Mark as None on conversion error

        _LOGGER.debug("Conversion complete. Example converted price for first hour: %s",
                      next(iter(converted_prices.items())) if converted_prices else "N/A")

        return converted_prices, exchange_rate, rate_timestamp

# Example Usage (in DataProcessor):
# currency_converter = CurrencyConverter(
#     exchange_service=self._exchange_service,
#     target_currency=self.target_currency,
#     display_unit=self.display_unit,
#     include_vat=self.include_vat,
#     vat_rate=self.vat_rate
# )
# converted_prices, rate, rate_ts = await currency_converter.convert_hourly_prices(
#     normalized_prices, # Prices after TZ normalization, still in source currency/unit
#     source_currency=raw_data.get("currency"), # Get source currency from raw data
#     source_unit=raw_data.get("unit", EnergyUnit.MWH) # Get source unit
# )
# result["hourly_prices"] = converted_prices
# result["ecb_rate"] = rate
# result["ecb_updated"] = rate_ts
