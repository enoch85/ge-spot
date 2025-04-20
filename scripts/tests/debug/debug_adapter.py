#!/usr/bin/env python3
"""Debug script for ElectricityPriceAdapter."""
import os
import sys
import json
import logging
import asyncio
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

try:
    from custom_components.ge_spot.price.adapter import ElectricityPriceAdapter
    from scripts.tests.mocks.hass import MockHass
except ImportError as e:
    logger.error(f"Failed to import required components: {e}")
    sys.exit(1)

async def debug_adapter():
    """Debug the ElectricityPriceAdapter."""
    # Load ENTSOE cache file
    cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../parser_cache"))
    cache_file = os.path.join(cache_dir, "entsoe_SE4.json")
    
    if not os.path.exists(cache_file):
        logger.error(f"Cache file {cache_file} does not exist")
        return
    
    logger.info(f"Loading cache file: {cache_file}")
    with open(cache_file, "r") as f:
        entsoe_data = json.load(f)
    
    # Print raw data structure
    logger.info("Raw data keys: %s", entsoe_data.get("raw_data", {}).keys())
    logger.info("Hourly prices: %d entries", len(entsoe_data.get("raw_data", {}).get("today_hourly_prices", {})))
    sample_prices = list(entsoe_data.get("raw_data", {}).get("today_hourly_prices", {}).items())[:5]
    logger.info("Sample hourly prices: %s", sample_prices)
    
    # Create adapter
    mock_hass = MockHass()
    adapter = ElectricityPriceAdapter(mock_hass, [entsoe_data.get("raw_data", {})], False)
    
    # Print adapter data
    logger.info("Adapter hourly price keys: %s", list(adapter.today_hourly_prices.keys())[:5] if adapter.today_hourly_prices else [])
    logger.info("Adapter tomorrow price keys: %s", list(adapter.tomorrow_prices.keys())[:5] if adapter.tomorrow_prices else [])
    
    # Create a fixed version of the data
    if "raw_data" in entsoe_data and "hourly_prices" in entsoe_data["raw_data"]:
        fixed_data = entsoe_data["raw_data"].copy()
        if "today_hourly_prices" not in fixed_data:
            fixed_data["today_hourly_prices"] = fixed_data.get("hourly_prices", {})
        
        logger.info("Creating adapter with fixed data")
        fixed_adapter = ElectricityPriceAdapter(mock_hass, [fixed_data], False)
        logger.info("Fixed adapter hourly price keys: %s", list(fixed_adapter.today_hourly_prices.keys())[:5] if fixed_adapter.today_hourly_prices else [])
    
    # Print current time and hour key
    now = datetime.now(timezone.utc)
    current_hour = now.hour
    current_hour_key = f"{current_hour:02d}:00"
    logger.info("Current hour: %s", current_hour_key)
    
    # Check if current hour key exists in adapter data
    if current_hour_key in adapter.today_hourly_prices:
        logger.info("Current hour price in adapter: %s", adapter.today_hourly_prices[current_hour_key])
    else:
        logger.warning("Current hour key %s not found in adapter hourly prices", current_hour_key)

if __name__ == "__main__":
    asyncio.run(debug_adapter())
