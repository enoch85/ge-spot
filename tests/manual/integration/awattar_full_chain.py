import asyncio
import logging
from datetime import datetime, timezone, timedelta
import sys
import os

# Adjust path to import from the ge_spot custom_component
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

import aiohttp

from custom_components.ge_spot.api.awattar_adapter import AwattarAdapter
from custom_components.ge_spot.api.base_adapter import PriceData
from custom_components.ge_spot.coordinator.api_key_manager import ApiKeyManager # Dummy for adapter
from custom_components.ge_spot.const.sources import SOURCE_AWATTAR

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
_LOGGER = logging.getLogger(__name__)

async def main(market_area: str):
    """Main function to test Awattar adapter."""
    _LOGGER.info(f"Testing Awattar adapter for market area: {market_area}")

    async with aiohttp.ClientSession() as session:
        # Dummy ApiKeyManager, not used by Awattar adapter but required by BaseAPIAdapter constructor
        api_key_manager = ApiKeyManager(hass=None, config_entry_id="dummy_id")

        adapter = AwattarAdapter(
            hass=None, # Not strictly needed for this adapter's fetch
            api_key_manager=api_key_manager,
            source_name=SOURCE_AWATTAR,
            market_area=market_area,
            session=session
        )

        _LOGGER.info(f"Adapter Name: {adapter.name}")
        _LOGGER.info(f"Market Area: {adapter.market_area}")
        _LOGGER.info(f"Source Name: {adapter.source_name}")

        try:
            # Fetch data for the current time
            target_dt = datetime.now(timezone.utc)
            _LOGGER.info(f"Fetching data for target_datetime: {target_dt.isoformat()}")

            price_data: PriceData = await adapter.async_fetch_data(target_dt)

            _LOGGER.info(f"Data fetched successfully from {price_data.source}")
            _LOGGER.info(f"Currency: {price_data.currency}")
            _LOGGER.info(f"Timezone: {price_data.timezone}") # Should be UTC
            _LOGGER.info(f"Raw Unit: {price_data.meta.get('raw_unit')}")
            _LOGGER.info(f"API URL: {price_data.meta.get('api_url')}")
            _LOGGER.info(f"Raw Response Preview: {price_data.meta.get('raw_response_preview')}")

            if price_data.hourly_raw:
                _LOGGER.info(f"Number of hourly prices fetched: {len(price_data.hourly_raw)}")
                # Display first 5 and last 5 prices if many, or all if few
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
            _LOGGER.error(f"Error during Awattar adapter test: {e}", exc_info=True)
        finally:
            await session.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        area = sys.argv[1].upper()
    else:
        area = "DE-LU" # Default test area, other is AT
        _LOGGER.info(f"No market area provided, defaulting to {area}. Supported: DE-LU, AT")
    
    asyncio.run(main(area))
