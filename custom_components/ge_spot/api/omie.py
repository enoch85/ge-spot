"""OMIE API client."""
import logging
from datetime import datetime, timedelta, timezone
import aiohttp
from typing import Dict, Any, Optional, List

from .base.base_price_api import BasePriceAPI
from .parsers.omie_parser import OmieParser
from ..const.sources import Source
from ..const.api import Omie
from ..utils.api_client import ApiClient
from ..utils.date_range import generate_date_ranges
from ..const.network import Network
from ..const.currencies import Currency

_LOGGER = logging.getLogger(__name__)

class OmieAPI(BasePriceAPI):
    """OMIE API client."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, session: Optional[aiohttp.ClientSession] = None, timezone_service=None):
        """Initialize the API client.

        Args:
            config: Configuration dictionary
            session: aiohttp client session
            timezone_service: Timezone service instance
        """
        super().__init__(config, session, timezone_service)

    def _get_source_type(self) -> str:
        """Get the source type for this API.

        Returns:
            Source type string
        """
        return Source.OMIE

    def _get_base_url(self) -> str:
        """Get the base URL for API requests.

        Returns:
            Base URL string
        """
        # Use constant defined in const/api.py if available, otherwise fallback
        return getattr(Omie, 'BASE_URL', "https://api.esios.ree.es/archives/70/download?date=")

    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> Dict[str, Any]:
        """Fetch raw price data from OMIE (ESIOS).

        Args:
            area: Area code (e.g., "ES", "PT")
            session: Optional session for API requests
            **kwargs: Additional parameters (expects 'reference_time')

        Returns:
            Dictionary containing raw CSV data for relevant dates (e.g., {"today_csv": "...", "tomorrow_csv": "..."})
        """
        reference_time = kwargs.get('reference_time')
        if not reference_time:
            reference_time = datetime.now(timezone.utc)

        _LOGGER.debug(f"Fetching OMIE prices for {area} around {reference_time.isoformat()}")

        client = ApiClient(session=session or self.session)
        raw_data_by_date = {}

        # Determine which dates to fetch based on reference time
        # OMIE/ESIOS provides day-ahead prices, usually available in the afternoon.
        # We need today's prices and potentially tomorrow's.
        date_ranges = generate_date_ranges(reference_time, self._get_source_type())

        # Extract unique dates needed from the ranges
        dates_to_fetch = set()
        for start_date, end_date in date_ranges:
            # ESIOS API uses the date parameter for the *delivery* date
            dates_to_fetch.add(start_date.date())
            # Fetch up to the end date (inclusive, as range is typically start_date to start_date + 1 day)
            current_date = start_date.date()
            while current_date <= end_date.date():
                 dates_to_fetch.add(current_date)
                 current_date += timedelta(days=1)

        # Fetch data for each required date
        for fetch_date in sorted(list(dates_to_fetch)):
            formatted_date = fetch_date.strftime("%Y-%m-%d")
            url = f"{self._get_base_url()}{formatted_date}"
            _LOGGER.debug(f"Fetching OMIE data for date {formatted_date} from {url}")

            try:
                # Fetch as text (CSV)
                csv_data = await client.fetch(
                    url,
                    timeout=Network.Defaults.TIMEOUT,
                    response_format='text'
                )

                if csv_data and isinstance(csv_data, str):
                    # Store raw CSV keyed by date string
                    raw_data_by_date[formatted_date] = csv_data
                    _LOGGER.debug(f"Successfully fetched OMIE data for {formatted_date}")
                else:
                    _LOGGER.warning(f"No OMIE data returned for {formatted_date}. Response: {csv_data}")

            except Exception as e:
                # Log error but continue trying other dates if possible
                _LOGGER.error(f"Error fetching OMIE data for {formatted_date}: {e}", exc_info=True)
                # Optionally store the error per date if needed for parsing logic
                # raw_data_by_date[formatted_date] = {"error": str(e)}

        # Close client only if session was not provided externally
        if session is None and client:
            await client.close()

        if not raw_data_by_date:
            _LOGGER.error(f"Failed to fetch any OMIE data for area {area} around {reference_time.isoformat()}")
            # Raise an error if absolutely no data could be fetched for any date
            raise ValueError(f"Could not retrieve OMIE data for area {area}")

        # Return the dictionary of raw CSV strings keyed by date
        return {
            "raw_csv_by_date": raw_data_by_date,
            "source": self._get_source_type(),
            "area": area # Include area for context in parser if needed
        }

    async def parse_raw_data(self, raw_data: Any) -> Dict[str, Any]:
        """Parse raw price data from OMIE.

        Args:
            raw_data: Dictionary containing raw CSV data keyed by date string
                      (output of fetch_raw_data, e.g., {"raw_csv_by_date": {...}})

        Returns:
            Parsed price data in standardized format.
        """
        if not isinstance(raw_data, dict) or "raw_csv_by_date" not in raw_data:
            _LOGGER.error(f"Invalid raw_data structure passed to OMIE parser: {type(raw_data)}")
            return {"error": "Invalid raw_data structure for OMIE parser"}

        raw_csv_by_date = raw_data.get("raw_csv_by_date", {})
        area = raw_data.get("area", "ES") # Get area from raw_data or default
        _LOGGER.debug(f"Parsing OMIE data for {area} from {len(raw_csv_by_date)} date(s)")

        parser = self.get_parser_for_area(area)
        combined_hourly_prices = {}
        all_metadata = [] # Collect metadata from each parsed file if needed

        # Parse CSV data for each date
        for date_str, csv_content in raw_csv_by_date.items():
            if isinstance(csv_content, str) and csv_content.strip():
                try:
                    # Pass the single CSV string to the parser
                    # The parser needs to handle extracting data for the specific date from the CSV
                    parsed_for_date = parser.parse({"raw_data": csv_content, "target_date": date_str})

                    if parsed_for_date and "hourly_prices" in parsed_for_date:
                        combined_hourly_prices.update(parsed_for_date["hourly_prices"])
                        if "metadata" in parsed_for_date:
                            all_metadata.append(parsed_for_date["metadata"])
                        _LOGGER.debug(f"Parsed {len(parsed_for_date['hourly_prices'])} prices from OMIE data for {date_str}")
                    else:
                         _LOGGER.warning(f"OMIE parser returned no prices for date {date_str}")
                except Exception as e:
                    _LOGGER.error(f"Error parsing OMIE CSV data for date {date_str}: {e}", exc_info=True)
            else:
                 _LOGGER.warning(f"Skipping empty or invalid CSV content for date {date_str}")

        # Consolidate metadata (simple approach: use first entry's currency/timezone if available)
        final_currency = Currency.EUR # OMIE is EUR
        final_timezone = self.get_timezone_for_area(area)
        # Could potentially extract more metadata if the parser provides it

        # Build the final standardized result
        result = {
            "hourly_prices": combined_hourly_prices,
            "currency": final_currency,
            "api_timezone": final_timezone,
            "source": self._get_source_type(),
            "area": area,
            # Optionally include combined raw data or metadata summary
            # "raw_data_summary": {date: len(csv) for date, csv in raw_csv_by_date.items()},
            # "metadata_summary": all_metadata
        }

        if not combined_hourly_prices:
             _LOGGER.warning(f"OMIE parsing resulted in empty hourly_prices for area {area}")
             # Optionally add an error/warning flag to the result
             # result["warning"] = "Parsing yielded no price data"

        return result

    def get_timezone_for_area(self, area: str) -> str:
        """Get the timezone for a specific area.

        Args:
            area: Area code

        Returns:
            Timezone string
        """
        if area and area.upper() == "PT": # Check area explicitly
            return "Europe/Lisbon"
        else:
            # Default to Madrid timezone for ES or unspecified
            return "Europe/Madrid"

    def get_parser_for_area(self, area: str) -> Any:
        """Get the appropriate parser for the area.

        Args:
            area: Area code

        Returns:
            Parser instance
        """
        # OMIE parser might be generic, or could potentially adapt based on area if needed
        return OmieParser()
