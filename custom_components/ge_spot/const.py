"""Constants for the integration."""

DOMAIN = "ge_spot"

class Source:
    """Data source types."""
    NORDPOOL = "nordpool"
    ENERGI_DATA_SERVICE = "energi_data_service"
    ENTSO_E = "entso_e"
    EPEX = "epex"
    OMIE = "omie"
    AEMO = "aemo"
    STROMLIGNING = "stromligning"

class Config:
    """Configuration constants."""
    AREA = "area"
    CURRENCY = "currency"
    VAT = "vat"
    API_KEY = "api_key"
    UPDATE_INTERVAL = "update_interval"
    SOURCE_PRIORITY = "source_priority"
    DISPLAY_UNIT = "display_unit"
    SELECTED_SENSOR_TYPES = "selected_sensor_types"

class EntsoE:
    """ENTSO-E specific constants."""
    XMLNS_NS = "ns"
    NS_URN = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0"
    DOCUMENT_TYPE_DAY_AHEAD = "A44"
    BUSINESS_TYPE_DAY_AHEAD = "A44"
    BUSINESS_TYPE_DAY_AHEAD_ALLOCATION = "A62"

class Nordpool:
    """Nordpool specific constants."""
    MARKET_DAYAHEAD = "Elspot"
    DEFAULT_AREA = "SE3"

class Currency:
    """Currency constants."""
    EUR = "EUR"
    SEK = "SEK"
    NOK = "NOK"
    DKK = "DKK"
    GBP = "GBP"
    PLN = "PLN"
    AUD = "AUD"

class CurrencyInfo:
    """Currency information."""
    REGION_TO_CURRENCY = {
        "SE1": Currency.SEK,
        "SE2": Currency.SEK,
        "SE3": Currency.SEK,
        "SE4": Currency.SEK,
        "FI": Currency.EUR,
        "DK1": Currency.DKK,
        "DK2": Currency.DKK,
        "NO1": Currency.NOK,
        "NO2": Currency.NOK,
        "NO3": Currency.NOK,
        "NO4": Currency.NOK,
        "NO5": Currency.NOK,
        "LT": Currency.EUR,
        "LV": Currency.EUR,
        "EE": Currency.EUR,
        "AT": Currency.EUR,
        "BE": Currency.EUR,
        "DE": Currency.EUR,
        "FR": Currency.EUR,
        "NL": Currency.EUR,
        "PL": Currency.PLN,
        "UK": Currency.GBP,
        "GB": Currency.GBP,
        "IE": Currency.EUR,
        "ES": Currency.EUR,
        "PT": Currency.EUR,
        "IT": Currency.EUR,
        "CH": Currency.EUR,
        "NSW": Currency.AUD,
        "QLD": Currency.AUD,
        "SA": Currency.AUD,
        "TAS": Currency.AUD,
        "VIC": Currency.AUD,
    }

    SUBUNIT_NAMES = {
        Currency.EUR: "cents",  # Euro cent
        Currency.SEK: "öre",    # Swedish öre
        Currency.NOK: "øre",    # Norwegian øre
        Currency.DKK: "øre",    # Danish øre
        Currency.GBP: "pence",  # British pence
        Currency.PLN: "grosz",  # Polish grosz
        Currency.AUD: "cents",  # Australian cent
    }

    SUBUNIT_MULTIPLIER = {
        Currency.EUR: 100,
        Currency.SEK: 100,
        Currency.NOK: 100,
        Currency.DKK: 100,
        Currency.GBP: 100,
        Currency.PLN: 100,
        Currency.AUD: 100,
    }

class Attributes:
    """Attribute names for sensor data."""
    VAT = "vat"
    AREA = "area"
    CURRENCY = "currency"
    MIN = "min"
    MAX = "max"
    LAST_UPDATED = "last_updated"
    TODAY = "today"
    TOMORROW = "tomorrow"
    TOMORROW_VALID = "tomorrow_valid"
    DATA_SOURCE = "data_source"
    FALLBACK_USED = "fallback_used"
    IS_USING_FALLBACK = "is_using_fallback"
    AVAILABLE_FALLBACKS = "available_fallbacks"
    API_KEY_STATUS = "api_key_status"

class DisplayUnit:
    """Display unit options."""
    DECIMAL = "decimal"  # Currency/kWh (e.g., €/kWh)
    CENTS = "cents"      # Cents/kWh (e.g., ¢/kWh)

    OPTIONS = {
        DECIMAL: "Currency per kWh (e.g., €/kWh)",
        CENTS: "Cents per kWh (e.g., ¢/kWh)"
    }

class Area:
    """Area constants."""
    SE1 = "SE1"
    SE2 = "SE2"
    SE3 = "SE3"
    SE4 = "SE4"
    DK1 = "DK1"
    DK2 = "DK2"

