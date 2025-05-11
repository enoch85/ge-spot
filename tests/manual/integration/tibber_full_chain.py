import asyncio
import logging
from datetime import datetime, timezone
import sys
import os
import aiohttp

# Adjust path to import from the ge_spot custom_component
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from custom_components.ge_spot.api.base_adapter import PriceData
from custom_components.ge_spot.api.tibber_adapter import TibberAdapter
from custom_components.ge_spot.const.sources import SOURCE_TIBBER, SourceInfo
from custom_components.ge_spot.coordinator.api_key_manager import ApiKeyManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
_LOGGER = logging.getLogger(__name__)

async def main(market_area: str): # Market area is for context, Tibber uses token for specifics
    """Main function to test TibberAdapter."""
    _LOGGER.info(f"Testing TibberAdapter. Market area parameter for context: {market_area}")

    api_key = os.environ.get("TIBBER_API_KEY")
    if not api_key:
        _LOGGER.error("TIBBER_API_KEY environment variable not set. Cannot run Tibber test.")
        return

    async with aiohttp.ClientSession() as session:
        # ApiKeyManager will be responsible for providing the key to the adapter
        # For this test, we simulate that it would retrieve the TIBBER_API_KEY
        # In a real scenario, ApiKeyManager would be configured via UI/config entry
        # and would store/retrieve keys appropriately.
        # We pass a mock ApiKeyManager that can return the key for SOURCE_TIBBER.
        class MockApiKeyManager(ApiKeyManager):
            def get_api_key(self, source_name: str, market_area: str | None = None) -> str | None:
                if source_name == SOURCE_TIBBER:
                    return api_key
                return None

        api_key_manager = MockApiKeyManager(hass=None, config_entry_id="dummy_tibber_id")

        adapter = TibberAdapter(
            hass=None, 
            api_key_manager=api_key_manager,
            source_name=SOURCE_TIBBER,
            market_area=market_area, # Used for context, adapter uses token
            session=session
        )

        _LOGGER.info(f"Adapter Name: {adapter.name}")
        _LOGGER.info(f"Market Area (context): {adapter.market_area}")
        _LOGGER.info(f"Source Name: {adapter.source_name}")

        try:
            target_dt = datetime.now(timezone.utc)
            _LOGGER.info(f"Fetching data for target_datetime: {target_dt.isoformat()}")

            price_data: PriceData = await adapter.async_fetch_data(target_dt)

            _LOGGER.info(f"Data fetched successfully from {price_data.source}")
            _LOGGER.info(f"Currency: {price_data.currency}")
            _LOGGER.info(f"Timezone: {price_data.timezone}") # Should be UTC as data is normalized
            if price_data.meta:
                _LOGGER.info(f"API URL: {price_data.meta.get('api_url')}")
                _LOGGER.info(f"Raw Unit: {price_data.meta.get('raw_unit')}")
                _LOGGER.info(f"Raw Response Preview: {price_data.meta.get('raw_response_preview')}")

            if price_data.hourly_raw:
                _LOGGER.info(f"Number of hourly prices fetched: {len(price_data.hourly_raw)}")
                display_limit = 5
                for i, price_entry in enumerate(price_data.hourly_raw):
                    if i < display_limit or i >= len(price_data.hourly_raw) - display_limit:
                        _LOGGER.info(
                            f"  {i+1:02d}: Start: {price_entry['start_time'].isoformat()}, "
                            f"Price: {price_entry['price']:.5f} {price_data.currency}/kWh"
                        )
                    elif i == display_limit:
                        _LOGGER.info("  ...")
            else:
                _LOGGER.warning("No hourly price data returned.")
            
            if price_data.meta and price_data.meta.get("error"):
                _LOGGER.error(f"Error in fetched data: {price_data.meta['error']}")

        except Exception as e:
            _LOGGER.error(f"Error during TibberAdapter test: {e}", exc_info=True)

if __name__ == "__main__":
    _LOGGER.info("Tibber test requires TIBBER_API_KEY environment variable to be set.")
    
    # Market area for Tibber is more for GE-Spot's internal organization if multiple Tibber accounts were ever a thing.
    # The actual data fetched is tied to the API token.
    # We use a placeholder or a common Tibber region like NO, SE, DE, NL.
    default_market_area_context = "NO" 
    supported_areas_for_tibber_source = SourceInfo.get_areas_for_source(SOURCE_TIBBER)
    supported_areas_info = f"Tibber operates in specific countries. Contextual areas in const: {supported_areas_for_tibber_source}"

    market_area_arg = default_market_area_context
    if len(sys.argv) > 1:
        market_area_arg = sys.argv[1].upper()
        # No strict validation against supported_areas_for_tibber_source as it's contextual for Tibber
        _LOGGER.info(f"Using market area context from argument: {market_area_arg}")
    else:
        _LOGGER.info(f"No market area context provided, defaulting to {market_area_arg}. {supported_areas_info}")
    
    asyncio.run(main(market_area_arg))
