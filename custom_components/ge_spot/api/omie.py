"""OMIE API client."""
import logging
from datetime import datetime, timedelta
import aiohttp
from typing import Dict, Any, Optional, List

from ..timezone.timezone_utils import get_timezone_by_name
from .base.base_price_api import BasePriceAPI
from .parsers.omie_parser import OmieParser
from ..const.sources import Source

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.esios.ree.es/archives/70/download?date="

class OmieAPI(BasePriceAPI):
    """OMIE API client."""

    def __init__(self, session: aiohttp.ClientSession):
        """Initialize the API client.
        
        Args:
            session: aiohttp client session
        """
        super().__init__(session)
        self.parser = OmieParser()

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
        return BASE_URL

    async def fetch_raw_data(self, area: str, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Fetch raw price data from OMIE.
        
        Args:
            area: Area code (e.g., "ES", "PT")
            start_date: Start date for price data
            end_date: End date for price data
            
        Returns:
            Raw API response data
        """
        _LOGGER.debug(f"Fetching OMIE prices for {area} from {start_date} to {end_date}")
        
        try:
            # OMIE API typically provides data for a specific date
            result = await self._fetch_data(area, start_date, end_date)
            return result
        except Exception as e:
            _LOGGER.error(f"Error fetching OMIE prices: {e}")
            return {
                "error": str(e),
                "source": self._get_source_type(),
                "area": area
            }

    async def parse_raw_data(self, raw_data: Dict[str, Any], area: str) -> Dict[str, Any]:
        """Parse raw price data from OMIE.
        
        Args:
            raw_data: Raw API response data
            area: Area code
            
        Returns:
            Parsed price data
        """
        if "error" in raw_data:
            return raw_data

        _LOGGER.debug(f"Parsing OMIE data for {area}")
        
        try:
            # Extract metadata
            metadata = self.parser.extract_metadata(raw_data)
            
            # Parse the data using the OmieParser
            result = self.parser.parse(raw_data)
            
            # Add area and metadata to result
            result["area"] = area
            result["metadata"] = {
                **metadata,
                "parser_version": "2.0",
                "area": area,
                "source": self._get_source_type()
            }
            
            return result
        except Exception as e:
            _LOGGER.error(f"Error parsing OMIE data: {e}")
            return {
                "error": str(e),
                "source": self._get_source_type(),
                "area": area
            }

    def get_timezone_for_area(self, area: str) -> str:
        """Get the timezone for a specific area.
        
        Args:
            area: Area code
            
        Returns:
            Timezone string
        """
        if area.upper() == "ES":
            return "Europe/Madrid"
        elif area.upper() == "PT":
            return "Europe/Lisbon"
        else:
            # Default to Madrid timezone
            return "Europe/Madrid"

    def get_parser_for_area(self, area: str) -> Any:
        """Get the appropriate parser for the area.
        
        Args:
            area: Area code
            
        Returns:
            Parser instance
        """
        return self.parser

    async def _fetch_data(self, area: str, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Fetch data from OMIE API.
        
        Args:
            area: Area code
            start_date: Start date
            end_date: End date
            
        Returns:
            Raw API response data
        """
        # Generate dates to fetch (OMIE typically requires one request per date)
        dates = []
        current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        while current_date <= end_date:
            dates.append(current_date)
            current_date += timedelta(days=1)
        
        # OMIE typically provides data in CSV format
        # We'll fetch data for each date and combine the results
        combined_raw_data = ""
        
        for date in dates:
            formatted_date = date.strftime("%Y-%m-%d")
            url = f"{self._get_base_url()}{formatted_date}"
            
            _LOGGER.debug(f"Fetching OMIE data for {formatted_date} from {url}")
            
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        csv_data = await response.text()
                        
                        # If this is the first data we're fetching, keep any headers
                        # Otherwise, we might want to skip headers to avoid duplicates
                        if not combined_raw_data:
                            combined_raw_data = csv_data
                        else:
                            # Skip header row for subsequent data
                            # This is a simple approach; might need refinement based on actual CSV format
                            lines = csv_data.strip().split('\n')
                            if len(lines) > 1:
                                combined_raw_data += '\n' + '\n'.join(lines[1:])
                    else:
                        _LOGGER.warning(f"Failed to fetch OMIE data for {formatted_date}: HTTP {response.status}")
            except Exception as e:
                _LOGGER.error(f"Error fetching OMIE data for {formatted_date}: {e}")
        
        return {
            "raw_data": combined_raw_data,
            "source": self._get_source_type(),
            "area": area,
            "target_date": start_date.strftime("%Y-%m-%d"),
            "url": f"{self._get_base_url()}{start_date.strftime('%Y-%m-%d')}"
        }
