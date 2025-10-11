"""Area constants for GE-Spot integration."""

class Area:
    """Area code constants."""
    # Nordic regions
    SE1 = "SE1"
    SE2 = "SE2"
    SE3 = "SE3"
    SE4 = "SE4"
    DK1 = "DK1"
    DK2 = "DK2"
    NO1 = "NO1"  # East Norway
    NO2 = "NO2"  # South Norway
    NO3 = "NO3"  # Central Norway
    NO4 = "NO4"  # North Norway
    NO5 = "NO5"  # West Norway
    FI = "FI"
    EE = "EE"
    LV = "LV"
    LT = "LT"

    # Central Europe
    DE = "DE"
    DE_LU = "DE-LU"
    AT = "AT"
    FR = "FR"
    BE = "BE"
    NL = "NL"
    CH = "CH"

    # Iberia
    ES = "ES"
    PT = "PT"

    # Australia
    NSW1 = "NSW1"
    QLD1 = "QLD1"
    SA1 = "SA1"
    TAS1 = "TAS1"
    VIC1 = "VIC1"


class Timezone:
    """Timezone mappings for areas."""
    AREA_TIMEZONES = {
        # European regions
        Area.DK1: "Europe/Copenhagen",
        Area.DK2: "Europe/Copenhagen",
        Area.FI: "Europe/Helsinki",
        Area.EE: "Europe/Tallinn",
        Area.LT: "Europe/Vilnius",
        Area.LV: "Europe/Riga",
        Area.NO1: "Europe/Oslo",
        Area.NO2: "Europe/Oslo",
        Area.NO3: "Europe/Oslo",
        Area.NO4: "Europe/Oslo",
        Area.NO5: "Europe/Oslo",
        Area.SE1: "Europe/Stockholm",
        Area.SE2: "Europe/Stockholm",
        Area.SE3: "Europe/Stockholm",
        Area.SE4: "Europe/Stockholm",
        "SYS": "Europe/Stockholm",
        Area.FR: "Europe/Paris",
        Area.NL: "Europe/Amsterdam",
        Area.BE: "Europe/Brussels",
        Area.AT: "Europe/Vienna",
        Area.DE_LU: "Europe/Berlin",
        "GER": "Europe/Berlin",
        "IT": "Europe/Rome",
        "IT-North": "Europe/Rome",
        "IT-Centre-South": "Europe/Rome",
        "IT-South": "Europe/Rome",
        "IT-South-2": "Europe/Rome",
        "IT-Calabria": "Europe/Rome",
        "IT-Sicily": "Europe/Rome",
        "IT-Sardinia": "Europe/Rome",
        "MT": "Europe/Malta",
        "GB": "Europe/London",
        "GB(IFA)": "Europe/London",
        "GB(IFA2)": "Europe/London",
        "GB(ElecLink)": "Europe/London",
        "XK": "Europe/Belgrade",
        "MD": "Europe/Chisinau",
        "UA": "Europe/Kiev",
        "UA-IPS": "Europe/Kiev",
        "UA-DobTPP": "Europe/Kiev",
        "AM": "Asia/Yerevan",
        "GE": "Asia/Tbilisi",
        "AZ": "Asia/Baku",
        Area.ES: "Europe/Madrid",
        Area.PT: "Europe/Lisbon",
        Area.CH: "Europe/Zurich",
        "PL": "Europe/Warsaw",

        # Australian regions
        Area.NSW1: "Australia/Sydney",
        Area.QLD1: "Australia/Brisbane",
        Area.SA1: "Australia/Adelaide",
        Area.TAS1: "Australia/Hobart",
        Area.VIC1: "Australia/Melbourne",
    }


