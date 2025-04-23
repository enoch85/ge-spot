"""Unified Price Manager for ge-spot integration."""
import logging
from datetime import timedelta, datetime, time
from typing import Any, Dict, Optional, List, Type, Union

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import async_track_time_interval

from ..const import DOMAIN
from ..const.config import Config
from ..const.sources import Source
from ..const.intervals import SourceIntervals
from ..const.defaults import Defaults
from ..const.display import DisplayUnit
from ..const.network import Network
from ..const.currencies import Currency
from ..api import get_sources_for_region
from ..api.base.base_price_api import BasePriceAPI
from ..api.base.data_structure import StandardizedPriceData, create_standardized_price_data
from ..api.base.data_fetch import PriceDataFetcher
from ..api.base.session_manager import close_session
from ..timezone import TimezoneService
from ..utils.exchange_service import ExchangeService
from ..utils.rate_limiter import RateLimiter
from .data_processor import DataProcessor

# Import all API implementations here to have them available
from ..api.nordpool import NordpoolAPI
from ..api.entsoe import EntsoeAPI
from ..api.aemo import AemoAPI
from ..api.epex import EpexAPI
from ..api.eds import EdsAPI

_LOGGER = logging.getLogger(__name__)

class UnifiedPriceManager:
    """Unified manager for price data using improved standardized APIs."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        area: str,
        currency: str,
        config: Dict[str, Any],
    ):
        """Initialize the unified price manager.
        
        Args:
            hass: Home Assistant instance
            area: Area code
            currency: Currency code
            config: Configuration dictionary
        """
        self.hass = hass
        self.area = area
        self.currency = currency
        self.config = config
        
        # API sources and tracking
        self._supported_sources = get_sources_for_region(area)
        self._source_priority = config.get(Config.SOURCE_PRIORITY, Source.DEFAULT_PRIORITY)
        self._active_source = None
        self._attempted_sources = []
        self._fallback_sources = []
        self._using_cached_data = False
        
        # Services and utilities
        self._data_fetcher = PriceDataFetcher()
        self._tz_service = TimezoneService(hass, area, config)
        self._exchange_service = ExchangeService(hass, config)
        self._data_processor = DataProcessor(hass, area, currency, config, self._tz_service)
        self._rate_limiter = RateLimiter(f"unified_price_manager_{area}")
        
        # API request tracking
        self._last_api_fetch = None
        self._next_scheduled_fetch = None
        self._last_data = None
        self._consecutive_failures = 0
        
        # Display settings
        self.display_unit = config.get(Config.DISPLAY_UNIT, Defaults.DISPLAY_UNIT)
        self.use_subunit = self.display_unit == DisplayUnit.CENTS
        self.vat_rate = config.get(Config.VAT, Defaults.VAT_RATE) / 100  # Convert from percentage to rate
        self.include_vat = config.get(Config.INCLUDE_VAT, Defaults.INCLUDE_VAT)
        
        # Configure source priorities and API class mappings
        self._configure_sources()
    
    def _configure_sources(self):
        """Configure source priorities and API class mappings."""
        # Filter source_priority to only include supported sources for this area
        self._source_priority = [s for s in self._source_priority if s in self._supported_sources]
        
        # If no sources remain after filtering, use all supported sources for this area
        if not self._source_priority:
            self._source_priority = self._supported_sources
        
        # Map source names to their API classes
        self._source_api_map = {
            Source.NORDPOOL: NordpoolAPI,
            Source.ENTSOE: EntsoeAPI,
            Source.AEMO: AemoAPI,
            Source.EPEX: EpexAPI,
            Source.EDS: EdsAPI,
            # Add other API classes here
        }
        
        # Build ordered list of API classes based on priority
        self._api_classes = []
        for source in self._source_priority:
            if source in self._source_api_map:
                self._api_classes.append(self._source_api_map[source])
        
        _LOGGER.info(f"Configured sources for area {self.area}: {self._source_priority}")
    
    async def fetch_data(self, force: bool = False) -> Dict[str, Any]:
        """Fetch price data considering rate limits and caching.
        
        Args:
            force: Whether to force fetch even if rate limited
            
        Returns:
            Dictionary with processed data
        """
        now = dt_util.now()
        
        # Check rate limiting unless forcing an update
        if not force and self._last_api_fetch:
            # Enforce minimum API call interval
            min_interval = timedelta(minutes=Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES)
            time_since_last_fetch = now - self._last_api_fetch
            
            if time_since_last_fetch < min_interval:
                remaining_seconds = (min_interval - time_since_last_fetch).total_seconds()
                _LOGGER.info(
                    f"Rate limiting in effect for area {self.area}. "
                    f"Next fetch allowed in {remaining_seconds:.1f} seconds. "
                    f"Using cached data."
                )
                
                # Use last data if available
                if self._last_data:
                    return self._last_data
        
        # Fetch data using our unified fetcher with fallback support
        _LOGGER.info(f"Fetching price data for area {self.area}")
        
        # Update API fetch timestamp
        self._last_api_fetch = now
        
        try:
            # Prepare API instances - needed for proper typing
            api_instances = [cls(self.config) for cls in self._api_classes]
            
            # Fetch with fallback
            result = await self._data_fetcher.fetch_with_fallback(
                sources=api_instances,
                area=self.area,
                currency=self.currency,
                reference_time=now,
                config=self.config,
                vat=self.vat_rate if self.include_vat else None,
                include_vat=self.include_vat
            )
            
            if not result:
                _LOGGER.error(f"Failed to fetch data for area {self.area}")
                self._consecutive_failures += 1
                return self._generate_empty_result()
            
            # Reset failure counter on success
            self._consecutive_failures = 0
            
            # Extract tracking info
            self._active_source = result.get("source", "unknown")
            self._attempted_sources = result.get("attempted_sources", [])
            self._fallback_sources = result.get("fallback_sources", [])
            self._using_cached_data = result.get("using_cached_data", False)
            
            # Log result
            _LOGGER.info(
                f"Fetch complete for area {self.area} - "
                f"Source: {self._active_source}, "
                f"Using cached data: {self._using_cached_data}, "
                f"Fallbacks: {self._fallback_sources}"
            )
            
            # Process result data
            processed_data = self._process_result(result)
            
            # Store as last data
            self._last_data = processed_data
            
            return processed_data
        
        except Exception as e:
            _LOGGER.error(f"Error fetching price data for area {self.area}: {e}", exc_info=True)
            self._consecutive_failures += 1
            
            # Use last known data if available, otherwise return empty result
            if self._last_data:
                return self._last_data
            else:
                return self._generate_empty_result()
    
    def _process_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Process raw result data.
        
        Args:
            result: Raw result data
            
        Returns:
            Processed data
        """
        # Basic validation
        if not result or not isinstance(result, dict):
            _LOGGER.error(f"Invalid result for area {self.area}")
            return self._generate_empty_result()
        
        # Use data processor to generate final result
        return self._data_processor.process(result)
    
    def _generate_empty_result(self) -> Dict[str, Any]:
        """Generate an empty result when data is unavailable.
        
        Returns:
            Empty result dictionary
        """
        now = dt_util.now()
        
        # Create empty price data
        empty_data = StandardizedPriceData.create_empty(
            source="None",
            area=self.area, 
            currency=self.currency
        ).to_dict()
        
        # Add metadata about failure
        empty_data.update({
            "attempted_sources": self._attempted_sources,
            "fallback_sources": self._fallback_sources,
            "using_cached_data": self._using_cached_data,
            "consecutive_failures": self._consecutive_failures,
            "last_fetch_attempt": now.isoformat(),
            "has_data": False,
            "error": f"Failed to fetch data after {self._consecutive_failures} attempts"
        })
        
        return self._data_processor.process(empty_data)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the data cache.
        
        Returns:
            Cache statistics
        """
        return self._data_fetcher.get_cache_stats()
    
    async def clear_cache(self) -> bool:
        """Clear the data cache.
        
        Returns:
            True if cache was cleared
        """
        self._data_fetcher.clear_cache(self.area)
        return True
    
    async def async_close(self):
        """Close any open sessions and resources."""
        if hasattr(self, '_exchange_service') and self._exchange_service:
            await self._exchange_service.async_close()

class UnifiedPriceCoordinator(DataUpdateCoordinator):
    """Data update coordinator using the unified price manager."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        area: str,
        currency: str,
        update_interval: timedelta,
        config: Dict[str, Any],
    ):
        """Initialize the coordinator.
        
        Args:
            hass: Home Assistant instance
            area: Area code
            currency: Currency code
            update_interval: Update interval
            config: Configuration dictionary
        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"gespot_{area}",
            update_interval=update_interval,
        )
        
        self.area = area
        self.currency = currency
        self.config = config
        
        # Create unified price manager
        self.price_manager = UnifiedPriceManager(
            hass=hass,
            area=area,
            currency=currency,
            config=config
        )
    
    async def _async_update_data(self):
        """Fetch data from price manager.
        
        Returns:
            Fetched data
        """
        return await self.price_manager.fetch_data()
    
    async def force_update(self):
        """Force an update regardless of schedule.
        
        Returns:
            True if update was forced
        """
        _LOGGER.info(f"Forcing update for area {self.area}")
        await self.price_manager.fetch_data(force=True)
        await self.async_request_refresh()
        return True
    
    async def clear_cache(self):
        """Clear the price cache.
        
        Returns:
            True if cache was cleared
        """
        return await self.price_manager.clear_cache()
    
    async def async_close(self):
        """Close any open sessions and resources."""
        await self.price_manager.async_close() 