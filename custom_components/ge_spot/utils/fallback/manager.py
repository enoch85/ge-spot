"""Fallback manager for API sources."""
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple, Union

from homeassistant.core import HomeAssistant

from ...const.config import Config
from ...const.sources import Source
from ...utils.price_extractor import extract_prices
from ...api.base.data_fetch import is_skipped_response
from ...api import fetch_day_ahead_prices, get_sources_for_region
from .source_health import SourceHealth
from .data_quality import DataQualityScore

_LOGGER = logging.getLogger(__name__)

class FallbackManager:
    """Manager for fallback between different data sources."""

    def __init__(
        self, 
        hass: Optional[HomeAssistant] = None, 
        config: Optional[Dict[str, Any]] = None,
        area: Optional[str] = None, 
        currency: Optional[str] = None, 
        session: Optional[Any] = None
    ):
        """Initialize fallback manager.

        Args:
            hass: Optional Home Assistant instance
            config: Optional configuration
            area: Optional area code
            currency: Optional currency code
            session: Optional session
        """
        self.hass = hass
        self.config = config or {}
        self.area = area
        self.currency = currency
        self.session = session

        # Track source health
        self.source_health: Dict[str, SourceHealth] = {}
        
        # Data quality scoring
        self.data_quality = DataQualityScore()

        # Default source priority
        self.default_priority = self.config.get(Config.SOURCE_PRIORITY, [
            Source.NORDPOOL,
            Source.ENTSOE,
            Source.ENERGI_DATA_SERVICE,
            Source.EPEX,
            Source.OMIE,
            Source.STROMLIGNING,
            Source.AEMO,
            Source.COMED
        ])

        # Cached data
        self.cached_data: Dict[str, Dict[str, Any]] = {}

    def update_source_health(self, source: str, success: Optional[bool],
                           response_time: Optional[float] = None,
                           error_type: Optional[str] = None) -> None:
        """Update health information for a source.

        Args:
            source: Source identifier
            success: Whether the request was successful (None if skipped)
            response_time: Optional response time in seconds
            error_type: Optional error type if the request failed
        """
        if source not in self.source_health:
            self.source_health[source] = SourceHealth(source)

        self.source_health[source].update(success, response_time, error_type)

    def get_source_health(self, source: Optional[str] = None) -> Union[Dict[str, Any], Dict[str, Dict[str, Any]]]:
        """Get health information for sources.

        Args:
            source: Optional source identifier

        Returns:
            Health information for the specified source or all sources
        """
        if source:
            if source in self.source_health:
                return self.source_health[source].metadata
            return {}

        return {s: h.metadata for s, h in self.source_health.items()}

    def get_healthy_sources(self) -> List[str]:
        """Get list of healthy sources.

        Returns:
            List of healthy source identifiers
        """
        return [s for s, h in self.source_health.items() if h.is_healthy]

    def get_priority_order(self, area: str) -> List[str]:
        """Get priority order for sources based on health and configuration.

        Args:
            area: Area code

        Returns:
            List of sources in priority order
        """
        # Start with default priority
        priority = list(self.default_priority)

        # Move unhealthy sources to the end
        healthy_sources = set(self.get_healthy_sources())
        priority.sort(key=lambda s: s not in healthy_sources)

        # Filter to sources that support the area
        supported_sources = get_sources_for_region(area)
        priority = [s for s in priority if s in supported_sources]

        return priority

    async def fetch_with_fallbacks(self) -> Dict[str, Any]:
        """Fetch data with fallbacks for the configured area.

        Returns:
            Dictionary with fetched data and metadata
        """
        if not self.area:
            _LOGGER.error("No area configured for FallbackManager")
            return {"data": None, "source": None, "attempted_sources": []}

        # Get supported sources for this area
        supported_sources = get_sources_for_region(self.area)
        if not supported_sources:
            _LOGGER.error(f"No supported sources for area {self.area}")
            return {"data": None, "source": None, "attempted_sources": []}

        # Common kwargs for all fetch functions
        common_kwargs = {
            "config": self.config,
            "area": self.area,
            "currency": self.currency,
            "hass": self.hass,
            "session": self.session
        }

        # Track sources
        attempted_sources = []
        skipped_sources = []
        fallback_sources = []
        fallback_data = {}

        # Try each source in priority order
        for source in self.get_priority_order(self.area):
            if source not in supported_sources:
                continue

            attempted_sources.append(source)
            start_time = time.time()

            try:
                # Fetch from this source
                kwargs = dict(common_kwargs)
                kwargs["source_type"] = source
                
                data = await fetch_day_ahead_prices(**kwargs)
                
                # Calculate response time
                response_time = time.time() - start_time

                # Check if the API was skipped due to missing credentials
                if is_skipped_response(data):
                    skipped_source = data.get("source")
                    reason = data.get("reason")
                    _LOGGER.debug(f"Source {skipped_source} skipped: {reason}")
                    skipped_sources.append(skipped_source)
                    
                    # Don't count this as a failure
                    self.update_source_health(skipped_source, None)
                    continue

                if data:
                    # Extract hourly prices using our generic extractor
                    hourly_prices = extract_prices(data, self.area)
                    
                    # If we have hourly prices, we're good to go
                    if hourly_prices:
                        # Update source health for successful fetch
                        self.update_source_health(source, True, response_time)
                        
                        # Score data quality
                        quality_score = self.data_quality.score_data(data, source)
                        
                        # If this is not the first source we tried, it's a fallback
                        if attempted_sources[0] != source:
                            fallback_used = True
                        else:
                            fallback_used = False
                            
                        # Store the successful data
                        self._cache_data(source, data, quality_score)
                        
                        # Add hourly prices to the data
                        data["hourly_prices"] = hourly_prices
                        
                        # Ensure we have the required metadata
                        if "api_timezone" not in data:
                            data["api_timezone"] = "UTC"  # Default to UTC if not specified
                            
                        if "currency" not in data:
                            data["currency"] = "EUR"  # Default to EUR if not specified
                        
                        # Build result
                        result = {
                            "data": data,
                            "source": source,
                            "attempted_sources": attempted_sources,
                            "skipped_sources": skipped_sources,
                            "fallback_sources": fallback_sources,
                            "primary_source": attempted_sources[0] if attempted_sources else None,
                            "fallback_used": fallback_used,
                            "quality_score": quality_score
                        }
                        
                        # Add fallback data if available
                        for fb_source, fb_data in fallback_data.items():
                            # Extract hourly prices from fallback data
                            fb_hourly_prices = extract_prices(fb_data, self.area)
                            
                            # Add hourly prices to fallback data
                            if fb_hourly_prices:
                                fb_data["hourly_prices"] = fb_hourly_prices
                                
                            result[f"fallback_data_{fb_source}"] = fb_data
                            
                        return result
                    else:
                        _LOGGER.warning(f"Source {source} returned data but no valid hourly prices for area {self.area}")
                        
                        # Mark as a failure
                        self.update_source_health(source, False, response_time, "no_hourly_prices")
                        
                        # Store as fallback data
                        fallback_sources.append(source)
                        fallback_data[source] = data
                else:
                    # Update source health for failed fetch
                    self.update_source_health(source, False, response_time, "no_data")
            except Exception as e:
                # Update source health for failed fetch
                response_time = time.time() - start_time
                self.update_source_health(source, False, response_time, str(e))
                _LOGGER.error(f"Error fetching from {source}: {e}")

        # All sources failed or were skipped
        _LOGGER.error(f"Failed to fetch data from any source for area {self.area}")

        # Try to use cached data
        cached_data = self._get_cached_data()
        if cached_data:
            cached_source = cached_data.get("_fallback_metadata", {}).get("source", "unknown")
            _LOGGER.info(f"Using cached data for {self.area} from {cached_source}")

            return {
                "data": cached_data,
                "source": cached_source,
                "attempted_sources": attempted_sources,
                "skipped_sources": skipped_sources,
                "fallback_sources": fallback_sources,
                "primary_source": attempted_sources[0] if attempted_sources else None,
                "fallback_used": True,
                "using_cached_data": True
            }

        return {
            "data": None,
            "source": None,
            "attempted_sources": attempted_sources,
            "skipped_sources": skipped_sources,
            "fallback_sources": fallback_sources
        }
        
    def _cache_data(self, source: str, data: Dict[str, Any], quality_score: float = 0.0) -> None:
        """Cache data from a source.

        Args:
            source: Source identifier
            data: Data to cache
            quality_score: Quality score for the data
        """
        # Add metadata
        data["_fallback_metadata"] = {
            "source": source,
            "area": self.area,
            "cached_at": datetime.now().isoformat(),
            "quality_score": quality_score
        }

        # Cache data
        if self.area not in self.cached_data:
            self.cached_data[self.area] = {}
            
        self.cached_data[self.area][source] = data
        
    def _get_cached_data(self, max_age: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Get cached data for the current area.

        Args:
            max_age: Optional maximum age in seconds

        Returns:
            Cached data, or None if not available
        """
        if self.area not in self.cached_data:
            return None
            
        # Get sources with cached data
        sources = list(self.cached_data[self.area].keys())
        if not sources:
            return None
            
        # Filter by age if specified
        if max_age is not None:
            sources = [
                s for s in sources
                if "_fallback_metadata" in self.cached_data[self.area][s]
                and self._get_cache_age(self.cached_data[self.area][s]) <= max_age
            ]
            
        if not sources:
            return None
            
        # Get best source based on quality score
        best_source = self.data_quality.get_best_source(sources)
        if best_source:
            return self.cached_data[self.area][best_source]
            
        # Fall back to most recent
        sources.sort(key=lambda s: self._get_cache_time(self.cached_data[self.area][s]), reverse=True)
        return self.cached_data[self.area][sources[0]]
        
    def _get_cache_time(self, data: Dict[str, Any]) -> datetime:
        """Get cache time for data.

        Args:
            data: Cached data

        Returns:
            Cache time, or epoch if not available
        """
        if "_fallback_metadata" not in data or "cached_at" not in data["_fallback_metadata"]:
            return datetime.fromtimestamp(0)

        try:
            return datetime.fromisoformat(data["_fallback_metadata"]["cached_at"])
        except (ValueError, KeyError):
            return datetime.fromtimestamp(0)
            
    def _get_cache_age(self, data: Dict[str, Any]) -> float:
        """Get age of cached data in seconds.

        Args:
            data: Cached data

        Returns:
            Age in seconds, or float('inf') if unknown
        """
        if "_fallback_metadata" not in data or "cached_at" not in data["_fallback_metadata"]:
            return float('inf')

        try:
            cached_at = datetime.fromisoformat(data["_fallback_metadata"]["cached_at"])
            return (datetime.now() - cached_at).total_seconds()
        except (ValueError, KeyError):
            return float('inf')
            
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about fallback manager."""
        return {
            "source_health": self.get_source_health(),
            "data_quality": self.data_quality.get_scores(),
            "cached_areas": list(self.cached_data.keys())
        }
