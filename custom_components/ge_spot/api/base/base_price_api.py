"""Base price API interface for standardizing price source implementations."""
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Union

from homeassistant.core import HomeAssistant

from ...utils.api_client import ApiClient
from ...const.sources import Source
from ...const.time import TimeFormat
from ...utils.date_range import generate_date_ranges

_LOGGER = logging.getLogger(__name__)

class BasePriceAPI(ABC):
    """Abstract base class for all price APIs."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, session=None):
        """Initialize the API.
        
        Args:
            config: Configuration dictionary
            session: Optional session for API requests
        """
        self.config = config or {}
        self.session = session
        self.source_type = self._get_source_type()
        self.base_url = self._get_base_url()
        self.client = None

    @abstractmethod
    def _get_source_type(self) -> str:
        """Get the source type identifier.
        
        Returns:
            Source type identifier
        """
        pass
    
    @abstractmethod
    def _get_base_url(self) -> str:
        """Get the base URL for the API.
        
        Returns:
            Base URL as string
        """
        pass
    
    @abstractmethod
    async def fetch_raw_data(self, area: str, session=None, **kwargs) -> List[Dict[str, Any]]:
        """Fetch raw price data for the given area.
        
        Args:
            area: Area code
            session: Optional session for API requests
            **kwargs: Additional parameters
            
        Returns:
            List of standardized price data dictionaries
        """
        pass
    
    @abstractmethod
    async def parse_raw_data(self, raw_data: Any) -> Dict[str, Any]:
        """Parse raw data into standardized format.
        
        Args:
            raw_data: Raw data from API
            
        Returns:
            Parsed data in standardized format
        """
        pass
    
    async def fetch_day_ahead_prices(self, area=None):
        try:
            if not self.timezone_service:
                raise ValueError("timezone_service is not initialized")
            target_timezone = self.timezone_service.get_target_timezone()
            
            _LOGGER.debug(f"{self.source_type}: Fetching day-ahead prices for area {area}")
            
            # Get source timezone for this area
            source_timezone = self.get_timezone_for_area(area)
            
            # Fetch raw data
            raw_data = await self.fetch_raw_data(area, reference_time, **kwargs)
            if not raw_data:
                _LOGGER.warning(f"{self.source_type}: No data returned for area {area}")
                return {}
                
            # Create parser with our timezone service
            parser = self.get_parser_for_area(area)
            
            # Parse raw data
            parsed_data = parser.parse(raw_data)
            
            # Add area and timezone info - Keep simple metadata, avoid processing
            parsed_data["area"] = area
            if source_timezone:
                 parsed_data["api_timezone"] = str(source_timezone)
            # target_timezone might not be needed here anymore if normalization is central
            # parsed_data["target_timezone"] = str(target_timezone) 
            
            # REMOVED: Timezone normalization block
            # REMOVED: _calculate_current_next_hour call
            # REMOVED: _calculate_statistics call
            # REMOVED: metadata extraction (can be done later if needed)
            
            # Ensure basic structure exists even if parser returns None/empty
            if not parsed_data:
                 parsed_data = {}
            if "hourly_prices" not in parsed_data:
                 parsed_data["hourly_prices"] = {}
            if "currency" not in parsed_data:
                 # Attempt to get currency from kwargs or default
                 parsed_data["currency"] = kwargs.get("currency", "EUR") # Default assumption
            
            # Add source type
            parsed_data["source"] = self.source_type

            _LOGGER.debug(f"Returning minimally processed data from {self.source_type}: {parsed_data.keys()}")
            return parsed_data
            
        except Exception as e:
            _LOGGER.error(f"Error in fetch_day_ahead_prices for {self.source_type}: {str(e)}", exc_info=True)
            # Return a structured empty dict on error
            return {
                "source": self.source_type,
                "area": area,
                "currency": currency,
                "hourly_prices": {},
                "error": str(e)
            }
    
    # --- Methods required by subclasses (as per PARSER_UPDATES.md) ---
    @abstractmethod
    def get_timezone_for_area(self, area: str) -> Any:
        """Get the source timezone for the specified area.
        
        Args:
            area: Area code
            
        Returns:
            Timezone object or identifier string for the area
        """
        pass
        
    @abstractmethod
    def get_parser_for_area(self, area: str) -> Any:
        """Get the appropriate parser instance for the specified area.
        
        Args:
            area: Area code
            
        Returns:
            Parser instance for the area
        """
        pass
    # --- END Required Methods ---

    # --- REMOVED UNUSED HELPER METHODS --- 
    # _calculate_current_next_hour - Logic moved to DataProcessor
    # _calculate_statistics - Logic moved to DataProcessor
    # _validate_complete_day_data - Logic moved to DataProcessor
    # _extract_prices_for_date - Logic moved to DataProcessor
    # _calculate_peak_hours - Logic moved to DataProcessor (or could be added there if needed)
    # _calculate_off_peak_hours - Logic moved to DataProcessor (or could be added there if needed)
    # get_timezone_for_area - Logic handled by TimezoneService
    # get_parser_for_area - Parsers instantiated in subclasses
    # --- END REMOVED METHODS --- 

    def get_timezone_for_area(self, area: str) -> Any:
        """Get the source timezone for the specified area.
        
        Args:
            area: Area code
            
        Returns:
            Timezone object for the area
        """
        # Use TimezoneService to get the area-specific timezone if possible
        if self.timezone_service:
            area_timezone = self.timezone_service.get_area_timezone(area)
            if area_timezone:
                return area_timezone
        
        # Fallback to UTC
        _LOGGER.debug(f"No specific timezone found for area {area}, using UTC")
        return timezone.utc
        
    def get_parser_for_area(self, area: str) -> Any:
        """Get the appropriate parser for the specified area.
        
        Args:
            area: Area code
            
        Returns:
            Parser instance for the area
        """
        # Import here to avoid circular imports
        from ..parsers import get_parser_for_source
        
        # Create parser with our timezone service
        return get_parser_for_source(self.source_type, self.timezone_service)