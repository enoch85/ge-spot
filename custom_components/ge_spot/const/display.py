"""Display constants for GE-Spot integration."""

# Display unit options
DISPLAY_UNIT_DECIMAL = "decimal"  # Example: 0.15 EUR/kWh
DISPLAY_UNIT_CENTS = "cents"  # Example: 15 cents/kWh or 15 öre/kWh

DISPLAY_UNITS = {
    DISPLAY_UNIT_DECIMAL: "Decimal (e.g., 0.15 EUR/kWh)",
    DISPLAY_UNIT_CENTS: "Cents/Öre (e.g., 15 cents/kWh)",
}

# Update interval options with longer durations
UPDATE_INTERVAL_OPTIONS = [
    {"value": 60, "label": "1 hour"},
    {"value": 360, "label": "6 hours"},
    {"value": 720, "label": "12 hours"},
    {"value": 1440, "label": "24 hours"},
]
