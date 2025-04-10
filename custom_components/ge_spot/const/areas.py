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
        "IT-Centre-North": "Europe/Rome",
        "IT-Centre-South": "Europe/Rome",
        "IT-South": "Europe/Rome",
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
        # Nordic regions
        Area.SE1: "10Y1001A1001A44P",
        Area.SE2: "10Y1001A1001A45N",
        Area.SE3: "10Y1001A1001A46L",
        Area.SE4: "10Y1001A1001A47J",
        Area.DK1: "10YDK-1--------W",
        Area.DK2: "10YDK-2--------M",
        Area.NO1: "10YNO-1--------2",
        Area.NO2: "10YNO-2--------T",
        Area.NO3: "10YNO-3--------J",
        Area.NO4: "10YNO-4--------9",
        Area.NO5: "10Y1001A1001A48H",
        "DK1-NO1": "46Y000000000007M",
        Area.FI: "10YFI-1--------U",
        Area.EE: "10Y1001A1001A39I",
        Area.LV: "10YLV-1001A00074",
        Area.LT: "10YLT-1001A0008Q",

        # Central Europe
        Area.DE: "10Y1001A1001A83F",
        Area.DE_LU: "10Y1001A1001A82H",
        Area.AT: "10YAT-APG------L",
        Area.BE: "10YBE----------2",
        Area.NL: "10YNL----------L",
        Area.FR: "10YFR-RTE------C",
        "LU": "10YLU-CEGEDEL-NQ",
        "GB": "10YGB----------A",
        "GB(IFA)": "10Y1001C--00098F",
        "GB(IFA2)": "17Y0000009369493",
        "GB(ElecLink)": "11Y0-0000-0265-K",
        "IE": "10YIE-1001A00010",
        Area.ES: "10YES-REE------0",
        Area.PT: "10YPT-REN------W",
        Area.CH: "10YCH-SWISSGRIDZ",
        "IT": "10YIT-GRTN-----B",
        "IT-North": "10Y1001A1001A73I",
        "IT-North-AT": "10Y1001A1001A80L",
        "IT-North-CH": "10Y1001A1001A68B",
        "IT-North-FR": "10Y1001A1001A81J",
        "IT-North-SI": "10Y1001A1001A67D",
        "IT-Centre-North": "10Y1001A1001A70O",
        "IT-Centre-South": "10Y1001A1001A71M",
        "IT-South": "10Y1001A1001A788",
        "IT-Calabria": "10Y1001C--00096J",
        "IT-Brindisi": "10Y1001A1001A699",
        "IT-Foggia": "10Y1001A1001A72K",
        "IT-Rossano": "10Y1001A1001A77A",
        "IT-Priolo": "10Y1001A1001A76C",
        "IT-Sicily": "10Y1001A1001A75E",
        "IT-Sardinia": "10Y1001A1001A74G",
        "IT-SACOAC": "10Y1001A1001A885",
        "IT-SACODC": "10Y1001A1001A893",
        "IT-GR": "10Y1001A1001A66F",
        "IT-Malta": "10Y1001A1001A877",
        "MT": "10Y1001A1001A93C",
        "CZ": "10YCZ-CEPS-----N",
        "PL": "10YPL-AREA-----S",
        "SI": "10YSI-ELES-----O",
        "SK": "10YSK-SEPS-----K",
        "HU": "10YHU-MAVIR----U",
        "RO": "10YRO-TEL------P",
        "BG": "10YCA-BULGARIA-R",
        "GR": "10YGR-HTSO-----Y",
        "HR": "10YHR-HEP------M",
        "RS": "10YCS-SERBIATSOV",
        "XK": "10Y1001C--00100H",
        "MD": "10Y1001A1001A990",

        # Eastern Europe and Caucasus
        "UA": "10Y1001C--00003F",
        "UA-IPS": "10Y1001C--000182",
        "UA-DobTPP": "10Y1001A1001B869",
        "AM": "10Y1001A1001B004",
        "GE": "10Y1001A1001B012",
        "AZ": "10Y1001A1001B05V",

        # Multi-country areas
        "CZ-DE-SK-LT-SE4": "10Y1001C--00038X"
    }

    # ENTSO-E areas (Display names)
    ENTSOE_AREAS = {
        # Nordic regions
        Area.SE1: "Sweden (SE1)",
        Area.SE2: "Sweden (SE2)",
        Area.SE3: "Sweden (SE3)",
        Area.SE4: "Sweden (SE4)",
        Area.DK1: "Denmark (DK1)",
        Area.DK2: "Denmark (DK2)",
        Area.NO1: "NO1 (Øst/East)",
        Area.NO2: "NO2 (Sør/South)",
        Area.NO3: "NO3 (Midt/Central)",
        Area.NO4: "NO4 (Nord/North)",
        Area.NO5: "NO5 (Vest/West)",
        "DK1-NO1": "Denmark-Norway (DK1-NO1)",
        Area.FI: "Finland",
        Area.EE: "Estonia",
        Area.LV: "Latvia",
        Area.LT: "Lithuania",

        # Central Europe
        Area.DE: "Germany",
        Area.DE_LU: "Germany-Luxembourg",
        Area.AT: "Austria",
        Area.BE: "Belgium",
        Area.NL: "Netherlands",
        Area.FR: "France",
        "LU": "Luxembourg",
        "GB": "Great Britain",
        "GB(IFA)": "Great Britain (IFA)",
        "GB(IFA2)": "Great Britain (IFA2)",
        "GB(ElecLink)": "Great Britain (ElecLink)",
        "IE": "Ireland",
        Area.ES: "Spain",
        Area.PT: "Portugal",
        Area.CH: "Switzerland",
        "IT": "Italy",
        "IT-North": "Italy (North)",
        "IT-North-AT": "Italy-North-Austria",
        "IT-North-CH": "Italy-North-Switzerland",
        "IT-North-FR": "Italy-North-France",
        "IT-North-SI": "Italy-North-Slovenia",
        "IT-Centre-North": "Italy (Centre-North)",
        "IT-Centre-South": "Italy (Centre-South)",
        "IT-South": "Italy (South)",
        "IT-Calabria": "Italy (Calabria)",
        "IT-Brindisi": "Italy (Brindisi)",
        "IT-Foggia": "Italy (Foggia)",
        "IT-Rossano": "Italy (Rossano)",
        "IT-Priolo": "Italy (Priolo)",
        "IT-Sicily": "Italy (Sicily)",
        "IT-Sardinia": "Italy (Sardinia)",
        "IT-SACOAC": "Italy (SACOAC)",
        "IT-SACODC": "Italy (SACODC)",
        "IT-GR": "Italy-Greece",
        "IT-Malta": "Italy-Malta",
        "MT": "Malta",
        "CZ": "Czech Republic",
        "PL": "Poland",
        "SI": "Slovenia",
        "SK": "Slovakia",
        "HU": "Hungary",
        "RO": "Romania",
        "BG": "Bulgaria",
        "GR": "Greece",
        "HR": "Croatia",
        "RS": "Serbia",
        "XK": "Kosovo",
        "MD": "Moldova",

        # Eastern Europe and Caucasus
        "UA": "Ukraine",
        "UA-IPS": "Ukraine (IPS)",
        "UA-DobTPP": "Ukraine (DobTPP)",
        "AM": "Armenia",
        "GE": "Georgia",
        "AZ": "Azerbaijan",

        # Multi-country areas
        "CZ-DE-SK-LT-SE4": "Czech-Germany-Slovakia-Lithuania-Sweden4",

        # These require ENTSO-E codes to be used directly
        "10YBA-JPCC-----D": "Bosnia Herzegovina",
        "10YCS-CG-TSO---S": "Montenegro",
        "10YMK-MEPSO----8": "North Macedonia",
        "10YAL-KESH-----5": "Albania",
        "10Y1001C--00003F": "Ukraine",
        "10YTR-TEIAS----W": "Turkey",
        "10YCY-1001A0003J": "Cyprus",
        "10Y1001A1001A93C": "Malta"
    }

    # EPEX areas
    EPEX_AREAS = {
        Area.DE_LU: "Germany-Luxembourg",
        Area.FR: "France",
        Area.BE: "Belgium",
        Area.NL: "Netherlands",
        Area.AT: "Austria",
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

    # All areas combined for lookup
    ALL_AREAS = {
        'nordpool': NORDPOOL_AREAS,
        'energi_data_service': ENERGI_DATA_AREAS,
        'entsoe': ENTSOE_AREAS,
        'epex': EPEX_AREAS,
        'omie': OMIE_AREAS,
        'aemo': AEMO_AREAS,
        'stromligning': STROMLIGNING_AREAS
    }

    # Default areas for each source
    DEFAULT_AREAS = {
        "nordpool": Area.SE4,
        "energi_data_service": Area.DK1,
        "entsoe": "10Y1001A1001A47J",  # SE4 EIC Code
        "epex": Area.DE_LU,
        "omie": Area.ES,
        "aemo": Area.NSW1,
        "stromligning": Area.DK1,
    }
