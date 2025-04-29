"""Currency service for GE-Spot integration."""
import logging
from typing import Dict, Any, Optional

from ..const.currencies import Currency
from ..const.areas import Timezone, AreaInfo
from ..const.api import Source
from ..const.sources import SourceInfo

_LOGGER = logging.getLogger(__name__)

# Map areas to their default currencies
AREA_DEFAULT_CURRENCIES = {
    # Nordic countries
    "DK1": Currency.DKK,
    "DK2": Currency.DKK,
    "SE1": Currency.SEK,
    "SE2": Currency.SEK,
    "SE3": Currency.SEK,
    "SE4": Currency.SEK,
    "FI": Currency.EUR,
    "NO1": Currency.NOK,
    "NO2": Currency.NOK,
    "NO3": Currency.NOK,
    "NO4": Currency.NOK,
    "NO5": Currency.NOK,
    
    # Central Europe
    "DE": Currency.EUR,
    "AT": Currency.EUR,
    "BE": Currency.EUR,
    "NL": Currency.EUR,
    "FR": Currency.EUR,
    "LU": Currency.EUR,
    "IE": Currency.EUR,
    "IT": Currency.EUR,
    "ES": Currency.EUR,
    "PT": Currency.EUR,
    "GR": Currency.EUR,
    
    # Eastern Europe
    "PL": Currency.EUR,  # Using EUR as fallback
    "CZ": Currency.EUR,  # Using EUR as fallback
    "HU": Currency.EUR,  # Using EUR as fallback
    "SK": Currency.EUR,
    "RO": Currency.EUR,  # Using EUR as fallback
    "BG": Currency.EUR,  # Using EUR as fallback
    "HR": Currency.EUR,
    "SI": Currency.EUR,
    
    # Baltics
    "EE": Currency.EUR,
    "LV": Currency.EUR,
    "LT": Currency.EUR,
    
    # United Kingdom
    "GB": Currency.GBP,
    "UK": Currency.GBP,
    
    # Australia
    "NSW1": Currency.AUD,
    "QLD1": Currency.AUD,
    "SA1": Currency.AUD,
    "TAS1": Currency.AUD,
    "VIC1": Currency.AUD,
    
    # USA
    "US": Currency.USD,
    "COMED": Currency.USD,
}

# Source to default currency mapping
SOURCE_DEFAULT_CURRENCIES = {
    Source.NORDPOOL: Currency.EUR,
    Source.ENTSOE: Currency.EUR, 
    Source.ENERGI_DATA_SERVICE: Currency.DKK,
    Source.EPEX: Currency.EUR,
    Source.OMIE: Currency.EUR,
    Source.AEMO: Currency.AUD,
    Source.COMED: Currency.USD,
    Source.STROMLIGNING: Currency.EUR,
}

def get_default_currency(area: str) -> str:
    """Get default currency for a specific area.
    
    Args:
        area: Area code
        
    Returns:
        Default currency code for the area
    """
    # First check if we have a direct mapping for this area
    if area in AREA_DEFAULT_CURRENCIES:
        return AREA_DEFAULT_CURRENCIES[area]
    
    # If not, try to get the region and infer from that
    region = AreaInfo.get_region_for_area(area)
    if region:
        # Use region-based defaults
        if "scandinavia" in region.lower() or "nordic" in region.lower():
            return Currency.EUR  # Default for Nordic/Scandinavian region
        elif "europe" in region.lower():
            return Currency.EUR  # Default for Europe
        elif "us" in region.lower() or "america" in region.lower():
            return Currency.USD  # Default for US
        elif "australia" in region.lower():
            return Currency.AUD  # Default for Australia
    
    # Get the default source for the area and use its default currency
    source = SourceInfo.get_default_source_for_area(area)
    if source and source in SOURCE_DEFAULT_CURRENCIES:
        return SOURCE_DEFAULT_CURRENCIES[source]
    
    # Default fallback
    _LOGGER.debug(f"No specific currency found for area {area}, using EUR as default")
    return Currency.EUR

def format_currency_for_display(value: float, currency: str) -> str:
    """Format currency value for display.
    
    Args:
        value: Currency value
        currency: Currency code
        
    Returns:
        Formatted currency string
    """
    # Handle special case for cents
    if currency == Currency.CENTS:
        # Display cents with 2 decimal places and no currency symbol
        return f"{value:.2f} ¢"
    
    # Get currency symbol based on the currency code
    symbol = get_currency_symbol(currency)
    
    # Format the value with 2 decimal places
    if value is None:
        return "N/A"
    
    # For most currencies, show 2 decimal places
    return f"{symbol}{value:.2f}"

def get_currency_symbol(currency: str) -> str:
    """Get symbol for a currency code.
    
    Args:
        currency: Currency code
        
    Returns:
        Currency symbol
    """
    symbols = {
        Currency.EUR: "€",
        Currency.USD: "$",
        Currency.GBP: "£",
        Currency.DKK: "kr",
        Currency.NOK: "kr",
        Currency.SEK: "kr",
        Currency.AUD: "A$",
        Currency.CENTS: "¢",
        Currency.MDL: "L",
        Currency.UAH: "₴",
        Currency.AMD: "֏",
        Currency.GEL: "₾",
        Currency.AZN: "₼",
    }
    
    return symbols.get(currency, currency)  # Return the currency code if no symbol found