"""Configuration constants for GE-Spot integration."""

# Configuration constants
class Config:
    """Configuration constants."""
    SOURCE = "source"
    AREA = "area"
    VAT = "vat"
    UPDATE_INTERVAL = "update_interval"
    DISPLAY_UNIT = "display_unit"
    CURRENCY = "currency"
    PRECISION = "precision"
    API_KEY = "api_key"
    PRICE_IN_CENTS = "price_in_cents"
    CACHE_TTL = "cache_ttl"
    SOURCE_PRIORITY = "source_priority"


# For backward compatibility - direct constants
CONF_SOURCE = Config.SOURCE
CONF_AREA = Config.AREA
CONF_VAT = Config.VAT
CONF_UPDATE_INTERVAL = Config.UPDATE_INTERVAL
CONF_DISPLAY_UNIT = Config.DISPLAY_UNIT
CONF_CURRENCY = Config.CURRENCY
CONF_PRECISION = Config.PRECISION
CONF_API_KEY = Config.API_KEY
CONF_PRICE_IN_CENTS = Config.PRICE_IN_CENTS
CONF_CACHE_TTL = Config.CACHE_TTL
CONF_SOURCE_PRIORITY = Config.SOURCE_PRIORITY