class AreaMapping:
    """Area mappings for different sources."""

    # Nordpool delivery area mapping
    NORDPOOL_DELIVERY = {
        Area.NO1: Area.NO1,
        Area.NO2: Area.NO2,
        Area.NO3: Area.NO3,
        Area.NO4: Area.NO4,
        Area.NO5: Area.NO5,
        Area.SE1: Area.SE1,
        Area.SE2: Area.SE2,
        Area.SE3: Area.SE3,
        Area.SE4: Area.SE4,
        Area.DK1: Area.DK1,
        Area.DK2: Area.DK2,
        Area.FI: Area.FI,
        Area.EE: Area.EE,
        Area.LV: Area.LV,
        Area.LT: Area.LT,
    }

    # Nordpool region mapping for v2 API
    # Is this needed?
    NORDPOOL_REGION_MAPPING = {
        Area.SE1: "Sweden",
        Area.SE2: "Sweden",
        Area.SE3: "Sweden",
        Area.SE4: "Sweden",
        Area.FI: "Finland",
        Area.DK1: "Denmark",
        Area.DK2: "Denmark",
        Area.NO1: "Norway",
        Area.NO2: "Norway",
        Area.NO3: "Norway",
        Area.NO4: "Norway",
        Area.NO5: "Norway",
        Area.LT: "Lithuania",
        Area.LV: "Latvia",
        Area.EE: "Estonia"
    }

    # Nordpool areas display names
    NORDPOOL_AREAS = {
        Area.NO1: "Norway (NO1)",
        Area.NO2: "Norway (NO2)",
        Area.NO3: "Norway (NO3)",
        Area.NO4: "Norway (NO4)",
        Area.NO5: "Norway (NO5)",
        Area.SE1: "Sweden (SE1)",
        Area.SE2: "Sweden (SE2)",
        Area.SE3: "Sweden (SE3)",
        Area.SE4: "Sweden (SE4)",
        Area.DK1: "Denmark (DK1)",
        Area.DK2: "Denmark (DK2)",
        Area.FI: "Finland (FI)",
        Area.EE: "Estonia (EE)",
        Area.LV: "Latvia (LV)",
        Area.LT: "Lithuania (LT)"
    }

    # Energi Data Service areas
    ENERGI_DATA_AREAS = {
        Area.DK1: "Denmark (DK1)",
        Area.DK2: "Denmark (DK2)",
    }

    # ENTSO-E area mapping from our area codes to ENTSO-E area codes
    ENTSOE_MAPPING = {
        # Core European Market Bidding Zones (SDAC)
        Area.AT: "10YAT-APG------L",
        Area.BE: "10YBE----------2",
        "BG": "10YCA-BULGARIA-R",
        "HR": "10YHR-HEP------M",
        "CZ": "10YCZ-CEPS-----N",
        Area.DK1: "10YDK-1--------W",
        Area.DK2: "10YDK-2--------M",
        Area.EE: "10Y1001A1001A39I",  # Updated EIC code (was: 10Y1001A1001A816)
        Area.FI: "10YFI-1--------U",
        Area.FR: "10YFR-RTE------C",
        Area.DE_LU: "10Y1001A1001A82H",
        "GR": "10YGR-HTSO-----Y",
        "HU": "10YHU-MAVIR----U",
        "IT": "10Y1001A1001A70O",  # Italy mainland
        "IT-North": "10Y1001A1001A71M",  # Italy north
        "IT-Centre-South": "10Y1001A1001A788",  # Italy centre-south
        "IT-South": "10Y1001A1001A885",  # Italy south
        "IT-South-2": "10Y1001A1001A75E",  # Additional Italian region
        "IT-Sardinia": "10Y1001A1001A73I",  # Updated EIC code (was: 10YIT-SARDGN--19)
        "IT-Sicily": "10Y1001A1001A74G",  # Updated EIC code (was: 10YIT-SICILY---A)
        Area.LV: "10YLV-1001A00074",  # Fixed: added missing zero
        Area.LT: "10YLT-1001A0008Q",  # Fixed: corrected EIC code
        Area.NL: "10YNL----------L",
        Area.NO1: "10Y1001A1001A48H",  # Updated EIC code (was: 10Y1001A1001A840)
        Area.NO2: "10YNO-2--------T",  # Updated EIC code (was: 10Y1001A1001A85Y)
        Area.NO3: "10YNO-3--------J",  # Updated EIC code (was: 10Y1001A1001A86W)
        Area.NO4: "10YNO-4--------9",  # Updated EIC code (was: 10Y1001A1001A87U)
        Area.NO5: "10Y1001A1001A48H",  # Fixed: corrected EIC code
        "PL": "10YPL-AREA-----S",
        Area.PT: "10YPT-REN------W",
        "RO": "10YRO-TEL------P",
        "SK": "10YSK-SEPS-----K",
        "SI": "10YSI-ELES-----O",
        Area.ES: "10YES-REE------0",
        Area.SE1: "10Y1001A1001A44P",  # Updated EIC code (was: 10YSE-1--------K)
        Area.SE2: "10Y1001A1001A45N",  # Updated EIC code (was: 10YSE-2--------E)
        Area.SE3: "10Y1001A1001A46L",  # Updated EIC code (was: 10YSE-3--------Y)
        Area.SE4: "10Y1001A1001A47J",  # Updated EIC code (was: 10YSE-4--------4)
        Area.CH: "10YCH-SWISSGRIDZ",

        # Other ENTSO-E Areas
        "GB": "10Y1001A1001A59C",  # Updated to use IE(SEM) code - working!
        "IE(SEM)": "10Y1001A1001A59C",
        "AL": "10YAL-KESH-----5",  # Re-enabled with verified code
        "BA": "10YBA-JPCC-----D",  # Re-enabled with verified code
        "ME": "10YCS-CG-TSO---S",  # Updated EIC code (was: 10YME-CGES-----S)
        "MK": "10YMK-MEPSO----8",
        "RS": "10YCS-SERBIATSOV",  # Updated EIC code (was: 10YRS-EMS------W)
        "TR": "10YTR-TEIAS----W",  # Re-enabled with verified code
        "UA": "10Y1001C--00003F",  # Fixed: corrected EIC code for Ukraine BZ
        "UA-IPS": "10Y1001C--000182",  # Ukraine IPS CTA
        "UA-BEI": "10YUA-WEPS-----0",  # Re-enabled with verified code
        "CY": "10YCY-1001A0003J",  # Re-enabled with verified code
    }

    # ENTSO-E areas (Display names)
    ENTSOE_AREAS = {
        # Core European Market Bidding Zones (SDAC)
        Area.AT: "Austria (AT)",
        Area.BE: "Belgium (BE)",
        "BG": "Bulgaria (BG)",
        "HR": "Croatia (HR)",
        "CZ": "Czech Republic (CZ)",
        Area.DK1: "Denmark (DK1, West Denmark)",
        Area.DK2: "Denmark (DK2, East Denmark)",
        Area.EE: "Estonia (EE)",
        Area.FI: "Finland (FI)",
        Area.FR: "France (FR)",
        Area.DE_LU: "Germany-Luxembourg (DE-LU)",
        "GR": "Greece (GR)",
        "HU": "Hungary (HU)",
        "IT": "Italy (IT, Mainland)",
        "IT-North": "Italy (IT-North)",
        "IT-Centre-South": "Italy (IT-Centre-South)",
        "IT-South": "Italy (IT-South)",
        "IT-South-2": "Italy (IT-South-2)",
        "IT-Sardinia": "Italy (IT-Sardinia)",
        "IT-Sicily": "Italy (IT-Sicily)",
        Area.LV: "Latvia (LV)",
        Area.LT: "Lithuania (LT)",
        Area.NL: "Netherlands (NL)",
        Area.NO1: "Norway (NO1, Oslo/East)",
        Area.NO2: "Norway (NO2, Kristiansand/South)",
        Area.NO3: "Norway (NO3, Trondheim/Central)",
        Area.NO4: "Norway (NO4, Tromsø/North)",
        Area.NO5: "Norway (NO5, Bergen/West)",
        "PL": "Poland (PL)",
        Area.PT: "Portugal (PT)",
        "RO": "Romania (RO)",
        "SK": "Slovakia (SK)",
        "SI": "Slovenia (SI)",
        Area.ES: "Spain (ES)",
        Area.SE1: "Sweden (SE1, Luleå/North)",
        Area.SE2: "Sweden (SE2, Sundsvall/North-Central)",
        Area.SE3: "Sweden (SE3, Stockholm/South-Central)",
        Area.SE4: "Sweden (SE4, Malmö/South)",
        Area.CH: "Switzerland (CH)",

        # Other ENTSO-E Areas
        "GB": "Great Britain (GB)",
        "IE(SEM)": "Ireland/Northern Ireland (SEM)",
        # "AL": "Albania (AL)",  # No day-ahead data available
        # "BA": "Bosnia and Herzegovina (BA)",  # No day-ahead data available
        "ME": "Montenegro (ME)",
        "MK": "North Macedonia (MK)",
        "RS": "Serbia (RS)",
        # "TR": "Turkey (TR)",  # No day-ahead data available
        # "UA": "Ukraine (UA)",  # No day-ahead data available - use UA-IPS instead
        "UA-IPS": "Ukraine IPS (UA-IPS)",
        # "UA-BEI": "Ukraine-West (UA-BEI)",  # No day-ahead data available
        # "CY": "Cyprus (CY)"  # No day-ahead data available
    }

    # Energy-Charts bidding zones (38 zones across Europe)
    ENERGY_CHARTS_BZN = {
        # Nordic regions
        Area.SE1: "SE1",
        Area.SE2: "SE2",
        Area.SE3: "SE3",
        Area.SE4: "SE4",
        Area.NO1: "NO1",
        Area.NO2: "NO2",
        Area.NO3: "NO3",
        Area.NO4: "NO4",
        Area.NO5: "NO5",
        "NO2NSL": "NO2NSL",  # Norway 2 NSL
        Area.DK1: "DK1",
        Area.DK2: "DK2",
        Area.FI: "FI",
        # Baltic states
        Area.EE: "EE",
        Area.LT: "LT",
        Area.LV: "LV",
        # Western Europe
        Area.DE_LU: "DE-LU",
        Area.FR: "FR",
        Area.NL: "NL",
        Area.BE: "BE",
        Area.AT: "AT",
        Area.CH: "CH",
        # Central & Eastern Europe
        "PL": "PL",
        "CZ": "CZ",
        "SK": "SK",
        "HU": "HU",
        "RO": "RO",
        "BG": "BG",
        "SI": "SI",
        "HR": "HR",
        "RS": "RS",
        "ME": "ME",
        "GR": "GR",
        # Italy zones (5 zones)
        "IT-North": "IT-North",
        "IT-South": "IT-South",
        "IT-Centre-South": "IT-Centre-South",
        "IT-Sardinia": "IT-Sardinia",
        "IT-Sicily": "IT-Sicily",
        # Iberia
        Area.ES: "ES",
        Area.PT: "PT",
    }

    # OMIE areas
    OMIE_AREAS = {
        Area.ES: "Spain",
        Area.PT: "Portugal",
    }

    # AEMO areas
    AEMO_AREAS = {
        Area.NSW1: "New South Wales (NSW1)",
        Area.QLD1: "Queensland (QLD1)",
        Area.SA1: "South Australia (SA1)",
        Area.TAS1: "Tasmania (TAS1)",
        Area.VIC1: "Victoria (VIC1)",
    }

    # Stromligning areas
    STROMLIGNING_AREAS = {
        Area.DK1: "Denmark (DK1)",
        Area.DK2: "Denmark (DK2)",
    }

    # ComEd areas
    COMED_AREAS = {
        "5minutefeed": "ComEd 5 Minute Price",
        "currenthouraverage": "ComEd Current Hour Average Price"
    }

    # All areas combined for lookup
    ALL_AREAS = {
        'nordpool': NORDPOOL_AREAS,
        'energi_data_service': ENERGI_DATA_AREAS,
        'entsoe': ENTSOE_AREAS,
        'energy_charts': ENERGY_CHARTS_BZN,
        'omie': OMIE_AREAS,
        'aemo': AEMO_AREAS,
        'stromligning': STROMLIGNING_AREAS,
        'comed': COMED_AREAS
    }

    # Default areas for each source
    DEFAULT_AREAS = {
        "nordpool": Area.SE4,
        "energi_data_service": Area.DK1,
        "entsoe": "10Y1001A1001A47J",  # SE4 EIC Code (updated)
        "energy_charts": Area.DE_LU,
        "omie": Area.ES,
        "aemo": Area.NSW1,
        "stromligning": Area.DK1,
        "comed": "5minutefeed",
    }


