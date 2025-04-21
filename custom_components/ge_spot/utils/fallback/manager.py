"""Fallback manager for API sources."""
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple, Union, Callable, Awaitable

from homeassistant.core import HomeAssistant

from ...const.config import Config
from ...const.defaults import Defaults
from ...const.sources import Source
from ..error import ErrorManager
from ..parallel_fetcher import SourcePriorityFetcher
from .source_health import SourceHealth
from .data_quality import DataQualityScore
from ...api.base.data_fetch import is_skipped_response

_LOGGER = logging.getLogger(__name__)

class FallbackManager:
    """Manage fallback between different data sources."""

    def __init__(self, hass: Optional[HomeAssistant] = None, config: Optional[Dict[str, Any]] = None,
                area: Optional[str] = None, currency: Optional[str] = None, session: Optional[Any] = None):
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
        self.error_manager = ErrorManager(hass, config)
        self.priority_fetcher = SourcePriorityFetcher(hass, config)
        self.data_quality = DataQualityScore()

        # Track source health
        self.source_health: Dict[str, SourceHealth] = {}

        # Default source priority
        self.default_priority = self.config.get(Config.SOURCE_PRIORITY, [
            Source.NORDPOOL,
            Source.ENTSOE,
            Source.ENERGI_DATA_SERVICE,
            Source.EPEX,
            Source.OMIE,
            Source.STROMLIGNING,
            Source.AEMO
        ])

        # Cached data
        self.cached_data: Dict[str, Dict[str, Any]] = {}

    def update_source_health(self, source: str, success: bool,
                           response_time: Optional[float] = None,
                           error_type: Optional[str] = None) -> None:
        """Update health information for a source.

        Args:
            source: Source identifier
            success: Whether the request was successful
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
        # This would require knowledge of which sources support which areas
        # For now, we'll just return the priority list

        return priority

    def cache_data(self, source: str, area: str, data: Dict[str, Any]) -> None:
        """Cache data from a source.

        Args:
            source: Source identifier
            area: Area code
            data: Data to cache
        """
        if area not in self.cached_data:
            self.cached_data[area] = {}

        # Score data quality
        quality_score = self.data_quality.score_data(data, source)

        # Add metadata
        data["_fallback_metadata"] = {
            "source": source,
            "area": area,
            "cached_at": datetime.now().isoformat(),
            "quality_score": quality_score
        }

        # Cache data
        self.cached_data[area][source] = data

    def get_cached_data(self, area: str, source: Optional[str] = None,
                       max_age: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Get cached data.

        Args:
            area: Area code
            source: Optional source identifier
            max_age: Optional maximum age in seconds

        Returns:
            Cached data, or None if not available
        """
        if area not in self.cached_data:
            return None

        if source:
            # Get data for specific source
            if source not in self.cached_data[area]:
                return None

            data = self.cached_data[area][source]

            # Check age
            if max_age is not None and "_fallback_metadata" in data:
                try:
                    cached_at = datetime.fromisoformat(data["_fallback_metadata"]["cached_at"])
                    age = (datetime.now() - cached_at).total_seconds()
                    if age > max_age:
                        return None
                except (ValueError, KeyError):
                    pass

            return data

        # Get best data from any source
        sources = list(self.cached_data[area].keys())
        if not sources:
            return None

        # Filter by age
        if max_age is not None:
            sources = [
                s for s in sources
                if "_fallback_metadata" in self.cached_data[area][s]
                and self._get_cache_age(self.cached_data[area][s]) <= max_age
            ]

        if not sources:
            return None

        # Get best source based on quality score
        best_source = self.data_quality.get_best_source(sources)
        if best_source:
            return self.cached_data[area][best_source]

        # Fallback to first source
        return self.cached_data[area][sources[0]]

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

    async def fetch_with_fallback(self,
                                fetch_functions: Dict[str, Callable[..., Awaitable[Any]]],
                                area: str,
                                common_kwargs: Optional[Dict[str, Any]] = None,
                                source_specific_kwargs: Optional[Dict[str, Dict[str, Any]]] = None,
                                parallel: Optional[bool] = None,
                                timeout: Optional[float] = None,
                                max_workers: Optional[int] = None,
                                use_cache: bool = True,
                                cache_max_age: Optional[float] = None) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Fetch data with fallback between sources.

        Args:
            fetch_functions: Dictionary mapping source names to fetch functions
            area: Area code
            common_kwargs: Optional common keyword arguments for all fetch functions
            source_specific_kwargs: Optional source-specific keyword arguments
            parallel: Whether to fetch in parallel (default: from config)
            timeout: Optional timeout override
            max_workers: Optional max workers override
            use_cache: Whether to use cached data if all sources fail
            cache_max_age: Optional maximum age for cached data

        Returns:
            Tuple of (source name, data) or (None, None) if all failed
        """
        # Get priority order for this area
        priority = self.get_priority_order(area)

        # Start timing
        start_time = time.time()

        # Track skipped sources
        skipped_sources = []

        # Fetch with priority
        source, data = await self.priority_fetcher.fetch_with_priority(
            fetch_functions,
            priority,
            common_kwargs,
            source_specific_kwargs,
            parallel,
            timeout,
            max_workers
        )

        # Calculate response time
        response_time = time.time() - start_time

        if source and data:
            # Check if the API was skipped due to missing credentials
            if is_skipped_response(data):
                skipped_source = data.get("source")
                reason = data.get("reason")
                _LOGGER.debug(f"Source {skipped_source} skipped: {reason}")
                skipped_sources.append(skipped_source)

                # Don't count this as a failure
                self.update_source_health(skipped_source, None)
            else:
                # Check if the data has valid hourly prices or tomorrow hourly prices
                has_hourly_prices = (
                    isinstance(data, dict) and
                    "hourly_prices" in data and
                    isinstance(data["hourly_prices"], dict) and
                    len(data["hourly_prices"]) > 0
                )

                has_tomorrow_prices = (
                    isinstance(data, dict) and
                    "tomorrow_hourly_prices" in data and
                    isinstance(data["tomorrow_hourly_prices"], dict) and
                    len(data["tomorrow_hourly_prices"]) > 0
                )

                if has_hourly_prices or has_tomorrow_prices:
                    # Update source health for successful fetch
                    self.update_source_health(source, True, response_time)

                    # Cache successful data
                    self.cache_data(source, area, data)

                    return source, data
                else:
                    _LOGGER.warning(f"Source {source} returned data but no valid hourly prices or tomorrow hourly prices for area {area}, trying next source")
                    # Mark as a failure to try the next source
                    self.update_source_health(source, False, error_type="no_hourly_prices")

        # All sources failed or were skipped
        for s in fetch_functions:
            if s != source and s not in skipped_sources:  # source might be None
                self.update_source_health(s, False)

        # Try to use cached data
        if use_cache:
            cached_data = self.get_cached_data(area, max_age=cache_max_age)
            if cached_data:
                _LOGGER.info(f"Using cached data for {area} from {cached_data.get('_fallback_metadata', {}).get('source', 'unknown')}")
                return cached_data.get("_fallback_metadata", {}).get("source"), cached_data

        return None, None

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about fallback manager."""
        return {
            "source_health": self.get_source_health(),
            "data_quality": self.data_quality.get_scores(),
            "cached_areas": list(self.cached_data.keys()),
            "priority_fetcher": self.priority_fetcher.get_stats()
        }

    async def fetch_with_fallbacks(self) -> Dict[str, Any]:
        """Fetch data with fallbacks for the configured area.

        Returns:
            Dictionary with fetched data and metadata
        """
        from ...api import fetch_day_ahead_prices, get_sources_for_region

        if not self.area:
            _LOGGER.error("No area configured for FallbackManager")
            return {"data": None, "source": None, "attempted_sources": []}

        # Get supported sources for this area
        supported_sources = get_sources_for_region(self.area)
        if not supported_sources:
            _LOGGER.error(f"No supported sources for area {self.area}")
            return {"data": None, "source": None, "attempted_sources": []}

        # Create fetch functions for each source
        fetch_functions = {}
        for source in supported_sources:
            fetch_functions[source] = fetch_day_ahead_prices

        # Common kwargs for all fetch functions
        common_kwargs = {
            "config": self.config,
            "area": self.area,
            "currency": self.currency,
            "hass": self.hass
        }

        # Source-specific kwargs
        source_specific_kwargs = {}
        for source in supported_sources:
            source_specific_kwargs[source] = {"source_type": source}

        # Track skipped sources
        skipped_sources = []

        # Try each source in priority order
        for source in self.get_priority_order(self.area):
            if source not in fetch_functions:
                continue

            # Fetch from this source
            fetch_func = fetch_functions[source]
            kwargs = dict(common_kwargs)
            if source in source_specific_kwargs:
                kwargs.update(source_specific_kwargs[source])

            try:
                data = await fetch_func(**kwargs)

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
                    # Check if the data has valid hourly prices or tomorrow hourly prices
                    has_hourly_prices = (
                        isinstance(data, dict) and
                        "hourly_prices" in data and
                        isinstance(data["hourly_prices"], dict) and
                        len(data["hourly_prices"]) > 0
                    )

                    has_tomorrow_prices = (
                        isinstance(data, dict) and
                        "tomorrow_hourly_prices" in data and
                        isinstance(data["tomorrow_hourly_prices"], dict) and
                        len(data["tomorrow_hourly_prices"]) > 0
                    )

                    if has_hourly_prices or has_tomorrow_prices:
                        # Update source health for successful fetch
                        self.update_source_health(source, True)

                        # Cache successful data
                        self.cache_data(source, self.area, data)

                        # Build result
                        # Safely get primary source
                        primary_source = None
                        if self.default_priority and len(self.default_priority) > 0:
                            primary_source = self.default_priority[0]

                        # Determine if fallback was used
                        fallback_used = False
                        if primary_source is not None and source is not None:
                            fallback_used = source != primary_source

                        result = {
                            "data": data,
                            "source": source,
                            "attempted_sources": self.get_priority_order(self.area),
                            "skipped_sources": skipped_sources,
                            "fallback_sources": [],
                            "primary_source": primary_source,
                            "fallback_used": fallback_used
                        }

                        # Add fallback data if available
                        for src, fb_data in self.cached_data.get(self.area, {}).items():
                            if src != source:
                                result[f"fallback_data_{src}"] = fb_data
                                result["fallback_sources"].append(src)

                        return result
                    else:
                        _LOGGER.warning(f"Source {source} returned data but no valid hourly prices or tomorrow hourly prices for area {self.area}, trying next source")
                        # Mark as a failure to try the next source
                        self.update_source_health(source, False, error_type="no_hourly_prices")
            except Exception as e:
                _LOGGER.error(f"Error fetching from {source}: {e}")
                self.update_source_health(source, False, error_type=str(e))

        # All sources failed or were skipped
        _LOGGER.error(f"Failed to fetch data from any source for area {self.area}")

        # Try to use cached data
        cached_data = self.get_cached_data(self.area)
        if cached_data:
            cached_source = cached_data.get("_fallback_metadata", {}).get("source", "unknown")
            _LOGGER.info(f"Using cached data for {self.area} from {cached_source}")

            # Safely get primary source
            primary_source = None
            if self.default_priority and len(self.default_priority) > 0:
                primary_source = self.default_priority[0]

            return {
                "data": cached_data,
                "source": cached_source,
                "attempted_sources": self.get_priority_order(self.area),
                "skipped_sources": skipped_sources,
                "fallback_sources": [],
                "primary_source": primary_source,
                "fallback_used": True,
                "using_cached_data": True
            }

        return {
            "data": None,
            "source": None,
            "attempted_sources": self.get_priority_order(self.area),
            "skipped_sources": skipped_sources,
            "fallback_sources": []
        }
