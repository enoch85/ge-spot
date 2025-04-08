"""API-specific constants for GE-Spot integration."""

class EntsoE:
    """ENTSO-E API constants."""
    DOCUMENT_TYPE_DAY_AHEAD = "A44"
    BUSINESS_TYPE_DAY_AHEAD_ALLOCATION = "A62"
    BUSINESS_TYPE_DAY_AHEAD = "A44"
    NS_URN = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"
    XMLNS_NS = "ns"

class Nordpool:
    """Nordpool API constants."""
    DEFAULT_AREA = "Oslo"
    MARKET_DAYAHEAD = "DayAhead"

class Omie:
    """OMIE API constants."""
    DEFAULT_AREA = "ES"
    PRICE_FIELD_ES = "Precio marginal en el sistema español (EUR/MWh)"
    PRICE_FIELD_PT = "Precio marginal en el sistema portugués (EUR/MWh)"
    URL_TEMPLATE = "https://www.omie.es/sites/default/files/dados/AGNO_{year}/MES_{month}/TXT/INT_PBC_EV_H_1_{day}_{month}_{year}_{day}_{month}_{year}.TXT"

class Stromligning:
    """Stromligning API constants."""
    DEFAULT_AREA = "DK1"
    DEFAULT_CURRENCY = "DKK"
    
    class PriceComponents:
        """Price component keys."""
        ELECTRICITY = "electricity"
        GRID = "grid"
        TAX = "tax"

class ECB:
    """European Central Bank API constants."""
    XML_NAMESPACE_GESMES = "http://www.gesmes.org/xml/2002-08-01"
    XML_NAMESPACE_ECB = "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"
