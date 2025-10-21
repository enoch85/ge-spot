"""Display constants for GE-Spot integration."""

class DisplayUnit:
    """Display unit options."""
    DECIMAL = "decimal"  # Example: 0.15 EUR/kWh
    CENTS = "cents"  # Example: 15 cents/kWh or 15 öre/kWh

    # Units displayable to the user
    OPTIONS = {
        CENTS: "Cents (e.g. 15 cents/kWh)",
        DECIMAL: "Decimal (e.g. 0.15 EUR/kWh)",
    }


class UpdateInterval:
    """Update interval options."""
    FIFTEEN_MINUTES = 15  # 15 minutes
    THIRTY_MINUTES = 30   # 30 minutes
    HOUR = 60             # 1 hour in minutes

    OPTIONS = [
        {"value": FIFTEEN_MINUTES, "label": "15 minutes"},
        {"value": THIRTY_MINUTES, "label": "30 minutes"},
        {"value": HOUR, "label": "1 hour"},
    ]

    # For selectors in configurations
    OPTIONS_DICT = {
        FIFTEEN_MINUTES: "15 minutes",
        THIRTY_MINUTES: "30 minutes",
        HOUR: "1 hour",
    }
