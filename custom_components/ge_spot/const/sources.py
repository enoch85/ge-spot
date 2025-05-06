"""Constants for API sources."""

class Source:
    """Constants for API sources."""

    NORDPOOL = "nordpool"
    ENTSOE = "entsoe"
    ENERGI_DATA_SERVICE = "energi_data_service"
    AEMO = "aemo"
    EPEX = "epex"
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
        EPEX,
        OMIE,
        STROMLIGNING,
        COMED,
        AMBER
    ]

    # Default source priority
    DEFAULT_PRIORITY = [
        NORDPOOL,
        ENTSOE,
        ENERGI_DATA_SERVICE,
        EPEX,
        OMIE,
        STROMLIGNING,
        AEMO,
        AMBER,
        COMED
    ]

    # Source display names
    DISPLAY_NAMES = {
        NORDPOOL: "Nord Pool",
        ENTSOE: "ENTSO-E",
        ENERGI_DATA_SERVICE: "Energi Data Service",
        AEMO: "AEMO",
        EPEX: "EPEX SPOT",
        OMIE: "OMIE",
        STROMLIGNING: "Strømligning",
        COMED: "ComEd Hourly Pricing",
        AMBER: "Amber Electric"
    }

    # Source URLs
    URLS = {
        NORDPOOL: "https://www.nordpoolgroup.com/",
        ENTSOE: "https://transparency.entsoe.eu/",
        ENERGI_DATA_SERVICE: "https://www.energidataservice.dk/",
        AEMO: "https://aemo.com.au/",
        EPEX: "https://www.epexspot.com/",
        OMIE: "https://www.omie.es/",
        STROMLIGNING: "https://www.stromligning.no/",
        COMED: "https://hourlypricing.comed.com/",
        AMBER: "https://amber.com.au/"
    }

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
    def get_url(source: str) -> str:
        """Get URL for a source.

        Args:
            source: Source identifier

        Returns:
            URL
        """
        return Source.URLS.get(source, "")

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
            "DK1", "DK2", "FI", "SE1", "SE2", "SE3", "SE4",
            "NO1", "NO2", "NO3", "NO4", "NO5", "EE", "LV", "LT"
        ],
        Source.ENTSOE: [
            "DK1", "DK2", "FI", "SE1", "SE2", "SE3", "SE4",
            "NO1", "NO2", "NO3", "NO4", "NO5", "EE", "LV", "LT",
            "AT", "BE", "DE-LU", "ES", "FR", "NL", "PT", "CH",
            "IT", "SI", "HR", "GR", "PL", "CZ", "SK", "HU", "RO", "BG"
        ],
        Source.ENERGI_DATA_SERVICE: ["DK1", "DK2"],
        Source.EPEX: ["DE-LU", "FR", "BE", "NL", "AT"],
        Source.OMIE: ["ES", "PT"],
        Source.AEMO: ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"],
        Source.STROMLIGNING: ["DK1", "DK2"],
        Source.COMED: ["COMED"],
        Source.AMBER: ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]
    }

    # Map areas to recommended sources
    AREA_RECOMMENDED_SOURCES = {
        # Nordic countries
        "DK1": [Source.NORDPOOL, Source.ENTSOE, Source.ENERGI_DATA_SERVICE, Source.STROMLIGNING],
        "DK2": [Source.NORDPOOL, Source.ENTSOE, Source.ENERGI_DATA_SERVICE, Source.STROMLIGNING],
        "SE1": [Source.NORDPOOL, Source.ENTSOE],
        "SE2": [Source.NORDPOOL, Source.ENTSOE],
        "SE3": [Source.NORDPOOL, Source.ENTSOE],
        "SE4": [Source.NORDPOOL, Source.ENTSOE],
        "FI": [Source.NORDPOOL, Source.ENTSOE],
        "NO1": [Source.NORDPOOL, Source.ENTSOE],
        "NO2": [Source.NORDPOOL, Source.ENTSOE],
        "NO3": [Source.NORDPOOL, Source.ENTSOE],
        "NO4": [Source.NORDPOOL, Source.ENTSOE],
        "NO5": [Source.NORDPOOL, Source.ENTSOE],
        "EE": [Source.NORDPOOL, Source.ENTSOE],
        "LT": [Source.NORDPOOL, Source.ENTSOE],
        "LV": [Source.NORDPOOL, Source.ENTSOE],

        # Central Europe
        "DE-LU": [Source.ENTSOE, Source.EPEX],
        "AT": [Source.ENTSOE, Source.EPEX],
        "FR": [Source.ENTSOE, Source.EPEX],
        "BE": [Source.ENTSOE, Source.EPEX],
        "NL": [Source.ENTSOE, Source.EPEX],

        # Southern Europe
        "ES": [Source.ENTSOE, Source.OMIE],
        "PT": [Source.ENTSOE, Source.OMIE],

        # Australia
        "NSW1": [Source.AEMO, Source.AMBER],
        "QLD1": [Source.AEMO, Source.AMBER],
        "SA1": [Source.AEMO, Source.AMBER],
        "TAS1": [Source.AEMO, Source.AMBER],
        "VIC1": [Source.AEMO, Source.AMBER],

        # USA
        "COMED": [Source.COMED]
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