class AreaMapping:
    """Mappings for area codes between different sources."""
    NORDPOOL_AREAS = {
        "SE1": "Sweden (SE1)",
        "SE2": "Sweden (SE2)",
        "SE3": "Sweden (SE3)",
        "SE4": "Sweden (SE4)",
        "FI": "Finland",
        "DK1": "Denmark (DK1)",
        "DK2": "Denmark (DK2)",
        "NO1": "Norway (NO1)",
        "NO2": "Norway (NO2)",
        "NO3": "Norway (NO3)",
        "NO4": "Norway (NO4)",
        "NO5": "Norway (NO5)",
        "LT": "Lithuania",
        "LV": "Latvia",
        "EE": "Estonia"
    }

    ENERGI_DATA_AREAS = {
        "DK1": "Denmark (DK1)",
        "DK2": "Denmark (DK2)"
    }

    ENTSOE_AREAS = {
        "SE1": "Sweden (SE1)",
        "SE2": "Sweden (SE2)",
        "SE3": "Sweden (SE3)",
        "SE4": "Sweden (SE4)",
        "FI": "Finland",
        "DK1": "Denmark (DK1)",
        "DK2": "Denmark (DK2)",
        "NO1": "Norway (NO1)",
        "NO2": "Norway (NO2)",
        "NO3": "Norway (NO3)",
        "NO4": "Norway (NO4)",
        "NO5": "Norway (NO5)",
        "LT": "Lithuania",
        "LV": "Latvia",
        "EE": "Estonia",
        "AT": "Austria",
        "BE": "Belgium",
        "DE": "Germany",
        "FR": "France",
        "NL": "Netherlands",
        "PL": "Poland",
        "UK": "United Kingdom",
        "GB": "Great Britain",
        "IE": "Ireland",
        "ES": "Spain",
        "PT": "Portugal",
        "IT": "Italy",
        "CH": "Switzerland"
    }

    EPEX_AREAS = {
        "AT": "Austria",
        "BE": "Belgium",
        "DE": "Germany",
        "FR": "France",
        "NL": "Netherlands"
    }

    OMIE_AREAS = {
        "ES": "Spain",
        "PT": "Portugal"
    }

    AEMO_AREAS = {
        "NSW": "New South Wales",
        "QLD": "Queensland",
        "SA": "South Australia",
        "TAS": "Tasmania",
        "VIC": "Victoria"
    }

    STROMLIGNING_AREAS = {
        "DK1": "Denmark (DK1)",
        "DK2": "Denmark (DK2)"
    }

    # Mapping between our area codes and ENTSO-E area codes
    ENTSOE_MAPPING = {
        "SE1": "10Y1001A1001A44P",  # Sweden SE1
        "SE2": "10Y1001A1001A45N",  # Sweden SE2
        "SE3": "10Y1001A1001A46L",  # Sweden SE3
        "SE4": "10Y1001A1001A47J",  # Sweden SE4
        "FI": "10YFI-1--------U",   # Finland
        "DK1": "10YDK-1--------W",  # Denmark DK1
        "DK2": "10YDK-2--------M",  # Denmark DK2
        "NO1": "10YNO-1--------2",  # Norway NO1
        "NO2": "10YNO-2--------T",  # Norway NO2
        "NO3": "10YNO-3--------J",  # Norway NO3
        "NO4": "10YNO-4--------9",  # Norway NO4
        "NO5": "10Y1001A1001A48H",  # Norway NO5
        "LT": "10YLT-1001A0008Q",   # Lithuania
        "LV": "10YLV-1001A00074",   # Latvia
        "EE": "10Y1001A1001A39I",   # Estonia
        "AT": "10YAT-APG------L",   # Austria
        "BE": "10YBE----------2",   # Belgium
        "DE": "10Y1001A1001A83F",   # Germany
        "FR": "10YFR-RTE------C",   # France
        "NL": "10YNL----------L",   # Netherlands
        "PL": "10YPL-AREA-----S",   # Poland
        "UK": "10Y1001A1001A92E",   # UK
        "GB": "10Y1001A1001A92E",   # Great Britain
        "IE": "10YIE-1001A00010",   # Ireland
        "ES": "10YES-REE------0",   # Spain
        "PT": "10YPT-REN------W",   # Portugal
        "IT": "10YIT-GRTN-----B",   # Italy
        "CH": "10YCH-SWISSGRIDZ"    # Switzerland
    }

    # Mapping between area codes and Nordpool delivery areas
    NORDPOOL_DELIVERY = {
        "SE1": "SFE_SYS:SE1",
        "SE2": "SFE_SYS:SE2",
        "SE3": "SFE_SYS:SE3",
        "SE4": "SFE_SYS:SE4",
        "FI": "SFE_SYS:FI",
        "DK1": "SFE_SYS:DK1",
        "DK2": "SFE_SYS:DK2",
        "NO1": "SFE_SYS:NO1",
        "NO2": "SFE_SYS:NO2",
        "NO3": "SFE_SYS:NO3",
        "NO4": "SFE_SYS:NO4",
        "NO5": "SFE_SYS:NO5",
        "LT": "SFE_SYS:LT",
        "LV": "SFE_SYS:LV",
        "EE": "SFE_SYS:EE"
    }

    # All areas combined (for UI display)
    ALL_AREAS = {
        "nordpool": NORDPOOL_AREAS,
        "energi_data_service": ENERGI_DATA_AREAS,
        "entso_e": ENTSOE_AREAS,
        "epex": EPEX_AREAS,
        "omie": OMIE_AREAS,
        "aemo": AEMO_AREAS,
        "stromligning": STROMLIGNING_AREAS
    }

