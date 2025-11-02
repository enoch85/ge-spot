"""Constants for API sources."""


class Source:
    """Constants for API sources."""

    NORDPOOL = "nordpool"
    ENTSOE = "entsoe"
    ENERGI_DATA_SERVICE = "energi_data_service"
    AEMO = "aemo"
    ENERGY_CHARTS = "energy_charts"
    OMIE = "omie"
    STROMLIGNING = "stromligning"
    COMED = "comed"
    AMBER = "amber"

    # List of all sources
    ALL = [
        NORDPOOL,
        ENTSOE,
        ENERGI_DATA_SERVICE,
        AEMO,
        ENERGY_CHARTS,
        OMIE,
        STROMLIGNING,
        COMED,
        AMBER,
    ]

    # Default source priority
    # All sources use same exponential timeout (5s → 15s → 45s)
    # Reliable sources tried first, unreliable sources last
    DEFAULT_PRIORITY = [
        NORDPOOL,
        ENTSOE,
        ENERGI_DATA_SERVICE,
        OMIE,
        STROMLIGNING,
        AEMO,
        AMBER,
        COMED,
        ENERGY_CHARTS,
    ]

    # Source display names
    DISPLAY_NAMES = {
        NORDPOOL: "Nord Pool",
        ENTSOE: "ENTSO-E",
        ENERGI_DATA_SERVICE: "Energi Data Service",
        AEMO: "AEMO",
        ENERGY_CHARTS: "Energy-Charts",
        OMIE: "OMIE",
        STROMLIGNING: "Strømligning",
        COMED: "ComEd Hourly Pricing",
        AMBER: "Amber Electric",
    }

    # Tomorrow data publication times (UTC hour when tomorrow data becomes available)
    # These are approximate times based on market schedules
    # - Nordpool: Day-ahead auction results published around 12:42 CET (~11:42 UTC winter, ~10:42 UTC summer)
    # - ENTSO-E: Similar to Nordpool, around 13:00 CET
    # - Energi Data Service: Based on Nordpool, around 13:00 CET
    # - OMIE: Day-ahead auction results published around 14:00 CET
    # - Energy-Charts: Data aggregation may take longer, around 14:00 CET
    # Using conservative estimates (1-2 hours after typical publication)
    PUBLICATION_TIMES_UTC = {
        NORDPOOL: 13,  # ~13:00 UTC (safe buffer after 12:42 CET)
        ENTSOE: 13,
        ENERGI_DATA_SERVICE: 13,
        OMIE: 14,  # Spanish market publishes slightly later
        STROMLIGNING: 13,
        AEMO: 14,  # Australian market, different schedule
        AMBER: 14,
        COMED: 14,
        ENERGY_CHARTS: 14,
    }

    @staticmethod
    def get_publication_time_utc(source: str) -> int:
        """Get expected UTC hour when tomorrow data becomes available.

        Args:
            source: Source identifier

        Returns:
            UTC hour (0-23) when tomorrow data should be available
        """
        return Source.PUBLICATION_TIMES_UTC.get(source, 14)  # Default to 14:00 UTC

    @staticmethod
    def get_display_name(source: str) -> str:
        """Get display name for a source.

        Args:
            source: Source identifier

        Returns:
            Display name
        """
        return Source.DISPLAY_NAMES.get(source, source)

    @staticmethod
    def is_valid(source: str) -> bool:
        """Check if a source is valid.

        Args:
            source: Source identifier

        Returns:
            True if valid, False otherwise
        """
        return source in Source.ALL