class AreaInfo:
    """Utility class for area information."""

    # Map areas to their regions
    AREA_REGIONS = {
        # Nordic countries
        "DK1": "Nordic",
        "DK2": "Nordic",
        "SE1": "Nordic",
        "SE2": "Nordic",
        "SE3": "Nordic",
        "SE4": "Nordic",
        "FI": "Nordic",
        "NO1": "Nordic",
        "NO2": "Nordic",
        "NO3": "Nordic",
        "NO4": "Nordic",
        "NO5": "Nordic",
        "EE": "Baltic",
        "LT": "Baltic",
        "LV": "Baltic",

        # Central Europe
        "DE": "Central Europe",
        "DE-LU": "Central Europe",
        "AT": "Central Europe",
        "FR": "Central Europe",
        "BE": "Central Europe",
        "NL": "Central Europe",
        "CH": "Central Europe",
        "CZ": "Central Europe",
        "PL": "Central Europe",
        "HU": "Central Europe",
        "SK": "Central Europe",
        "SI": "Central Europe",

        # Southern Europe
        "ES": "Southern Europe",
        "PT": "Southern Europe",
        "IT": "Southern Europe",
        "GR": "Southern Europe",
        "HR": "Southern Europe",
        "BG": "Southern Europe",
        "RO": "Southern Europe",

        # British Isles
        "GB": "British Isles",
        "UK": "British Isles",
        "IE": "British Isles",

        # Australia
        "NSW1": "Australia",
        "QLD1": "Australia",
        "SA1": "Australia",
        "TAS1": "Australia",
        "VIC1": "Australia",

        # USA
        "COMED": "USA",
        "US": "USA",
    }

    # Map areas to their common names
    AREA_NAMES = {
        # Nordic countries
        "DK1": "West Denmark",
        "DK2": "East Denmark",
        "SE1": "North Sweden",
        "SE2": "North-Central Sweden",
        "SE3": "South-Central Sweden",
        "SE4": "South Sweden",
        "FI": "Finland",
        "NO1": "East Norway (Oslo)",
        "NO2": "South Norway (Kristiansand)",
        "NO3": "Central Norway (Trondheim)",
        "NO4": "North Norway (Tromsø)",
        "NO5": "West Norway (Bergen)",
        "EE": "Estonia",
        "LT": "Lithuania",
        "LV": "Latvia",

        # Central Europe
        "DE": "Germany",
        "DE-LU": "Germany-Luxembourg",
        "AT": "Austria",
        "FR": "France",
        "BE": "Belgium",
        "NL": "Netherlands",
        "CH": "Switzerland",

        # Southern Europe
        "ES": "Spain",
        "PT": "Portugal",

        # Australia
        "NSW1": "New South Wales",
        "QLD1": "Queensland",
        "SA1": "South Australia",
        "TAS1": "Tasmania",
        "VIC1": "Victoria",
    }

    @classmethod
    def get_region_for_area(cls, area: str) -> str:
        """Get region for a specific area code.

        Args:
            area: Area code

        Returns:
            Region name or None if not found
        """
        return cls.AREA_REGIONS.get(area)

    @classmethod
    def get_name_for_area(cls, area: str) -> str:
        """Get human-readable name for a specific area code.

        Args:
            area: Area code

        Returns:
            Area name or the area code if not found
        """
        return cls.AREA_NAMES.get(area, area)

    @classmethod
    def get_areas_for_region(cls, region: str) -> list:
        """Get all areas in a specific region.

        Args:
            region: Region name

        Returns:
            List of area codes in the region
        """
        return [area for area, reg in cls.AREA_REGIONS.items() if reg == region]


def get_available_sources(area: str) -> list:
    """Get a list of available sources for an area.

    Args:
        area: The area code to check

    Returns:
        List of source identifiers that support this area
    """
    available_sources = []

    # Check each source's area mappings
    if area in AreaMapping.NORDPOOL_AREAS:
        available_sources.append("nordpool")

    if area in AreaMapping.ENERGI_DATA_AREAS:
        available_sources.append("energi_data_service")

    # Only add ENTSOE for areas visible in config (working areas only)
    if area in AreaMapping.ENTSOE_AREAS:
        available_sources.append("entsoe")

    if area in AreaMapping.ENERGY_CHARTS_BZN:
        available_sources.append("energy_charts")

    if area in AreaMapping.OMIE_AREAS:
        available_sources.append("omie")

    if area in AreaMapping.AEMO_AREAS:
        available_sources.append("aemo")

    if area in AreaMapping.STROMLIGNING_AREAS:
        available_sources.append("stromligning")

    if area in AreaMapping.COMED_AREAS:
        available_sources.append("comed")

    return available_sources
