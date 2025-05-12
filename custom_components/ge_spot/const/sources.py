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
    AWATTAR = "awattar"  # Added
    EPEX_SPOT_WEB = "epex_spot_web"
    ENERGY_FORECAST = "energy_forecast"
    SMARD = "smard"
    TIBBER = "tibber"
    SMART_ENERGY = "smart_energy"

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
        AMBER,
        AWATTAR,
        EPEX_SPOT_WEB,
        ENERGY_FORECAST,
        SMARD,
        TIBBER,
        SMART_ENERGY
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
        COMED,
        AWATTAR,  # Added
        EPEX_SPOT_WEB, # Added
        ENERGY_FORECAST, # Added
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
        AMBER: "Amber Electric",
        AWATTAR: "aWATTar",
        EPEX_SPOT_WEB: "EPEX SPOT Web", # Added
        ENERGY_FORECAST: "Energy Forecast", # Added
        SMARD: "SMARD",
        TIBBER: "Tibber",
        SMART_ENERGY: "Smart Energy"
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
        AMBER: "https://amber.com.au/",
        AWATTAR: "https://www.awattar.com/",
        EPEX_SPOT_WEB: "https://www.epexspot.com/en/market-data/", # Added
        ENERGY_FORECAST: "https://www.energyforecast.eu/", # Added
        SMARD: "https://www.smard.de/",
        TIBBER: "https://tibber.com/",
        SMART_ENERGY: "https://www.smartenergy.com/"
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

# Add individual source constants at module level, referencing them via the class
SOURCE_NORDPOOL = Source.NORDPOOL
SOURCE_ENTSOE = Source.ENTSOE
SOURCE_ENERGI_DATA_SERVICE = Source.ENERGI_DATA_SERVICE
SOURCE_AEMO = Source.AEMO
SOURCE_EPEX = Source.EPEX
SOURCE_OMIE = Source.OMIE
SOURCE_STROMLIGNING = Source.STROMLIGNING
SOURCE_COMED = Source.COMED
SOURCE_AMBER = Source.AMBER
SOURCE_AWATTAR = Source.AWATTAR
SOURCE_EPEX_SPOT_WEB = Source.EPEX_SPOT_WEB
SOURCE_ENERGY_FORECAST = Source.ENERGY_FORECAST
SOURCE_SMARD = Source.SMARD
SOURCE_TIBBER = Source.TIBBER
SOURCE_SMART_ENERGY = Source.SMART_ENERGY

