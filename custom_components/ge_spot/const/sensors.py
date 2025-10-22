"""Sensor constants for GE-Spot integration."""


# Sensor types
class SensorType:
    """Sensor types."""

    CURRENT = "current_price"
    NEXT = "next_interval_price"
    DAY_AVG = "day_average_price"
    PEAK = "peak_price"
    OFF_PEAK = "off_peak_price"
    TOMORROW_AVG = "tomorrow_average_price"
    TOMORROW_PEAK = "tomorrow_peak_price"
    TOMORROW_OFF_PEAK = "tomorrow_off_peak_price"

    ALL = [
        CURRENT,
        NEXT,
        DAY_AVG,
        PEAK,
        OFF_PEAK,
        TOMORROW_AVG,
        TOMORROW_PEAK,
        TOMORROW_OFF_PEAK,
    ]
