"""Parallel fetching of data from multiple sources."""
import logging
import asyncio
import time
from typing import Dict, Any, Optional, List, Tuple, Callable, Awaitable

from homeassistant.core import HomeAssistant

from ..const.config import Config
from ..const.defaults import Defaults
from ..api.base.data_fetch import is_skipped_response

_LOGGER = logging.getLogger(__name__)

class SourcePriorityFetcher:
    """Fetch data from multiple sources in priority order or parallel."""

    def __init__(self, hass: Optional[HomeAssistant] = None, config: Optional[Dict[str, Any]] = None):
        """Initialize the fetcher.

        Args:
            hass: Optional Home Assistant instance
            config: Optional configuration
        """
        self.hass = hass
        self.config = config or {}

        # Configuration
        self.parallel_fetch = self.config.get(Config.PARALLEL_FETCH, Defaults.PARALLEL_FETCH)
        self.timeout = self.config.get(Config.PARALLEL_FETCH_TIMEOUT, Defaults.PARALLEL_FETCH_TIMEOUT)
        self.max_workers = self.config.get(Config.PARALLEL_FETCH_MAX_WORKERS, Defaults.PARALLEL_FETCH_MAX_WORKERS)

        # Statistics
        self._stats = {
            "total_fetches": 0,
            "parallel_fetches": 0,
            "sequential_fetches": 0,
            "successful_fetches": 0,
            "failed_fetches": 0,
            "total_time": 0.0,
            "sources_tried": {},
            "sources_succeeded": {}
        }

    async def fetch_with_priority(self,
                                fetch_functions: Dict[str, Callable[..., Awaitable[Any]]],
                                priority: List[str],
                                common_kwargs: Optional[Dict[str, Any]] = None,
                                source_specific_kwargs: Optional[Dict[str, Dict[str, Any]]] = None,
                                parallel: Optional[bool] = None,
                                timeout: Optional[float] = None,
                                max_workers: Optional[int] = None) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Fetch data from multiple sources in priority order or parallel.

        Args:
            fetch_functions: Dictionary mapping source names to fetch functions
            priority: List of sources in priority order
            common_kwargs: Optional common keyword arguments for all fetch functions
            source_specific_kwargs: Optional source-specific keyword arguments
            parallel: Whether to fetch in parallel (default: from config)
            timeout: Optional timeout override
            max_workers: Optional max workers override

        Returns:
            Tuple of (source name, data) or (None, None) if all failed
        """
        # Start timing
        start_time = time.time()

        # Update stats
        self._stats["total_fetches"] += 1

        # Use config values if not overridden
        parallel = self.parallel_fetch if parallel is None else parallel
        timeout = self.timeout if timeout is None else timeout
        max_workers = self.max_workers if max_workers is None else max_workers

        # Prepare kwargs for each source
        common_kwargs = common_kwargs or {}
        source_specific_kwargs = source_specific_kwargs or {}

        kwargs_by_source = {}
        for source in fetch_functions:
            kwargs = dict(common_kwargs)
            if source in source_specific_kwargs:
                kwargs.update(source_specific_kwargs[source])
            kwargs_by_source[source] = kwargs

        # Filter and order sources based on priority
        sources = [s for s in priority if s in fetch_functions]

        # Update stats
        for source in sources:
            self._stats["sources_tried"][source] = self._stats["sources_tried"].get(source, 0) + 1

        if not sources:
            _LOGGER.warning("No valid sources to fetch from")
            self._stats["failed_fetches"] += 1
            return None, None

        if parallel:
            # Update stats
            self._stats["parallel_fetches"] += 1

            # Fetch in parallel
            return await self._fetch_parallel(
                fetch_functions,
                sources,
                kwargs_by_source,
                timeout,
                max_workers
            )
        else:
            # Update stats
            self._stats["sequential_fetches"] += 1

            # Fetch sequentially in priority order
            return await self._fetch_sequential(
                fetch_functions,
                sources,
                kwargs_by_source,
                timeout
            )

    async def _fetch_sequential(self,
                              fetch_functions: Dict[str, Callable[..., Awaitable[Any]]],
                              sources: List[str],
                              kwargs_by_source: Dict[str, Dict[str, Any]],
                              timeout: float) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Fetch data sequentially in priority order.

        Args:
            fetch_functions: Dictionary mapping source names to fetch functions
            sources: List of sources in priority order
            kwargs_by_source: Dictionary mapping source names to keyword arguments
            timeout: Timeout in seconds

        Returns:
            Tuple of (source name, data) or (None, None) if all failed
        """
        for source in sources:
            try:
                # Create task with timeout
                fetch_func = fetch_functions[source]
                kwargs = kwargs_by_source[source]

                task = asyncio.create_task(fetch_func(**kwargs))

                # Wait for task with timeout
                data = await asyncio.wait_for(task, timeout=timeout)

                # Check if the API was skipped due to missing credentials
                if is_skipped_response(data):
                    _LOGGER.debug(f"Source {source} skipped: {data.get('reason')}")
                    continue

                # Update stats
                self._stats["successful_fetches"] += 1
                self._stats["sources_succeeded"][source] = self._stats["sources_succeeded"].get(source, 0) + 1

                return source, data

            except asyncio.TimeoutError:
                _LOGGER.warning(f"Timeout fetching from {source}")
                continue

            except Exception as e:
                _LOGGER.warning(f"Error fetching from {source}: {e}")
                continue

        # All sources failed
        self._stats["failed_fetches"] += 1
        return None, None

    async def _fetch_parallel(self,
                            fetch_functions: Dict[str, Callable[..., Awaitable[Any]]],
                            sources: List[str],
                            kwargs_by_source: Dict[str, Dict[str, Any]],
                            timeout: float,
                            max_workers: int) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Fetch data in parallel from multiple sources.

        Args:
            fetch_functions: Dictionary mapping source names to fetch functions
            sources: List of sources in priority order
            kwargs_by_source: Dictionary mapping source names to keyword arguments
            timeout: Timeout in seconds
            max_workers: Maximum number of parallel workers

        Returns:
            Tuple of (source name, data) or (None, None) if all failed
        """
        # Limit number of sources to max_workers
        sources = sources[:max_workers]

        # Create tasks
        tasks = []
        for source in sources:
            fetch_func = fetch_functions[source]
            kwargs = kwargs_by_source[source]

            task = asyncio.create_task(fetch_func(**kwargs))
            tasks.append((source, task))

        # Wait for first successful task or all to fail
        pending = set(task for _, task in tasks)
        source_by_task = {task: source for source, task in tasks}

        try:
            # Wait for first task to complete or timeout
            done, pending = await asyncio.wait(
                pending,
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()

            # Check if any task completed successfully
            for task in done:
                try:
                    data = task.result()
                    source = source_by_task[task]

                    # Check if the API was skipped due to missing credentials
                    if is_skipped_response(data):
                        _LOGGER.debug(f"Source {source} skipped: {data.get('reason')}")
                        continue

                    # Update stats
                    self._stats["successful_fetches"] += 1
                    self._stats["sources_succeeded"][source] = self._stats["sources_succeeded"].get(source, 0) + 1

                    return source, data
                except Exception as e:
                    _LOGGER.warning(f"Error in task for {source_by_task[task]}: {e}")
                    continue

        except asyncio.TimeoutError:
            _LOGGER.warning("All parallel fetches timed out")

            # Cancel all tasks
            for task in pending:
                task.cancel()

        # All tasks failed or timed out
        self._stats["failed_fetches"] += 1
        return None, None

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about fetching."""
        return dict(self._stats)
