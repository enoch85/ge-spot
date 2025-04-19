#!/usr/bin/env python3
"""Debug script for directly accessing Nordpool API and testing tomorrow data."""
import sys
import os
import logging
import json
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path so we can import the custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# Import components from the integration
try:
    from custom_components.ge_spot.api.parsers.nordpool_parser import NordpoolPriceParser
    from custom_components.ge_spot.const.currencies import Currency
    from scripts.tests.mocks.hass import MockHass
    import aiohttp
    IMPORTS_SUCCESSFUL = True
except ImportError as e:
    logger.error(f"Failed to import from custom_components: {e}")
    IMPORTS_SUCCESSFUL = False
    sys.exit(1)

async def debug_direct_nordpool(area: str = "SE3"):
    """Debug direct Nordpool API access and test parser with tomorrow data.
    
    Args:
        area: Area code to test
        
    Returns:
        Debug results
    """
    # Create a new session
    session = aiohttp.ClientSession()
    
    try:
        # Get today's and tomorrow's dates
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Delivery area is the same as region for SE1-SE4
        delivery_area = area
        
        # Nordpool API details
        base_url = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
        
        # Fetch today's data
        today_url = f"{base_url}?currency=EUR&date={today}&market=DayAhead&deliveryArea={delivery_area}"
        logger.info(f"Fetching today's data from: {today_url}")
        
        async with session.get(today_url) as response:
            if response.status == 200:
                today_data = await response.json()
                logger.info(f"Successfully fetched today's data: {len(today_data.get('multiAreaEntries', []))} entries")
                
                # Save today's data to file for debugging
                with open("nordpool_today_data.json", "w") as f:
                    json.dump(today_data, f, indent=2)
                logger.info("Saved today's data to nordpool_today_data.json")
            else:
                logger.error(f"Failed to fetch today's data: {response.status}")
                today_data = None
        
        # Fetch tomorrow's data
        tomorrow_url = f"{base_url}?currency=EUR&date={tomorrow}&market=DayAhead&deliveryArea={delivery_area}"
        logger.info(f"Fetching tomorrow's data from: {tomorrow_url}")
        
        async with session.get(tomorrow_url) as response:
            if response.status == 200:
                tomorrow_data = await response.json()
                logger.info(f"Successfully fetched tomorrow's data: {len(tomorrow_data.get('multiAreaEntries', []))} entries")
                
                # Save tomorrow's data to file for debugging
                with open("nordpool_tomorrow_data.json", "w") as f:
                    json.dump(tomorrow_data, f, indent=2)
                logger.info("Saved tomorrow's data to nordpool_tomorrow_data.json")
            else:
                logger.error(f"Failed to fetch tomorrow's data: {response.status}")
                tomorrow_data = None
        
        # Create a complete raw_data dictionary with today and tomorrow data
        raw_data = {
            "today": today_data,
            "tomorrow": tomorrow_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Save the complete raw_data to file for debugging
        with open("nordpool_complete_data.json", "w") as f:
            json.dump(raw_data, f, indent=2)
        logger.info("Saved complete data to nordpool_complete_data.json")
        
        # Create parser instance
        parser = NordpoolPriceParser()
        
        # Parse today's hourly prices
        today_prices = parser.parse_hourly_prices(raw_data, area)
        logger.info(f"Today hourly prices: {len(today_prices)}")
        logger.info(f"Sample today prices: {list(today_prices.items())[:5]}")
        
        # Parse tomorrow's hourly prices
        tomorrow_prices = parser.parse_tomorrow_prices(raw_data, area)
        logger.info(f"Tomorrow hourly prices: {len(tomorrow_prices)}")
        logger.info(f"Sample tomorrow prices: {list(tomorrow_prices.items())[:5] if tomorrow_prices else 'None'}")
        
        # Log debug info about tomorrow data
        logger.debug(f"tomorrow_data type: {type(tomorrow_data)}")
        if isinstance(tomorrow_data, dict):
            logger.debug(f"tomorrow_data keys: {tomorrow_data.keys()}")
            if "multiAreaEntries" in tomorrow_data:
                logger.debug(f"tomorrow_data entries: {len(tomorrow_data['multiAreaEntries'])}")
                
                # Check a few entries to see what's in them
                for i, entry in enumerate(tomorrow_data['multiAreaEntries'][:3]):
                    logger.debug(f"Entry {i} keys: {entry.keys()}")
                    if "entryPerArea" in entry:
                        logger.debug(f"Entry {i} areas: {entry['entryPerArea'].keys()}")
                        if area in entry["entryPerArea"]:
                            logger.debug(f"Entry {i} price for {area}: {entry['entryPerArea'][area]}")
                    if "deliveryStart" in entry:
                        logger.debug(f"Entry {i} deliveryStart: {entry['deliveryStart']}")
                        
                        # Parse the timestamp
                        dt = parser._parse_timestamp(entry["deliveryStart"])
                        if dt:
                            logger.debug(f"Entry {i} parsed timestamp: {dt}")
        
        return {
            "today_data": today_data,
            "tomorrow_data": tomorrow_data,
            "today_prices": today_prices,
            "tomorrow_prices": tomorrow_prices
        }
    
    except Exception as e:
        logger.error(f"Error in debug_direct_nordpool: {e}", exc_info=True)
        return None
    finally:
        # Close the session
        if session and not session.closed:
            await session.close()

async def main():
    """Run the debug script."""
    parser = argparse.ArgumentParser(description="Debug direct Nordpool API access")
    parser.add_argument("--area", default="SE3", help="Area code to test")
    args = parser.parse_args()
    
    # Debug direct Nordpool API access
    await debug_direct_nordpool(args.area)
    
    return 0

if __name__ == "__main__":
    asyncio.run(main())
