"""API-specific constants for GE-Spot integration."""

from .areas import Area
from ..const.sources import Source
from ..const.time import TimezoneName

class EntsoE:
    """ENTSO-E API constants."""
    DOCUMENT_TYPE_DAY_AHEAD = "A44"
    BUSINESS_TYPE_DAY_AHEAD_ALLOCATION = "A62"
    BUSINESS_TYPE_DAY_AHEAD = "A44"
    NS_URN = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"
    XMLNS_NS = "ns"


class Nordpool:
    """Nordpool API constants."""
    DEFAULT_AREA = Area.NO1
    MARKET_DAYAHEAD = "DayAhead"


class Omie:
    """OMIE API constants."""
    DEFAULT_AREA = Area.ES
    PRICE_FIELD_ES = "Precio marginal en el sistema español (EUR/MWh)"
    PRICE_FIELD_PT = "Precio marginal en el sistema portugués (EUR/MWh)"


class Stromligning:
    """Stromligning API constants."""
    DEFAULT_AREA = Area.DK1
    DEFAULT_CURRENCY = "DKK"

    class PriceComponents:
        """Price component keys."""
        ELECTRICITY = "electricity"
        GRID = "grid"
        TAX = "tax"


class Aemo:
    """AEMO API constants."""
    # AEMO regions
    REGIONS = ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]

    # AEMO API endpoints - Now consolidated into a single endpoint
    SUMMARY_URL = "https://visualisations.aemo.com.au/aemo/apps/api/report/ELEC_NEM_SUMMARY"

    # AEMO data fields
    PRICE_FIELD = "PRICE"
    REGION_FIELD = "REGIONID"
    SETTLEMENT_DATE_FIELD = "SETTLEMENTDATE"
    DATETIME_FIELD = "DATETIME"
    RRP_FIELD = "RRP"

    # AEMO data array names
    SUMMARY_ARRAY = "ELEC_NEM_SUMMARY"
    PRICES_ARRAY = "ELEC_NEM_SUMMARY_PRICES"
    MARKET_NOTICE_ARRAY = "ELEC_NEM_SUMMARY_MARKET_NOTICE"


class ECB:
    """European Central Bank API constants."""
    XML_NAMESPACE_GESMES = "http://www.gesmes.org/xml/2002-08-01"
    XML_NAMESPACE_ECB = "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"

class ComEd:
    """ComEd API constants."""
    # API endpoints
    FIVE_MINUTE_FEED = "5minutefeed"
    CURRENT_HOUR_AVERAGE = "currenthouraverage"

    # Supported areas
    AREAS = ["5minutefeed", "currenthouraverage"]

    # Endpoint mapping
    ENDPOINTS = {
        "5minutefeed": "5minutefeed",
        "currenthouraverage": "currenthouraverage"
    }

    # Base URL
    BASE_URL = "https://hourlypricing.comed.com/api"


class SourceTimezone:
    """Source-specific timezone constants."""

    # Define exact timezones for each API source - never use None or ambiguous values
    API_TIMEZONES = {
        Source.NORDPOOL: TimezoneName.UTC,  # Nordpool timestamps are in UTC (with 'Z' suffix)
        Source.ENERGI_DATA_SERVICE: TimezoneName.EUROPE_COPENHAGEN,  # HourUTC vs HourDK shows UTC+2
        Source.ENTSOE: TimezoneName.UTC,  # Timestamps have 'Z' suffix indicating UTC
        Source.EPEX: TimezoneName.EUROPE_PARIS,  # Central European Time for EPEX market
        Source.OMIE: TimezoneName.EUROPE_MADRID,  # Spanish market uses local time
        Source.AEMO: TimezoneName.AUSTRALIA_SYDNEY,  # Australian east coast market timezone
        Source.STROMLIGNING: TimezoneName.EUROPE_COPENHAGEN,  # Danish service, uses consistent local time
        Source.COMED: TimezoneName.AMERICA_CHICAGO  # ComEd uses Chicago time
    }

    # Define API-specific datetime formats for parsing if needed
    API_FORMATS = {
        Source.NORDPOOL: "%Y-%m-%dT%H:%M:%S.%fZ",  # ISO format with milliseconds and Z suffix
        Source.ENERGI_DATA_SERVICE: "%Y-%m-%dT%H:%M:%S",  # ISO format without timezone
        Source.ENTSOE: "%Y%m%d%H%M",  # ENTSOE numeric format
        Source.EPEX: "%Y-%m-%d %H:%M:%S",  # Standard datetime format
        Source.OMIE: "%d/%m/%Y %H:%M:%S",  # European date format
        Source.AEMO: "%Y-%m-%dT%H:%M:%S",  # ISO format without timezone
        Source.STROMLIGNING: "%Y-%m-%dT%H:%M:%S.%fZ",  # ISO format with milliseconds
        Source.COMED: "%Y-%m-%dT%H:%M:%S"  # ISO format without timezone
    }


class Amber:
    """Amber Energy API constants."""
    # Default currency for Australia
    DEFAULT_CURRENCY = "AUD"
    
    # Amber API constants
    PRICE_FIELD = "perKwh"
    TIMESTAMP_FIELD = "date"
    
    # Australian regions
    REGIONS = ["NSW", "QLD", "SA", "TAS", "VIC"]