class SourceInfo:
    """Utility class for source information."""

    # Map source to supported areas
    SOURCE_AREAS = {
        Source.NORDPOOL: [
            "DK1",
            "DK2",
            "FI",
            "SE1",
            "SE2",
            "SE3",
            "SE4",
            "NO1",
            "NO2",
            "NO3",
            "NO4",
            "NO5",
            "EE",
            "LV",
            "LT",
        ],
        Source.ENTSOE: [
            "DK1",
            "DK2",
            "FI",
            "SE1",
            "SE2",
            "SE3",
            "SE4",
            "NO1",
            "NO2",
            "NO3",
            "NO4",
            "NO5",
            "EE",
            "LV",
            "LT",
            "AT",
            "BE",
            "DE-LU",
            "ES",
            "FR",
            "NL",
            "PT",
            "CH",
            "IT",
            "SI",
            "HR",
            "GR",
            "PL",
            "CZ",
            "SK",
            "HU",
            "RO",
            "BG",
        ],
        Source.ENERGI_DATA_SERVICE: ["DK1", "DK2"],
        Source.ENERGY_CHARTS: [
            # Nordic regions (13 zones)
            "SE1",
            "SE2",
            "SE3",
            "SE4",
            "NO1",
            "NO2",
            "NO3",
            "NO4",
            "NO5",
            "NO2NSL",
            "DK1",
            "DK2",
            "FI",
            # Baltic states (3 zones)
            "EE",
            "LT",
            "LV",
            # Western Europe (6 zones)
            "DE-LU",
            "FR",
            "NL",
            "BE",
            "AT",
            "CH",
            # Central and Eastern Europe (11 zones)
            "PL",
            "CZ",
            "SK",
            "HU",
            "RO",
            "BG",
            "SI",
            "HR",
            "RS",
            "ME",
            "GR",
            # Italy (6 zones)
            "IT-North",
            "IT-South",
            "IT-Centre-North",
            "IT-Centre-South",
            "IT-Sardinia",
            "IT-Sicily",
            # Iberian Peninsula (2 zones)
            "ES",
            "PT",
        ],
        Source.OMIE: ["ES", "PT"],
        Source.AEMO: ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"],
        Source.STROMLIGNING: ["DK1", "DK2"],
        Source.COMED: ["COMED"],
        Source.AMBER: ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"],
    }

    # Map areas to recommended sources
    AREA_RECOMMENDED_SOURCES = {
        # Nordic countries
        "DK1": [
            Source.NORDPOOL,
            Source.ENTSOE,
            Source.ENERGI_DATA_SERVICE,
            Source.STROMLIGNING,
            Source.ENERGY_CHARTS,
        ],
        "DK2": [
            Source.NORDPOOL,
            Source.ENTSOE,
            Source.ENERGI_DATA_SERVICE,
            Source.STROMLIGNING,
            Source.ENERGY_CHARTS,
        ],
        "SE1": [Source.NORDPOOL, Source.ENTSOE, Source.ENERGY_CHARTS],
        "SE2": [Source.NORDPOOL, Source.ENTSOE, Source.ENERGY_CHARTS],
        "SE3": [Source.NORDPOOL, Source.ENTSOE, Source.ENERGY_CHARTS],
        "SE4": [Source.NORDPOOL, Source.ENTSOE, Source.ENERGY_CHARTS],
        "FI": [Source.NORDPOOL, Source.ENTSOE, Source.ENERGY_CHARTS],
        "NO1": [Source.NORDPOOL, Source.ENTSOE, Source.ENERGY_CHARTS],
        "NO2": [Source.NORDPOOL, Source.ENTSOE, Source.ENERGY_CHARTS],
        "NO3": [Source.NORDPOOL, Source.ENTSOE, Source.ENERGY_CHARTS],
        "NO4": [Source.NORDPOOL, Source.ENTSOE, Source.ENERGY_CHARTS],
        "NO5": [Source.NORDPOOL, Source.ENTSOE, Source.ENERGY_CHARTS],
        "EE": [Source.NORDPOOL, Source.ENTSOE, Source.ENERGY_CHARTS],
        "LT": [Source.NORDPOOL, Source.ENTSOE, Source.ENERGY_CHARTS],
        "LV": [Source.NORDPOOL, Source.ENTSOE, Source.ENERGY_CHARTS],
        # Central Europe
        "DE-LU": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "AT": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "FR": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "BE": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "NL": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "CH": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "PL": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "CZ": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "HU": [Source.ENERGY_CHARTS, Source.ENTSOE],
        # Southern Europe
        "ES": [Source.ENERGY_CHARTS, Source.ENTSOE, Source.OMIE],
        "PT": [Source.ENERGY_CHARTS, Source.ENTSOE, Source.OMIE],
        "SK": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "RO": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "BG": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "SI": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "HR": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "RS": [Source.ENERGY_CHARTS],
        "ME": [Source.ENERGY_CHARTS],
        "GR": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "IT-North": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "IT-South": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "IT-Centre-North": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "IT-Centre-South": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "IT-Sardinia": [Source.ENERGY_CHARTS, Source.ENTSOE],
        "IT-Sicily": [Source.ENERGY_CHARTS, Source.ENTSOE],
        # Australia
        "NSW1": [Source.AEMO, Source.AMBER],
        "QLD1": [Source.AEMO, Source.AMBER],
        "SA1": [Source.AEMO, Source.AMBER],
        "TAS1": [Source.AEMO, Source.AMBER],
        "VIC1": [Source.AEMO, Source.AMBER],
        # USA
        "COMED": [Source.COMED],
    }

    @classmethod
    def get_default_source_for_area(cls, area: str) -> str:
        """Get default source for a specific area.

        Args:
            area: Area code

        Returns:
            Default source for the area or None if not found
        """
        sources = cls.AREA_RECOMMENDED_SOURCES.get(area, [])
        if sources:
            return sources[0]

        # If no recommended sources, find any source that supports this area
        for source, areas in cls.SOURCE_AREAS.items():
            if area in areas:
                return source

        return None

    @classmethod
    def get_sources_for_area(cls, area: str) -> list:
        """Get all sources that support a specific area.

        Args:
            area: Area code

        Returns:
            List of sources that support the area
        """
        return cls.AREA_RECOMMENDED_SOURCES.get(area, [])

    @classmethod
    def get_areas_for_source(cls, source: str) -> list:
        """Get all areas supported by a specific source.

        Args:
            source: Source identifier

        Returns:
            List of areas supported by the source
        """
        return cls.SOURCE_AREAS.get(source, [])
