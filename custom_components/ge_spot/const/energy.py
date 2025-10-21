"""Energy-related constants for GE-Spot integration."""


class EnergyUnit:
    """Energy unit constants."""

    MWH = "MWh"
    KWH = "kWh"
    WH = "Wh"

    DEFAULT = MWH
    TARGET = KWH

    # Energy unit conversion map (relative to MWh)
    CONVERSION = {
        MWH: 1,
        KWH: 1000,
        WH: 1000000,
    }
