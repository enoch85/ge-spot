"""Sensor constants for GE-Spot integration."""

# Sensor types
class SensorType:
    """Sensor types."""
    CURRENT = "current_price"
    NEXT = "next_hour_price"
    DAY_AVG = "day_average_price"
    PEAK = "peak_price"
    OFF_PEAK = "off_peak_price"
    TOMORROW_AVG = "tomorrow_average_price"
    TOMORROW_PEAK = "tomorrow_peak_price"
    TOMORROW_OFF_PEAK = "tomorrow_off_peak_price"

    ALL = [
        CURRENT, NEXT, DAY_AVG, PEAK, OFF_PEAK,
        TOMORROW_AVG, TOMORROW_PEAK, TOMORROW_OFF_PEAK
    ]


# For backward compatibility - direct constants
SENSOR_TYPE_CURRENT = SensorType.CURRENT
SENSOR_TYPE_NEXT = SensorType.NEXT
SENSOR_TYPE_DAY_AVG = SensorType.DAY_AVG
SENSOR_TYPE_PEAK = SensorType.PEAK
SENSOR_TYPE_OFF_PEAK = SensorType.OFF_PEAK
SENSOR_TYPE_TOMORROW_AVG = SensorType.TOMORROW_AVG
SENSOR_TYPE_TOMORROW_PEAK = SensorType.TOMORROW_PEAK
SENSOR_TYPE_TOMORROW_OFF_PEAK = SensorType.TOMORROW_OFF_PEAK
