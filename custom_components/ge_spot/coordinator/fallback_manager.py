import logging
from typing import List, Dict, Any, Optional, Type

# Import BasePriceAPI from its specific module
from ..api.base.base_price_api import BasePriceAPI
from ..const.sources import Source
from ..const.config import Config
from ..const.errors import PriceFetchError

_LOGGER = logging.getLogger(__name__)


class FallbackManager:
    """Manages fetching data with fallback logic."""

    async def fetch_with_fallbacks(
        self,
        apis: List[BasePriceAPI],
        area: str,
        currency: str,
        reference_time: Optional[Any] = None,
        hass: Optional[Any] = None,
        session: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt to fetch data from a list of APIs sequentially until one succeeds.

        Args:
            apis: A list of API instances, ordered by priority.
            area: The geographical area for the price data.
            currency: The target currency (may be handled later).
            reference_time: The reference time for the fetch.
            hass: Home Assistant instance (optional).
            session: aiohttp client session (optional).

        Returns:
            The data dictionary from the first successful API, or None if all fail.
        """
        last_exception = None
        attempted_sources = []

        if not apis:
            _LOGGER.warning("No API sources configured or available for area %s", area)
            return None

        for api_instance in apis:
            source_name = getattr(api_instance, 'source_name', type(api_instance).__name__)
            attempted_sources.append(source_name)
            _LOGGER.debug(
                "Attempting to fetch data from source: %s for area %s",
                source_name,
                area,
            )
            try:
                # Assuming fetch_day_ahead_prices exists and follows a standard signature
                # This signature might need adjustment based on the actual base class/interface
                data = await api_instance.fetch_day_ahead_prices(
                    area=area,
                    currency=currency, # Pass currency, but conversion might happen later
                    reference_time=reference_time,
                    hass=hass,
                    session=session,
                )
                if data and data.get("hourly_prices"): # Basic validation: ensure we got some hourly data
                    _LOGGER.info(
                        "Successfully fetched data from source: %s for area %s",
                        source_name,
                        area,
                    )
                    # Add metadata about which source succeeded and which were tried
                    data["data_source"] = source_name
                    data["attempted_sources"] = attempted_sources
                    return data
                else:
                    _LOGGER.warning(
                        "Source %s returned no data or empty hourly prices for area %s.",
                        source_name,
                        area
                    )
                    # Treat empty data as a failure for fallback purposes
                    last_exception = PriceFetchError(f"Source {source_name} returned no data.")


            except Exception as e:
                _LOGGER.warning(
                    "Failed to fetch data from source: %s for area %s. Error: %s",
                    source_name,
                    area,
                    e,
                    exc_info=True, # Log traceback for debugging
                )
                last_exception = e

        _LOGGER.error(
            "All API sources failed for area %s. Last error: %s",
            area,
            last_exception,
        )
        # Optionally return metadata about failed attempts even if all fail
        return {"attempted_sources": attempted_sources, "error": last_exception} # Or just return None
