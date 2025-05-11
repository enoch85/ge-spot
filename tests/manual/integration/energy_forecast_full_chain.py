import asyncio
import logging
from datetime import datetime, timezone
import sys
import os
import aiohttp

# Adjust path to import from the ge_spot custom_component
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from custom_components.ge_spot.api.base_adapter import PriceData
from custom_components.ge_spot.api.energy_forecast_adapter import EnergyForecastAdapter
from custom_components.ge_spot.const.sources import SOURCE_ENERGY_FORECAST, SourceInfo
from custom_components.ge_spot.coordinator.api_key_manager import ApiKeyManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
_LOGGER = logging.getLogger(__name__)

async def main(market_area: str):
    """Main function to test EnergyForecastAdapter."""
    _LOGGER.info(f"Testing EnergyForecastAdapter for market area: {market_area}")

    api_key = os.environ.get("ENERGY_FORECAST_API_KEY")
    if not api_key:
        _LOGGER.error("ENERGY_FORECAST_API_KEY environment variable not set. Cannot run EnergyForecast test.")
        return

    async with aiohttp.ClientSession() as session:
        class MockApiKeyManager(ApiKeyManager):
            def get_api_key(self, source_name: str, market_area: str | None = None) -> str | None:
                if source_name == SOURCE_ENERGY_FORECAST:
                    return api_key
                return None

        api_key_manager = MockApiKeyManager(hass=None, config_entry_id="dummy_energy_forecast_id")

        adapter = EnergyForecastAdapter(
            hass=None, 
            api_key_manager=api_key_manager,
            source_name=SOURCE_ENERGY_FORECAST,
            market_area=market_area,
            session=session
        )

        _LOGGER.info(f"Adapter Name: {adapter.name}")
        _LOGGER.info(f"Market Area: {adapter.market_area}")
        _LOGGER.info(f"Source Name: {adapter.source_name}")

        try:
            target_dt = datetime.now(timezone.utc)
            _LOGGER.info(f"Fetching data for target_datetime: {target_dt.isoformat()}")

            price_data: PriceData = await adapter.async_fetch_data(target_dt)

            _LOGGER.info(f"Data fetched successfully from {price_data.source}")
            _LOGGER.info(f"Currency: {price_data.currency}")
            _LOGGER.info(f"Timezone: {price_data.timezone}") # Should be UTC
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
            _LOGGER.error(f"Error during EnergyForecastAdapter test: {e}", exc_info=True)

if __name__ == "__main__":
    _LOGGER.info("EnergyForecast test requires ENERGY_FORECAST_API_KEY environment variable to be set.")
    
    default_market_area = "DE-LU"
    supported_areas = SourceInfo.get_areas_for_source(SOURCE_ENERGY_FORECAST)
    supported_areas_info = f"Supported areas from const: {supported_areas}"
    
    market_area_arg = default_market_area
    if len(sys.argv) > 1:
        market_area_arg = sys.argv[1].upper()
        if market_area_arg not in supported_areas:
            _LOGGER.warning(f"Provided market area '{market_area_arg}' may not be explicitly listed as supported. Test will proceed. {supported_areas_info}")
            # Allow proceeding as token might be general or for a new/unlisted area for this specific source
    else:
        _LOGGER.info(f"No market area provided, defaulting to {market_area_arg}. {supported_areas_info}")
    
    asyncio.run(main(market_area_arg))
