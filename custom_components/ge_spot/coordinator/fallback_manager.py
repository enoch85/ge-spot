import logging
import asyncio
from typing import List, Dict, Any, Optional, Type

# Import BasePriceAPI from its specific module
from ..api.base.base_price_api import BasePriceAPI
from ..const.sources import Source
from ..const.config import Config
from ..const.errors import PriceFetchError
from ..const.network import Network

_LOGGER = logging.getLogger(__name__)


class FallbackManager:
    """Manages fetching data with fallback logic and exponential timeout."""

    async def fetch_with_fallback(
        self,
        api_instances: List[BasePriceAPI],
        area: str,
        reference_time: Optional[Any] = None,
        session: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """Try API sources in priority order with exponential timeout backoff.

        Implements exponential timeout strategy per source:
            - Attempt 1: 2 seconds
            - Attempt 2: 6 seconds (2s × 3)
            - Attempt 3: 18 seconds (6s × 3)

        Total max time per source: 2s + 6s + 18s = 26 seconds

        Args:
            api_instances: List of API instances to try in priority order
            area: Area code for the fetch
            reference_time: Optional reference time for the fetch
            session: Optional aiohttp session

        Returns:
            Standardized price data dict or None if all sources failed
        """
        attempted_sources = []
        last_exception = None

        if not api_instances:
            _LOGGER.warning(f"No API sources configured for area {area}")
            return None

        for api_instance in api_instances:
            source_name = getattr(api_instance, 'source_type', type(api_instance).__name__)
            attempted_sources.append(source_name)

            # Try each source with exponential backoff
            for attempt in range(Network.Defaults.RETRY_COUNT):
                # Calculate timeout: base × (multiplier ^ attempt)
                # No cap - let it grow naturally (2s, 6s, 18s)
                timeout = (
                    Network.Defaults.RETRY_BASE_TIMEOUT *
                    (Network.Defaults.RETRY_TIMEOUT_MULTIPLIER ** attempt)
                )

                try:
                    _LOGGER.debug(
                        f"[{area}] Trying '{source_name}' attempt {attempt + 1}/{Network.Defaults.RETRY_COUNT} "
                        f"(timeout: {timeout}s)"
                    )

                    # Wrap the API call with timeout
                    data = await asyncio.wait_for(
                        api_instance.fetch_raw_data(
                            area=area,
                            session=session,
                            reference_time=reference_time
                        ),
                        timeout=timeout
                    )

                    # Check if we got valid data
                    if data and isinstance(data, dict) and data.get("raw_data"):
                        _LOGGER.info(
                            f"[{area}] ✓ '{source_name}' succeeded "
                            f"(attempt {attempt + 1}, {timeout}s timeout)"
                        )
                        data["data_source"] = source_name
                        data["attempted_sources"] = attempted_sources
                        return data
                    else:
                        _LOGGER.debug(
                            f"[{area}] '{source_name}' returned no data "
                            f"(attempt {attempt + 1}/{Network.Defaults.RETRY_COUNT})"
                        )
                        # No data, but no exception - try next attempt
                        if attempt < Network.Defaults.RETRY_COUNT - 1:
                            continue
                        else:
                            # Last attempt failed, move to next source
                            last_exception = PriceFetchError(
                                f"Source {source_name} returned no raw data after {Network.Defaults.RETRY_COUNT} attempts"
                            )
                            break

                except asyncio.TimeoutError:
                    _LOGGER.debug(
                        f"[{area}] '{source_name}' timeout after {timeout}s "
                        f"(attempt {attempt + 1}/{Network.Defaults.RETRY_COUNT})"
                    )
                    last_exception = PriceFetchError(
                        f"Source {source_name} timeout after {timeout}s"
                    )
                    if attempt < Network.Defaults.RETRY_COUNT - 1:
                        # Not last attempt, retry immediately with higher timeout
                        continue
                    else:
                        # Last attempt failed, log warning and move to next source
                        _LOGGER.warning(
                            f"[{area}] ✗ '{source_name}' failed all {Network.Defaults.RETRY_COUNT} attempts "
                            f"(timeouts: 2s, 6s, 18s)"
                        )
                        break

                except Exception as e:
                    _LOGGER.warning(
                        f"[{area}] '{source_name}' error on attempt {attempt + 1}: {e}",
                        exc_info=True
                    )
                    last_exception = e
                    # On unexpected error, don't retry this source, move to next
                    break

            # Continue to next source in priority list

        # All sources failed
        _LOGGER.error(
            f"[{area}] All sources failed to provide data. "
            f"Attempted: {', '.join(attempted_sources)}. "
            f"Last error: {last_exception}"
        )
        return {
            "attempted_sources": attempted_sources,
            "error": last_exception,
            "has_data": False
        }
