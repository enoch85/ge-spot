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
    FIFTEEN_MINUTES = 15  # 15 minutes
    HOUR = 60             # 1 hour in minutes
    TWELVE_HOURS = 720    # 12 hours in minutes
    DAY = 1440            # 24 hours (full day) in minutes

    OPTIONS = [
        {"value": FIFTEEN_MINUTES, "label": "15 minutes"},
        {"value": HOUR, "label": "1 hour"},
        {"value": TWELVE_HOURS, "label": "12 hours"},
        {"value": DAY, "label": "24 hours"},
    ]

    # For selectors in configurations
    OPTIONS_DICT = {
        FIFTEEN_MINUTES: "15 minutes",
        HOUR: "1 hour",
        TWELVE_HOURS: "12 hours",
        DAY: "24 hours",
    }
