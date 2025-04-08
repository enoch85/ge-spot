"""Currency constants for GE-Spot integration."""

# Direct Currency code constants - for modules that import them directly
CURRENCY_EUR = "EUR"  # Euro
CURRENCY_SEK = "SEK"  # Swedish krona
CURRENCY_NOK = "NOK"  # Norwegian krone
CURRENCY_DKK = "DKK"  # Danish krone
CURRENCY_GBP = "GBP"  # British pound
CURRENCY_AUD = "AUD"  # Australian dollar
CURRENCY_MDL = "MDL"  # Moldovan leu
CURRENCY_UAH = "UAH"  # Ukrainian hryvnia
CURRENCY_AMD = "AMD"  # Armenian dram
CURRENCY_GEL = "GEL"  # Georgian lari
CURRENCY_AZN = "AZN"  # Azerbaijani manat

# Currency class - more modern approach
class Currency:
    """Currency code constants."""
    EUR = CURRENCY_EUR
    SEK = CURRENCY_SEK
    NOK = CURRENCY_NOK
    DKK = CURRENCY_DKK
    GBP = CURRENCY_GBP
    AUD = CURRENCY_AUD
    MDL = CURRENCY_MDL
    UAH = CURRENCY_UAH
    AMD = CURRENCY_AMD
    GEL = CURRENCY_GEL
    AZN = CURRENCY_AZN

# Region to Currency mapping
REGION_TO_CURRENCY = {
    # Nordics
    "SE1": CURRENCY_SEK,
    "SE2": CURRENCY_SEK,
    "SE3": CURRENCY_SEK,
    "SE4": CURRENCY_SEK,
    "DK1": CURRENCY_DKK,
    "DK2": CURRENCY_DKK,
    "FI": CURRENCY_EUR,
    "NO1": CURRENCY_NOK,
    "NO1A": CURRENCY_NOK,
    "NO2": CURRENCY_NOK,
    "NO2A": CURRENCY_NOK,
    "NO2NSL": CURRENCY_NOK,
    "NO3": CURRENCY_NOK,
    "NO4": CURRENCY_NOK,
    "NO5": CURRENCY_NOK,
    "DK1-NO1": CURRENCY_NOK,  # Cross-border, default to NOK
    # Baltics
    "EE": CURRENCY_EUR,
    "LV": CURRENCY_EUR,
    "LT": CURRENCY_EUR,
    # Central Europe
    "AT": CURRENCY_EUR,
    "BE": CURRENCY_EUR,
    "FR": CURRENCY_EUR,
    "DE-LU": CURRENCY_EUR,
    "NL": CURRENCY_EUR,
    # UK
    "GB": CURRENCY_GBP,
    "GB(IFA)": CURRENCY_GBP,
    "GB(IFA2)": CURRENCY_GBP,
    "GB(ElecLink)": CURRENCY_GBP,
    # Italy and Mediterranean
    "IT": CURRENCY_EUR,
    "IT-North": CURRENCY_EUR,
    "IT-North-AT": CURRENCY_EUR,
    "IT-North-CH": CURRENCY_EUR,
    "IT-North-FR": CURRENCY_EUR,
    "IT-North-SI": CURRENCY_EUR,
    "IT-Centre-North": CURRENCY_EUR,
    "IT-Centre-South": CURRENCY_EUR,
    "IT-South": CURRENCY_EUR,
    "IT-Calabria": CURRENCY_EUR,
    "IT-Brindisi": CURRENCY_EUR,
    "IT-Foggia": CURRENCY_EUR,
    "IT-Rossano": CURRENCY_EUR,
    "IT-Priolo": CURRENCY_EUR,
    "IT-Sicily": CURRENCY_EUR,
    "IT-Sardinia": CURRENCY_EUR,
    "IT-SACOAC": CURRENCY_EUR,
    "IT-SACODC": CURRENCY_EUR,
    "IT-GR": CURRENCY_EUR,
    "IT-Malta": CURRENCY_EUR,
    "MT": CURRENCY_EUR,
    # Eastern Europe and Caucasus
    "XK": CURRENCY_EUR,  # Kosovo uses Euro
    "MD": CURRENCY_MDL,  # Moldova uses Moldovan Leu
    "UA": CURRENCY_UAH,  # Ukraine uses Ukrainian Hryvnia
    "UA-IPS": CURRENCY_UAH,
    "UA-DobTPP": CURRENCY_UAH,
    "AM": CURRENCY_AMD,  # Armenia uses Armenian Dram
    "GE": CURRENCY_GEL,  # Georgia uses Georgian Lari
    "AZ": CURRENCY_AZN,  # Azerbaijan uses Azerbaijani Manat
    # Multi-country areas
    "CZ-DE-SK-LT-SE4": CURRENCY_EUR,  # Mixed currency zone, default to EUR
    # Australia
    "NSW1": CURRENCY_AUD,
    "QLD1": CURRENCY_AUD,
    "SA1": CURRENCY_AUD,
    "TAS1": CURRENCY_AUD,
    "VIC1": CURRENCY_AUD,
    # Additional mappings (Norwegian regions)
    "Oslo": CURRENCY_NOK,
    "Kr.sand": CURRENCY_NOK,
    "Bergen": CURRENCY_NOK,
    "Molde": CURRENCY_NOK,
    "Tr.heim": CURRENCY_NOK,
    "Tromsø": CURRENCY_NOK,
}

# Currency subunit multipliers
CURRENCY_SUBUNIT_MULTIPLIER = {
    CURRENCY_EUR: 100,  # Euro to cents
    CURRENCY_SEK: 100,  # Swedish krona to öre
    CURRENCY_NOK: 100,  # Norwegian krone to øre
    CURRENCY_DKK: 100,  # Danish krone to øre
    CURRENCY_GBP: 100,  # Pound to pence
    CURRENCY_AUD: 100,  # Australian dollar to cents
    CURRENCY_MDL: 100,  # Moldovan leu to bani
    CURRENCY_UAH: 100,  # Ukrainian hryvnia to kopiyky
    CURRENCY_AMD: 100,  # Armenian dram to luma
    CURRENCY_GEL: 100,  # Georgian lari to tetri
    CURRENCY_AZN: 100,  # Azerbaijani manat to qəpik
}

# Currency subunit names
CURRENCY_SUBUNIT_NAMES = {
    CURRENCY_EUR: "cents",
    CURRENCY_SEK: "öre",
    CURRENCY_NOK: "øre",
    CURRENCY_DKK: "øre",
    CURRENCY_GBP: "pence",
    CURRENCY_AUD: "cents",
    CURRENCY_MDL: "bani",
    CURRENCY_UAH: "kopiyky",
    CURRENCY_AMD: "luma",
    CURRENCY_GEL: "tetri",
    CURRENCY_AZN: "qəpik",
}
