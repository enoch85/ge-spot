"""Update interval constants for different API sources."""

from .sources import Source


class SourceIntervals:
    """Source-specific update intervals."""

    # Source-specific update intervals (in minutes)
    INTERVALS = {
        Source.AEMO: 5,  # Every 5 minutes for real-time AEMO data
        Source.ENTSOE: 360,  # Every 6 hours for ENTSO-E
        Source.NORDPOOL: 1440,  # Every 24 hours
        Source.ENERGI_DATA_SERVICE: 1440,
        Source.ENERGY_CHARTS: 15,  # Native 15-minute data updates
        Source.OMIE: 1440,
        Source.STROMLIGNING: 1440,
    }

    # Default interval if source not specified
    DEFAULT_INTERVAL = 1440  # 24 hours

    @staticmethod
    def get_interval(source: str) -> int:
        """Get update interval for a specific source.

        Args:
            source: Source identifier

        Returns:
            Update interval in minutes
        """
        return SourceIntervals.INTERVALS.get(source, SourceIntervals.DEFAULT_INTERVAL)