class SourceInfo:
    """Utility class for source information."""

    # Map source to supported areas
    SOURCE_AREAS = {
        Source.NORDPOOL: [
            "DK1", "DK2", "FI", "SE1", "SE2", "SE3", "SE4",
            "NO1", "NO2", "NO3", "NO4", "NO5", "EE", "LV", "LT"
        ],
        Source.ENTSOE: [ # ENTSO-E is very broad
            "AL", "AT", "BA", "BE", "BG", "CH", "CY", "CZ", "DE-AT-LU", "DE-LU", 
            "DK1", "DK2", "EE", "ES", "FI", "FR", "GB", "GB-NIR", "GR", "HR", 
            "HU", "IE", "IT", "IT-BRNN", "IT-CNOR", "IT-CSUD", "IT-FOGN", 
            "IT-GR", "IT-MALTA", "IT-NORD", "IT-NORD-AT", "IT-NORD-CH", "IT-NORD-FR", 
            "IT-NORD-SI", "IT-PRGP", "IT-ROSN", "IT-SARD", "IT-SICI", "IT-SUD", 
            "LT", "LU", "LV", "ME", "MK", "MT", "NL", "NO1", "NO2", "NO3", "NO4", "NO5", 
            "PL", "PT", "RO", "RS", "SE1", "SE2", "SE3", "SE4", "SI", "SK", "UA", "XK"
            # Note: Some ENTSO-E areas might be too granular or specific for general use.
            # We list common ones and those seen in other configs. DE-LU is preferred over DE-AT-LU if both exist.
        ],
        Source.ENERGI_DATA_SERVICE: ["DK1", "DK2"],
        Source.EPEX: ["DE-LU", "FR", "BE", "NL", "AT", "CH", "GB"], # Added CH, GB based on EPEX offerings
        Source.OMIE: ["ES", "PT"],
        Source.AEMO: ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"], # Australia
        Source.STROMLIGNING: ["DK1", "DK2"], # Norway, but data for DK
        Source.COMED: ["COMED"], # USA
        Source.AMBER: ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"], # Australia
        Source.AWATTAR: ["AT", "DE-LU"],
        Source.EPEX_SPOT_WEB: [
            "AT", "BE", "CH", "DE-LU", "DK1", "DK2", "FI", "FR", "GB", "NL",
            "NO1", "NO2", "NO3", "NO4", "NO5", "PL",
            "SE1", "SE2", "SE3", "SE4"
        ],
        Source.ENERGY_FORECAST: ["DE-LU"], # Primarily Germany
        Source.SMARD: [
            "DE-LU", "AT", "BE", "DK1", "DK2", "FR", "NL", "NO2", "PL",
            "CH", "SI", "CZ", "HU", "IT-NO" # IT-NO is specific for SMARD's Italy North
        ],
        Source.TIBBER: [ # Token-dependent, but these are known supported/potential areas
            "DE-LU", "NL", "NO1", "NO2", "NO3", "NO4", "NO5",
            "SE1", "SE2", "SE3", "SE4", "AT", "BE", "FR", # Added AT, BE, FR as potential
            "NSW1", "QLD1", "SA1", "TAS1", "VIC1" # Australia
        ],
        Source.SMART_ENERGY: ["AT", "DE-LU"] # Austria and Germany
    }

    # Map areas to recommended sources
    # The order in the list defines priority for get_default_source_for_area
    AREA_RECOMMENDED_SOURCES = {
        # Nordic countries
        "DK1": list(set([Source.NORDPOOL, Source.ENTSOE, Source.ENERGI_DATA_SERVICE, Source.STROMLIGNING, Source.EPEX_SPOT_WEB, Source.ENERGY_FORECAST, Source.SMARD])),
        "DK2": list(set([Source.NORDPOOL, Source.ENTSOE, Source.ENERGI_DATA_SERVICE, Source.STROMLIGNING, Source.EPEX_SPOT_WEB, Source.ENERGY_FORECAST, Source.SMARD])),
        "SE1": list(set([Source.NORDPOOL, Source.ENTSOE, Source.EPEX_SPOT_WEB, Source.TIBBER])),
        "SE2": list(set([Source.NORDPOOL, Source.ENTSOE, Source.EPEX_SPOT_WEB, Source.TIBBER])),
        "SE3": list(set([Source.NORDPOOL, Source.ENTSOE, Source.EPEX_SPOT_WEB, Source.TIBBER])),
        "SE4": list(set([Source.NORDPOOL, Source.ENTSOE, Source.EPEX_SPOT_WEB, Source.TIBBER])),
        "FI": list(set([Source.NORDPOOL, Source.ENTSOE, Source.EPEX_SPOT_WEB])),
        "NO1": list(set([Source.NORDPOOL, Source.ENTSOE, Source.EPEX_SPOT_WEB, Source.TIBBER])),
        "NO2": list(set([Source.NORDPOOL, Source.ENTSOE, Source.EPEX_SPOT_WEB, Source.TIBBER, Source.SMARD])),
        "NO3": list(set([Source.NORDPOOL, Source.ENTSOE, Source.EPEX_SPOT_WEB, Source.TIBBER])),
        "NO4": list(set([Source.NORDPOOL, Source.ENTSOE, Source.EPEX_SPOT_WEB, Source.TIBBER])),
        "NO5": list(set([Source.NORDPOOL, Source.ENTSOE, Source.EPEX_SPOT_WEB, Source.TIBBER])),
        "EE": list(set([Source.NORDPOOL, Source.ENTSOE])),
        "LT": list(set([Source.NORDPOOL, Source.ENTSOE])),
        "LV": list(set([Source.NORDPOOL, Source.ENTSOE])),

        # Central Europe
        "DE-LU": list(set([Source.ENTSOE, Source.EPEX, Source.AWATTAR, Source.EPEX_SPOT_WEB, Source.ENERGY_FORECAST, Source.SMARD, Source.TIBBER, Source.SMART_ENERGY])),
        "AT": list(set([Source.ENTSOE, Source.EPEX, Source.AWATTAR, Source.EPEX_SPOT_WEB, Source.ENERGY_FORECAST, Source.SMARD, Source.SMART_ENERGY])),
        "FR": list(set([Source.ENTSOE, Source.EPEX, Source.EPEX_SPOT_WEB, Source.ENERGY_FORECAST, Source.SMARD])),
        "BE": list(set([Source.ENTSOE, Source.EPEX, Source.EPEX_SPOT_WEB, Source.ENERGY_FORECAST, Source.SMARD])),
        "NL": list(set([Source.ENTSOE, Source.EPEX, Source.EPEX_SPOT_WEB, Source.ENERGY_FORECAST, Source.SMARD, Source.TIBBER])),
        "CH": list(set([Source.ENTSOE, Source.EPEX_SPOT_WEB, Source.SMARD])),
        "PL": list(set([Source.ENTSOE, Source.EPEX_SPOT_WEB, Source.SMARD])),

        # Southern Europe
        "ES": list(set([Source.ENTSOE, Source.OMIE])),
        "PT": list(set([Source.ENTSOE, Source.OMIE])),
        "IT": list(set([Source.ENTSOE, Source.SMARD])), # Added for IT (SMARD for IT-NO)
        "SI": list(set([Source.ENTSOE, Source.SMARD])), # Added for SI
        "HR": list(set([Source.ENTSOE])), # Added for HR
        "GR": list(set([Source.ENTSOE])), # Added for GR

        # Other European countries
        "CZ": list(set([Source.ENTSOE, Source.SMARD])), # Added for CZ
        "SK": list(set([Source.ENTSOE])),             # Added for SK
        "HU": list(set([Source.ENTSOE, Source.SMARD])), # Added for HU
        "RO": list(set([Source.ENTSOE])),             # Added for RO
        "BG": list(set([Source.ENTSOE])),             # Added for BG

        # Australia
        "NSW1": list(set([Source.AEMO, Source.AMBER, Source.TIBBER])), # Corrected: Removed SMART_ENERGY
        "QLD1": list(set([Source.AEMO, Source.AMBER, Source.TIBBER])), # Corrected: Removed SMART_ENERGY
        "SA1": list(set([Source.AEMO, Source.AMBER, Source.TIBBER])),  # Corrected: Removed SMART_ENERGY
        "TAS1": list(set([Source.AEMO, Source.AMBER, Source.TIBBER])), # Corrected: Removed SMART_ENERGY
        "VIC1": list(set([Source.AEMO, Source.AMBER, Source.TIBBER])), # Corrected: Removed SMART_ENERGY

        # USA
        "COMED": [Source.COMED], # Kept as is, assuming list(set()) not strictly needed for single item
        # GB
        "GB": list(set([Source.EPEX_SPOT_WEB])),
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
