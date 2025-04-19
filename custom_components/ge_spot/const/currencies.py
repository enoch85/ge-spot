"""Currency constants for GE-Spot integration."""

class Currency:
    """Currency code constants."""
    EUR = "EUR"  # Euro
    SEK = "SEK"  # Swedish krona
    NOK = "NOK"  # Norwegian krone
    DKK = "DKK"  # Danish krone
    GBP = "GBP"  # British pound
    AUD = "AUD"  # Australian dollar
    MDL = "MDL"  # Moldovan leu
    UAH = "UAH"  # Ukrainian hryvnia
    AMD = "AMD"  # Armenian dram
    GEL = "GEL"  # Georgian lari
    AZN = "AZN"  # Azerbaijani manat
    USD = "USD"  # US dollar
    CENTS = "cents"  # US cents (used by ComEd API)


class CurrencyInfo:
    """Currency information including subunits and region mappings."""

    # Region to Currency mapping
    REGION_TO_CURRENCY = {
        # Nordics
        "SE1": Currency.SEK,
        "SE2": Currency.SEK,
        "SE3": Currency.SEK,
        "SE4": Currency.SEK,
        "DK1": Currency.DKK,
        "DK2": Currency.DKK,
        "FI": Currency.EUR,
        "NO1": Currency.NOK,
        "NO2": Currency.NOK,
        "NO3": Currency.NOK,
        "NO4": Currency.NOK,
        "NO5": Currency.NOK,
        "DK1-NO1": Currency.NOK,  # Cross-border, default to NOK
        # Baltics
        "EE": Currency.EUR,
        "LV": Currency.EUR,
        "LT": Currency.EUR,
        # Central Europe
        "AT": Currency.EUR,
        "BE": Currency.EUR,
        "FR": Currency.EUR,
        "DE-LU": Currency.EUR,
        "NL": Currency.EUR,
        # UK
        "GB": Currency.GBP,
        "GB(IFA)": Currency.GBP,
        "GB(IFA2)": Currency.GBP,
        "GB(ElecLink)": Currency.GBP,
        # Italy and Mediterranean
        "IT": Currency.EUR,
        "IT-North": Currency.EUR,
        "IT-North-AT": Currency.EUR,
        "IT-North-CH": Currency.EUR,
        "IT-North-FR": Currency.EUR,
        "IT-North-SI": Currency.EUR,
        "IT-Centre-North": Currency.EUR,
        "IT-Centre-South": Currency.EUR,
        "IT-South": Currency.EUR,
        "IT-Calabria": Currency.EUR,
        "IT-Brindisi": Currency.EUR,
        "IT-Foggia": Currency.EUR,
        "IT-Rossano": Currency.EUR,
        "IT-Priolo": Currency.EUR,
        "IT-Sicily": Currency.EUR,
        "IT-Sardinia": Currency.EUR,
        "IT-SACOAC": Currency.EUR,
        "IT-SACODC": Currency.EUR,
        "IT-GR": Currency.EUR,
        "IT-Malta": Currency.EUR,
        "MT": Currency.EUR,
        # Eastern Europe and Caucasus
        "XK": Currency.EUR,  # Kosovo uses Euro
        "MD": Currency.MDL,  # Moldova uses Moldovan Leu
        "UA": Currency.UAH,  # Ukraine uses Ukrainian Hryvnia
        "UA-IPS": Currency.UAH,
        "UA-DobTPP": Currency.UAH,
        "AM": Currency.AMD,  # Armenia uses Armenian Dram
        "GE": Currency.GEL,  # Georgia uses Georgian Lari
        "AZ": Currency.AZN,  # Azerbaijan uses Azerbaijani Manat
        # Multi-country areas
        "CZ-DE-SK-LT-SE4": Currency.EUR,  # Mixed currency zone, default to EUR
        # Australia
        "NSW1": Currency.AUD,
        "QLD1": Currency.AUD,
        "SA1": Currency.AUD,
        "TAS1": Currency.AUD,
        "VIC1": Currency.AUD,
        # United States
        "5minutefeed": Currency.CENTS,  # ComEd 5 minute feed (already in cents/kWh)
        "currenthouraverage": Currency.CENTS,  # ComEd current hour average (already in cents/kWh)
    }

    # Currency subunit multipliers
    SUBUNIT_MULTIPLIER = {
        Currency.EUR: 100,  # Euro to cents
        Currency.SEK: 100,  # Swedish krona to öre
        Currency.NOK: 100,  # Norwegian krone to øre
        Currency.DKK: 100,  # Danish krone to øre
        Currency.GBP: 100,  # Pound to pence
        Currency.AUD: 100,  # Australian dollar to cents
        Currency.MDL: 100,  # Moldovan leu to bani
        Currency.UAH: 100,  # Ukrainian hryvnia to kopiyky
        Currency.AMD: 100,  # Armenian dram to luma
        Currency.GEL: 100,  # Georgian lari to tetri
        Currency.AZN: 100,  # Azerbaijani manat to qəpik
        Currency.USD: 100,  # US dollar to cents
        Currency.CENTS: 1,   # cents are already in the smallest unit
    }

    # Currency subunit names
    SUBUNIT_NAMES = {
        Currency.EUR: "cents",
        Currency.SEK: "öre",
        Currency.NOK: "øre",
        Currency.DKK: "øre",
        Currency.GBP: "pence",
        Currency.AUD: "cents",
        Currency.MDL: "bani",
        Currency.UAH: "kopiyky",
        Currency.AMD: "luma",
        Currency.GEL: "tetri",
        Currency.AZN: "qəpik",
        Currency.USD: "cents",
        Currency.CENTS: "cents",  # cents are already in the smallest unit
    }