class TimeFormat:
    """Time format constants."""
    DATE_ONLY = "%Y-%m-%d"
    HOUR_ONLY = "%H:%M"
    ENTSOE_DATE_HOUR = "%Y%m%d%H%M"

class EnergyUnit:
    """Energy unit constants."""
    MWH = "MWh"
    KWH = "kWh"
    WH = "Wh"

class PeriodType:
    """Period type constants."""
    TODAY = "today"
    TOMORROW = "tomorrow"
    OTHER = "other"
    MIN_VALID_HOURS = 20  # Minimum hours needed for valid tomorrow data

class ContentType:
    """Content type constants."""
    JSON = "application/json"
    XML = "application/xml"

class TimeInterval:
    """Time interval constants."""
    HOURLY = "PT60M"
    QUARTER_HOURLY = "PT15M"

class Network:
    """Network constants."""
    class URLs:
        """URL constants."""
        NORDPOOL = "https://www.nordpoolgroup.com/api/marketdata/page/10"
        ENTSOE = "https://transparency.entsoe.eu/api"
        ECB = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

    class Defaults:
        """Default values for network operations."""
        TIMEOUT = 30
        RETRY_COUNT = 3
        RETRY_BASE_DELAY = 2.0
        USER_AGENT = "ge_spot/1.0"
        CACHE_TTL = 86400  # 24 hours in seconds

class ECB:
    """ECB XML namespace constants."""
    XML_NAMESPACE_GESMES = "http://www.gesmes.org/xml/2002-08-01"
    XML_NAMESPACE_ECB = "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"

class Timezone:
    """Timezone constants."""
    AREA_TIMEZONES = {
        "SE1": "Europe/Stockholm",
        "SE2": "Europe/Stockholm",
        "SE3": "Europe/Stockholm",
        "SE4": "Europe/Stockholm",
        "FI": "Europe/Helsinki",
        "DK1": "Europe/Copenhagen",
        "DK2": "Europe/Copenhagen",
        "NO1": "Europe/Oslo",
        "NO2": "Europe/Oslo",
        "NO3": "Europe/Oslo",
        "NO4": "Europe/Oslo",
        "NO5": "Europe/Oslo",
        "LT": "Europe/Vilnius",
        "LV": "Europe/Riga",
        "EE": "Europe/Tallinn",
        "AT": "Europe/Vienna",
        "BE": "Europe/Brussels",
        "DE": "Europe/Berlin",
        "FR": "Europe/Paris",
        "NL": "Europe/Amsterdam",
        "PL": "Europe/Warsaw",
        "UK": "Europe/London",
        "GB": "Europe/London",
        "IE": "Europe/Dublin",
        "ES": "Europe/Madrid",
        "PT": "Europe/Lisbon",
        "IT": "Europe/Rome",
        "CH": "Europe/Zurich",
        "NSW": "Australia/Sydney",
        "QLD": "Australia/Brisbane",
        "SA": "Australia/Adelaide",
        "TAS": "Australia/Hobart",
        "VIC": "Australia/Melbourne"
    }

class UpdateInterval:
    """Update interval constants."""
    HOURLY = 60
    SIX_HOURS = 360
    TWELVE_HOURS = 720
    DAILY = 1440

    OPTIONS_DICT = {
        HOURLY: "1 hour",
        SIX_HOURS: "6 hours", 
        TWELVE_HOURS: "12 hours",
        DAILY: "24 hours"
    }

class Defaults:
    """Default values."""
    UPDATE_INTERVAL = UpdateInterval.HOURLY
    VAT = 0
    DISPLAY_UNIT = DisplayUnit.DECIMAL
