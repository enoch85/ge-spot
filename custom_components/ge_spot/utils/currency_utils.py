"""Utility functions for currency and unit conversions."""
import logging

_LOGGER = logging.getLogger(__name__)

# Map region codes to their default currencies
REGION_TO_CURRENCY = {
    # Nordics
    "SE1": "SEK",
    "SE2": "SEK",
    "SE3": "SEK",
    "SE4": "SEK",
    "DK1": "DKK",
    "DK2": "DKK",
    "FI": "EUR",
    "NO1": "NOK",
    "NO2": "NOK",
    "NO3": "NOK",
    "NO4": "NOK",
    "NO5": "NOK",
    # Baltics
    "EE": "EUR",
    "LV": "EUR",
    "LT": "EUR",
    # Central Europe
    "AT": "EUR",
    "BE": "EUR",
    "FR": "EUR",
    "DE-LU": "EUR",
    "NL": "EUR",
    # UK
    "GB": "GBP",
    # Australia
    "NSW1": "AUD",
    "QLD1": "AUD",
    "SA1": "AUD",
    "TAS1": "AUD",
    "VIC1": "AUD",
    # Additional mappings (Norwegian regions)
    "Oslo": "NOK",
    "Kr.sand": "NOK",
    "Bergen": "NOK",
    "Molde": "NOK",
    "Tr.heim": "NOK",
    "Tromsø": "NOK",
}

# Currency conversion multipliers (to convert to subunits like cents, öre)
CURRENCY_SUBUNIT_MULTIPLIER = {
    "EUR": 100,  # Euro to cents
    "SEK": 100,  # Swedish krona to öre
    "NOK": 100,  # Norwegian krone to øre
    "DKK": 100,  # Danish krone to øre
    "GBP": 100,  # Pound to pence
    "AUD": 100,  # Australian dollar to cents
}

# Currency subunit names
CURRENCY_SUBUNIT_NAMES = {
    "EUR": "cents",
    "SEK": "öre",
    "NOK": "øre",
    "DKK": "øre",
    "GBP": "pence",
    "AUD": "cents",
}

# Energy unit conversion factors (from MWh)
ENERGY_UNIT_CONVERSION = {
    "MWh": 1,
    "kWh": 1000,
    "Wh": 1000000,
}


def get_default_currency(region):
    """Get the default currency for a region."""
    return REGION_TO_CURRENCY.get(region, "EUR")


def convert_to_subunit(value, currency):
    """Convert currency value to its subunit (e.g., EUR to cents)."""
    multiplier = CURRENCY_SUBUNIT_MULTIPLIER.get(currency, 1)
    return value * multiplier


def get_subunit_name(currency):
    """Get the name of a currency's subunit."""
    return CURRENCY_SUBUNIT_NAMES.get(currency, currency)


def format_price(price, currency, use_subunit=False, precision=3):
    """Format price with the appropriate unit and precision."""
    if use_subunit:
        price = convert_to_subunit(price, currency)
        unit = get_subunit_name(currency)
        precision = max(0, precision - 2)  # Reduce precision for subunits
    else:
        unit = currency
    
    return round(price, precision), unit


def convert_energy_price(price, from_unit="MWh", to_unit="kWh", vat=0.0):
    """Convert energy price between units and apply VAT."""
    # Convert between energy units
    from_factor = ENERGY_UNIT_CONVERSION.get(from_unit, 1)
    to_factor = ENERGY_UNIT_CONVERSION.get(to_unit, 1)
    
    converted = price * from_factor / to_factor
    
    # Apply VAT
    if vat > 0:
        converted = converted * (1 + vat)
    
    return converted
