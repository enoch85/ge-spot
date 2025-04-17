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

    # List of all sources
    ALL = [
        NORDPOOL,
        ENTSOE,
        ENERGI_DATA_SERVICE,
        AEMO,
        EPEX,
        OMIE,
        STROMLIGNING,
        COMED
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
        COMED: "ComEd Hourly Pricing"
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
        COMED: "https://hourlypricing.comed.com/"
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
