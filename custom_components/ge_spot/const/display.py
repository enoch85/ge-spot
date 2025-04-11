"""Display constants for GE-Spot integration."""

class DisplayUnit:
    """Display unit options."""
    DECIMAL = "decimal"  # Example: 0.15 EUR/kWh
    CENTS = "cents"  # Example: 15 cents/kWh or 15 öre/kWh

    # Units displayable to the user
    OPTIONS = {
        DECIMAL: "Decimal (e.g., 0.15 EUR/kWh)",
        CENTS: "Cents (e.g., 15 cents/kWh)",
    }


class UpdateInterval:
    """Update interval options."""
    HOUR = 60          # 1 hour in minutes
    SIX_HOURS = 360    # 6 hours in minutes
    TWELVE_HOURS = 720 # 12 hours in minutes
    DAY = 1440         # 24 hours (full day) in minutes

    OPTIONS = [
        {"value": HOUR, "label": "1 hour"},
        {"value": SIX_HOURS, "label": "6 hours"},
        {"value": TWELVE_HOURS, "label": "12 hours"},
        {"value": DAY, "label": "24 hours"},
    ]

    # For selectors in configurations
    OPTIONS_DICT = {
        HOUR: "1 hour",
        SIX_HOURS: "6 hours",
        TWELVE_HOURS: "12 hours",
        DAY: "24 hours",
    }
