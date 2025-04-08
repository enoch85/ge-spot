"""Energy-related constants for GE-Spot integration."""

class EnergyUnit:
    """Energy unit constants."""
    MWH = "MWh"
    KWH = "kWh"
    WH = "Wh"
    
    DEFAULT = MWH
    TARGET = KWH

# Energy unit conversion map (relative to MWh)
ENERGY_UNIT_CONVERSION = {
    EnergyUnit.MWH: 1,
    EnergyUnit.KWH: 1000,
    EnergyUnit.WH: 1000000,
}
