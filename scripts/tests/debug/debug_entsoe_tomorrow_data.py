#!/usr/bin/env python3
"""Debug script for ENTSOE tomorrow data."""
import sys
import os
import logging
import json
import argparse
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path so we can import the custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# Import components from the integration
try:
    from custom_components.ge_spot.price.adapter import ElectricityPriceAdapter
    from custom_components.ge_spot.api.parsers.entsoe_parser import EntsoeParser
    from custom_components.ge_spot.api.entsoe import fetch_day_ahead_prices
    from custom_components.ge_spot.const.currencies import Currency
    from scripts.tests.mocks.hass import MockHass
    from scripts.tests.utils.general import build_api_key_config
    IMPORTS_SUCCESSFUL = True
except ImportError as e:
    logger.error(f"Failed to import from custom_components: {e}")
    IMPORTS_SUCCESSFUL = False
    sys.exit(1)

async def debug_entsoe_tomorrow_data(api_key: str, area: str = "SE4"):
    """Debug ENTSOE tomorrow data.
    
    Args:
        api_key: ENTSOE API key
        area: Area code
        
    Returns:
        Debug results
    """
    # Create mock HASS instance
    hass = MockHass()
    
    # Build config with API key
    config = {
        "api_key": api_key,
        "area": area
    }
    
    # Fetch data from the API
    logger.info(f"Fetching data from ENTSOE API for area {area}")
    data = await fetch_day_ahead_prices(
        source_type="entsoe",
        config=config,
        area=area,
        currency=Currency.EUR,
        hass=hass
    )
    
    # Check if we got a valid response
    if not data:
        logger.error("No data returned from ENTSOE API")
        return None
    
    # Log the raw data
    logger.info(f"Raw data: {data.keys()}")
    
    # Check if we have hourly_prices
    if "hourly_prices" in data:
        hourly_prices = data["hourly_prices"]
        logger.info(f"Hourly prices: {len(hourly_prices)} entries")
        
        # Log the first few entries
        sample_entries = list(hourly_prices.items())[:5]
        logger.info(f"Sample hourly prices: {sample_entries}")
        
        # Check if hourly_prices contains ISO format dates
        has_dates = any("T" in hour for hour in hourly_prices.keys())
        logger.info(f"Hourly prices contain ISO format dates: {has_dates}")
        
        # Check if we have tomorrow's data in hourly_prices
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date()
        tomorrow_hours = 0
        tomorrow_hour_keys = []
        
        for hour_key, price in hourly_prices.items():
            # Try to parse the hour key to check if it's for tomorrow
            if "T" in hour_key:  # ISO format with date
                try:
                    hour_dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                    if hour_dt.date() == tomorrow:
                        tomorrow_hours += 1
                        tomorrow_hour_keys.append(hour_key)
                except (ValueError, TypeError):
                    pass
        
        logger.info(f"Found {tomorrow_hours} hours of tomorrow's data in hourly_prices")
        if tomorrow_hours > 0:
            logger.info(f"Tomorrow hour keys: {tomorrow_hour_keys}")
    
    # Check if we have tomorrow_hourly_prices
    if "tomorrow_hourly_prices" in data:
        tomorrow_hourly_prices = data["tomorrow_hourly_prices"]
        logger.info(f"Tomorrow hourly prices: {len(tomorrow_hourly_prices)} entries")
        
        # Log the first few entries
        sample_entries = list(tomorrow_hourly_prices.items())[:5]
        logger.info(f"Sample tomorrow hourly prices: {sample_entries}")
    
    # Create adapter to test tomorrow data extraction
    adapter = ElectricityPriceAdapter(hass, [data], False)
    
    # Check if adapter correctly extracts tomorrow's data
    tomorrow_prices = adapter.tomorrow_prices
    
    # Log the keys to see what format they are in
    logger.info(f"Adapter hourly price keys: {list(adapter.hourly_prices.keys())[:5]}")
    logger.info(f"Adapter tomorrow price keys: {list(tomorrow_prices.keys())[:5] if tomorrow_prices else 'None'}")
    
    # Check if tomorrow's data is correctly identified
    is_tomorrow_valid = adapter.is_tomorrow_valid()
    
    # Log the results
    logger.info(f"Tomorrow data validation: {is_tomorrow_valid}")
    logger.info(f"Today hours: {len(adapter.hourly_prices)}, Tomorrow hours: {len(tomorrow_prices)}")
    
    return {
        "is_tomorrow_valid": is_tomorrow_valid,
        "today_hours": len(adapter.hourly_prices),
        "tomorrow_hours": len(tomorrow_prices),
        "hourly_prices": adapter.hourly_prices,
        "tomorrow_prices": tomorrow_prices
    }

async def main():
    """Run the debug script."""
    parser = argparse.ArgumentParser(description="Debug ENTSOE tomorrow data")
    parser.add_argument("--api-key", required=True, help="ENTSOE API key")
    parser.add_argument("--area", default="SE4", help="Area code")
    args = parser.parse_args()
    
    # Debug ENTSOE tomorrow data
    await debug_entsoe_tomorrow_data(args.api_key, args.area)
    
    return 0

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
