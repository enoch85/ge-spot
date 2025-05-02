"""Base data fetching utilities for API modules."""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union, Type
from datetime import datetime, timezone

from ...const.sources import Source
from .error_handler import ErrorHandler
from .base_price_api import BasePriceAPI
from .data_structure import StandardizedPriceData, create_standardized_price_data
from ...utils.advanced_cache import AdvancedCache

_LOGGER = logging.getLogger(__name__)

class BaseDataFetcher(ABC):
    """Base class for API data fetchers."""

    def __init__(self, source: str, session=None, config: Optional[Dict[str, Any]] = None):
        """Initialize the data fetcher.

        Args:
            source: Source identifier
            session: Optional session for API requests
            config: Optional configuration
        """
        self.source = source
        self.session = session
        self.config = config or {}
        self._owns_session = False

    @abstractmethod
    async def fetch_data(self, **kwargs) -> Dict[str, Any]:
        """Fetch data from API.

        Args:
            **kwargs: Additional keyword arguments

        Returns:
            Fetched data
        """
        pass

    async def process_response(self, response: Any) -> Dict[str, Any]:
        """Process API response.

        Args:
            response: Raw API response

        Returns:
            Processed data
        """
        # Default implementation returns the response as is
        return response

    async def handle_error(self, error: Exception) -> Dict[str, Any]:
        """Handle error during data fetching.

        Args:
            error: Exception that occurred

        Returns:
            Error response or None
        """
        _LOGGER.error(f"Error fetching data from {self.source}: {error}")
        return None

    async def validate_config(self) -> bool:
        """Validate configuration.

        Returns:
            True if configuration is valid, False otherwise
        """
        # Default implementation assumes valid config
        return True

    def create_skipped_response(self, reason: str = "missing_api_key") -> Dict[str, Any]:
        """Create a standardized response for when an API is skipped.

        Args:
            reason: The reason for skipping (default: "missing_api_key")

        Returns:
            A dictionary with standardized skipped response format
        """
        return create_skipped_response(self.source, reason)

def create_skipped_response(source: str, reason: str = "missing_api_key") -> Dict[str, Any]:
    """Create a standardized response for when an API is skipped.

    Args:
        source: The source identifier (e.g., Source.ENTSOE)
        reason: The reason for skipping (default: "missing_api_key")

    Returns:
        A dictionary with standardized skipped response format
    """
    _LOGGER.debug(f"Creating skipped response for {source}: {reason}")
    return {
        "skipped": True,
        "reason": reason,
        "source": source
    }

def is_skipped_response(data: Any) -> bool:
    """Check if a response is a skipped response.

    Args:
        data: The data to check

    Returns:
        True if the data is a skipped response, False otherwise
    """
    return (
        isinstance(data, dict) and
        data.get("skipped") is True and
        "reason" in data and
        "source" in data
    )

