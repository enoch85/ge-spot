"""Currency constants for GE-Spot integration."""

# Region to Currency mapping
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
    "NO1A": "NOK",
    "NO2": "NOK",
    "NO2A": "NOK",
    "NO2NSL": "NOK",
    "NO3": "NOK",
    "NO4": "NOK",
    "NO5": "NOK",
    "DK1-NO1": "NOK",  # Cross-border, default to NOK
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
    "GB(IFA)": "GBP",
    "GB(IFA2)": "GBP",
    "GB(ElecLink)": "GBP",
    # Italy and Mediterranean
    "IT": "EUR",
    "IT-North": "EUR",
    "IT-North-AT": "EUR",
    "IT-North-CH": "EUR",
    "IT-North-FR": "EUR",
    "IT-North-SI": "EUR",
    "IT-Centre-North": "EUR",
    "IT-Centre-South": "EUR",
    "IT-South": "EUR",
    "IT-Calabria": "EUR",
    "IT-Brindisi": "EUR",
    "IT-Foggia": "EUR",
    "IT-Rossano": "EUR",
    "IT-Priolo": "EUR",
    "IT-Sicily": "EUR",
    "IT-Sardinia": "EUR",
    "IT-SACOAC": "EUR",
    "IT-SACODC": "EUR",
    "IT-GR": "EUR",
    "IT-Malta": "EUR",
    "MT": "EUR",
    # Eastern Europe and Caucasus
    "XK": "EUR",  # Kosovo uses Euro
    "MD": "MDL",  # Moldova uses Moldovan Leu
    "UA": "UAH",  # Ukraine uses Ukrainian Hryvnia
    "UA-IPS": "UAH",
    "UA-DobTPP": "UAH",
    "AM": "AMD",  # Armenia uses Armenian Dram
    "GE": "GEL",  # Georgia uses Georgian Lari
    "AZ": "AZN",  # Azerbaijan uses Azerbaijani Manat
    # Multi-country areas
    "CZ-DE-SK-LT-SE4": "EUR",  # Mixed currency zone, default to EUR
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

# Currency subunit multipliers
CURRENCY_SUBUNIT_MULTIPLIER = {
    "EUR": 100,  # Euro to cents
    "SEK": 100,  # Swedish krona to öre
    "NOK": 100,  # Norwegian krone to øre
    "DKK": 100,  # Danish krone to øre
    "GBP": 100,  # Pound to pence
    "AUD": 100,  # Australian dollar to cents
    "MDL": 100,  # Moldovan leu to bani
    "UAH": 100,  # Ukrainian hryvnia to kopiyky
    "AMD": 100,  # Armenian dram to luma
    "GEL": 100,  # Georgian lari to tetri
    "AZN": 100,  # Azerbaijani manat to qəpik
}

# Currency subunit names
CURRENCY_SUBUNIT_NAMES = {
    "EUR": "cents",
    "SEK": "öre",
    "NOK": "øre",
    "DKK": "øre",
    "GBP": "pence",
    "AUD": "cents",
    "MDL": "bani",
    "UAH": "kopiyky",
    "AMD": "luma",
    "GEL": "tetri",
    "AZN": "qəpik",
}

# Energy unit conversion
ENERGY_UNIT_CONVERSION = {
    "MWh": 1,
    "kWh": 1000,
    "Wh": 1000000,
}