class PriceDataFetcher:
    """Centralized data fetching with standardized fallback handling."""
    
    def __init__(self):
        """Initialize the price data fetcher."""
        self.error_handler = ErrorHandler("PriceDataFetcher")
        # Replace simple dict with AdvancedCache (using defaults, no persistence)
        # Note: Persistence requires hass and config, which aren't available here.
        # Max entries and default TTL will use defaults from AdvancedCache.
        self.cache = AdvancedCache()

    async def fetch_with_fallback(
        self,
        sources: List[Union[BasePriceAPI, Type[BasePriceAPI]]],
        area: str,
        currency: str, 
        reference_time: Optional[datetime] = None,
        config: Optional[Dict[str, Any]] = None,
        session=None,
        vat: Optional[float] = None,
        include_vat: bool = False,
        cache_expiry_hours: Optional[float] = None,  # Keep this parameter for TTL
        **kwargs
    ) -> Dict[str, Any]:
        """Fetch data from multiple sources with fallback.
        
        Args:
            sources: List of API sources to try in order
            area: Area code
            currency: Currency code
            reference_time: Optional reference time
            config: Optional configuration
            session: Optional session
            vat: Optional VAT rate
            include_vat: Whether to include VAT
            cache_expiry_hours: Optional cache expiry time in hours (used for TTL)
            **kwargs: Additional parameters
            
        Returns:
            Standardized price data or standardized empty result if all sources fail
        """
        if not sources:
            _LOGGER.error("No sources provided for fetch_with_fallback")
            # Return standardized empty result
            return self._create_empty_result(area, currency, "No sources provided")
        
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
        
        # Tracking for which sources were attempted and which succeeded/failed
        attempted_sources = []
        successful_source = None
        fallback_sources = []
        using_cached_data = False
        
        # Initialize data with empty default
        result = None
        errors = {}
        
        # Try each source in order
        for i, source in enumerate(sources):
            source_name = f"Source_{i}"  # Use consistent naming format for tests
            attempted_sources.append(source_name)
            
            _LOGGER.info(f"Trying source {source_name} for area {area}")
            
            try:
                # Make sure we have an instance, not a class
                source_instance = source
                if isinstance(source, type):
                    source_instance = source(config, session)
                
                # Fetch data from this source
                source_result = await source_instance.fetch_day_ahead_prices(
                    area=area,
                    currency=currency,
                    reference_time=reference_time,
                    vat=vat,
                    include_vat=include_vat,
                    session=session,
                    **kwargs
                )
                
                # Check if we got valid data
                if source_result and "hourly_prices" in source_result and source_result["hourly_prices"]:
                    _LOGGER.info(f"Successfully fetched data from {source_name} for area {area}")
                    
                    # If this isn't the primary source, record as fallback
                    if i > 0:
                        fallback_sources.append(source_name)
                    
                    # Record which source succeeded
                    successful_source = source_name
                    
                    # Store in cache for future use
                    cache_key = f"{area}_{currency}"
                    # Use cache.set() with TTL from cache_expiry_hours or AdvancedCache default
                    ttl_seconds = None
                    if cache_expiry_hours is not None:
                        ttl_seconds = int(cache_expiry_hours * 3600)
                    
                    # Store the actual data, not a dict containing data/timestamp/source
                    self.cache.set(cache_key, source_result, ttl=ttl_seconds, metadata={"source": source_name})
                    
                    # Use this result
                    result = source_result
                    break
                else:
                    _LOGGER.warning(f"Source {source_name} returned empty or invalid data for area {area}")
                    errors[source_name] = "Empty or invalid data"
                    # Add to fallback sources since it failed
                    fallback_sources.append(source_name)
            
            except Exception as e:
                error_msg = str(e)
                _LOGGER.warning(f"Error fetching from {source_name} for area {area}: {error_msg}")
                errors[source_name] = error_msg
                # Add to fallback sources since it failed
                fallback_sources.append(source_name)
                continue
        
        # If all sources failed, try to use cached data
        if result is None:
            cache_key = f"{area}_{currency}"
            # Use cache.get() which handles expiration automatically
            cached_data = self.cache.get(cache_key)
            
            if cached_data:
                # Get source info from metadata if needed
                # Use a temporary dict to avoid errors if entry is gone between get() and get_info()
                cache_info = self.cache.get_info()
                entry_info = cache_info.get("entries", {}).get(cache_key, {})
                cached_source = entry_info.get("metadata", {}).get("source", "unknown_cached")
                cache_age_seconds = entry_info.get("age", 0)
                
                _LOGGER.warning(
                    f"All sources failed for area {area}, using cached data from {cached_source} "
                    f"({int(cache_age_seconds / 60)} minutes old)"
                )
                result = cached_data
                using_cached_data = True
                successful_source = f"{cached_source} (cached)"
            else:
                _LOGGER.error(f"All sources failed for area {area} and no valid cache available")
                # Return an empty result structure
                result = self._create_empty_result(area, currency, "All sources failed and no cache available")
        
        # Add metadata about the fetch process to the result
        if result:
            result["attempted_sources"] = attempted_sources
            result["fallback_sources"] = fallback_sources
            result["using_cached_data"] = using_cached_data
            
            if "errors" not in result:
                result["errors"] = {}
            
            # Add error details
            result["errors"].update(errors)
            
            # Make sure area is set
            if "area" not in result:
                result["area"] = area
        
        return result
        
    def _create_empty_result(self, area: str, currency: str, error_message: str = "") -> Dict[str, Any]:
        """Create a standardized empty result structure.
        
        Args:
            area: Area code
            currency: Currency code
            error_message: Optional error message
            
        Returns:
            Dictionary with standardized empty structure
        """
        from custom_components.ge_spot.api.base.data_structure import StandardizedPriceData
        
        # Generate empty result with proper structure
        empty_result = StandardizedPriceData.create_empty(
            source="None",
            area=area,
            currency=currency
        ).to_dict()
        
        # Add error message if provided
        if error_message:
            empty_result["error"] = error_message
            
        return empty_result
    
    async def fetch_multiple_regions(
        self,
        region_source_map: Dict[str, List[Union[BasePriceAPI, Type[BasePriceAPI]]]],
        default_currency: str,
        reference_time: Optional[datetime] = None,
        config: Optional[Dict[str, Any]] = None,
        session=None,
        vat: Optional[Dict[str, float]] = None,
        include_vat: Dict[str, bool] = None,
        **kwargs
    ) -> Dict[str, Dict[str, Any]]:
        """Fetch data for multiple regions in parallel.
        
        Args:
            region_source_map: Dictionary mapping region codes to their source lists
            default_currency: Default currency code
            reference_time: Optional reference time
            config: Optional configuration dictionary
            session: Optional session
            vat: Optional dictionary mapping regions to VAT rates
            include_vat: Dictionary mapping regions to whether to include VAT
            **kwargs: Additional parameters
            
        Returns:
            Dictionary mapping region codes to their price data
        """
        if not region_source_map:
            _LOGGER.error("No regions provided for fetch_multiple_regions")
            return {}
        
        import asyncio
        
        # Create tasks for each region
        tasks = {}
        for region, sources in region_source_map.items():
            # Get region-specific parameters
            region_vat = None
            if vat and region in vat:
                region_vat = vat[region]
                
            region_include_vat = False
            if include_vat and region in include_vat:
                region_include_vat = include_vat[region]
                
            # Create task for this region
            tasks[region] = self.fetch_with_fallback(
                sources=sources,
                area=region,
                currency=default_currency,
                reference_time=reference_time,
                config=config,
                session=session,
                vat=region_vat,
                include_vat=region_include_vat,
                **kwargs
            )
        
        # Wait for all tasks to complete
        results = {}
        for region, task in tasks.items():
            try:
                results[region] = await task
            except Exception as e:
                _LOGGER.error(f"Error fetching data for region {region}: {e}")
                # Initialize with empty data
                results[region] = StandardizedPriceData.create_empty(
                    source="None",
                    area=region,
                    currency=default_currency
                ).to_dict()
                
                # Add error information
                results[region]["errors"] = {"fetch_error": str(e)}
        
        return results
    
    def clear_cache(self):
        """Clear all cached data."""
        # Simplify to just clear the whole cache
        # Get count before clearing if possible (accessing internal _cache)
        try:
            old_count = len(self.cache._cache)
        except AttributeError:
            old_count = 'unknown'
        self.cache.clear()
        _LOGGER.debug(f"Cleared {old_count} cache entries")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the cache using AdvancedCache.get_info().

        Returns:
            Dictionary with cache statistics from AdvancedCache
        """
        # Use the get_info method from AdvancedCache
        return self.cache.get_info()
