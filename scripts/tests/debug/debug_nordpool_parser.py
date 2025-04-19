#!/usr/bin/env python3
"""Debug script for Nordpool parser issues."""
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
    from custom_components.ge_spot.api.nordpool import fetch_day_ahead_prices, _fetch_data, _process_data
    from custom_components.ge_spot.const.currencies import Currency
    from custom_components.ge_spot.utils.api_client import ApiClient
    from scripts.tests.mocks.hass import MockHass
    import aiohttp
    IMPORTS_SUCCESSFUL = True
except ImportError as e:
    logger.error(f"Failed to import from custom_components: {e}")
    IMPORTS_SUCCESSFUL = False
    sys.exit(1)

async def debug_nordpool_parser(area: str = "SE3"):
    """Debug Nordpool parser.
    
    Args:
        area: Area code to test
        
    Returns:
        Debug results
    """
    # Create mock HASS instance
    hass = MockHass()
    
    # Create a new session
    session = aiohttp.ClientSession()
    
    try:
        # Build config
        config = {
            "area": area,
            "currency": Currency.EUR,
            "vat": 0,
            "display_unit": "decimal"
        }
        
        # Fetch data directly using _fetch_data
        logger.info(f"Fetching data from Nordpool API for area {area}")
        client = ApiClient(session=session)
        raw_data = await _fetch_data(client, config, area, None)
        
        # Try to directly fetch tomorrow's data from the API
        logger.info("Directly fetching tomorrow's data from Nordpool API")
        
        # Get today's and tomorrow's dates
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Delivery area is the same as region for SE1 and SE4
        delivery_area = area
        
        # Nordpool API details
        base_url = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
        
        # Fetch tomorrow's data
        tomorrow_url = f"{base_url}?currency=EUR&date={tomorrow}&market=DayAhead&deliveryArea={delivery_area}"
        logger.info(f"Fetching tomorrow's data from: {tomorrow_url}")
        
        async with session.get(tomorrow_url) as response:
            if response.status == 200:
                tomorrow_data = await response.json()
                logger.info(f"Successfully fetched tomorrow's data: {len(tomorrow_data.get('multiAreaEntries', []))} entries")
                
                # Check if we have multiAreaEntries
                if "multiAreaEntries" in tomorrow_data:
                    logger.info(f"Found {len(tomorrow_data['multiAreaEntries'])} entries in tomorrow's data")
                    
                    # Check if we have data for the specified region
                    for entry in tomorrow_data["multiAreaEntries"][:3]:
                        if "entryPerArea" in entry and area in entry["entryPerArea"]:
                            logger.info(f"Found data for {area} in tomorrow's data")
                            logger.info(f"Example price: {entry['entryPerArea'][area]}")
                            break
                else:
                    logger.warning("No multiAreaEntries found in tomorrow's data")
                
                # Save the tomorrow data to a file for inspection
                with open("tomorrow_data.json", "w") as f:
                    import json
                    json.dump(tomorrow_data, f, indent=2)
                logger.info("Saved tomorrow data to tomorrow_data.json")
            else:
                logger.error(f"Failed to fetch tomorrow's data: {response.status}")
        
        if not raw_data:
            logger.error("No data returned from Nordpool API")
            return None
        
        # Log the raw data structure
        logger.info(f"Raw data keys: {raw_data.keys()}")
        
        # Check if tomorrow is None
        if "tomorrow" in raw_data:
            logger.info(f"Tomorrow is None: {raw_data['tomorrow'] is None}")
            logger.info(f"Tomorrow type: {type(raw_data['tomorrow'])}")
            logger.info(f"Tomorrow value: {raw_data['tomorrow']}")
        
        # Check if we have today's data
        if "today" in raw_data and raw_data["today"]:
            today_data = raw_data["today"]
            logger.info(f"Today data keys: {today_data.keys() if isinstance(today_data, dict) else 'Not a dict'}")
            
            if isinstance(today_data, dict) and "multiAreaEntries" in today_data:
                logger.info(f"Today multiAreaEntries: {len(today_data['multiAreaEntries'])}")
        
        # Create parser
        parser = NordpoolPriceParser()
        
        # Check if we have tomorrow's data
        if "tomorrow" in raw_data and raw_data["tomorrow"]:
            tomorrow_data = raw_data["tomorrow"]
            logger.info(f"Tomorrow data type: {type(tomorrow_data)}")
            logger.info(f"Tomorrow data: {tomorrow_data}")
            
            if isinstance(tomorrow_data, dict) and "multiAreaEntries" in tomorrow_data:
                logger.info(f"Tomorrow multiAreaEntries: {len(tomorrow_data['multiAreaEntries'])}")
                
                # Check the first few entries to see if they have the expected structure
                for i, entry in enumerate(tomorrow_data["multiAreaEntries"][:3]):
                    logger.info(f"Tomorrow entry {i} keys: {entry.keys() if isinstance(entry, dict) else 'Not a dict'}")
                    
                    if isinstance(entry, dict) and "entryPerArea" in entry:
                        logger.info(f"Tomorrow entry {i} entryPerArea keys: {entry['entryPerArea'].keys() if isinstance(entry['entryPerArea'], dict) else 'Not a dict'}")
                        
                        if area in entry["entryPerArea"]:
                            logger.info(f"Tomorrow entry {i} has data for area {area}: {entry['entryPerArea'][area]}")
                            
                            # Check if the entry has deliveryStart
                            if "deliveryStart" in entry:
                                logger.info(f"Tomorrow entry {i} deliveryStart: {entry['deliveryStart']}")
                                
                                # Try to parse the timestamp
                                dt = parser._parse_timestamp(entry["deliveryStart"])
                                if dt:
                                    logger.info(f"Tomorrow entry {i} parsed timestamp: {dt}")
                                    
                                    # Format as hour key
                                    from custom_components.ge_spot.timezone.timezone_utils import normalize_hour_value
                                    normalized_hour, adjusted_date = normalize_hour_value(dt.hour, dt.date())
                                    hour_key = f"{normalized_hour:02d}:00"
                                    logger.info(f"Tomorrow entry {i} hour key: {hour_key}")
                                else:
                                    logger.warning(f"Tomorrow entry {i} failed to parse timestamp: {entry['deliveryStart']}")
                            else:
                                logger.warning(f"Tomorrow entry {i} does not have deliveryStart")
                        else:
                            logger.warning(f"Tomorrow entry {i} does not have data for area {area}")
                    else:
                        logger.warning(f"Tomorrow entry {i} does not have entryPerArea")
        
        # Create parser
        parser = NordpoolPriceParser()
        
        # Parse today's hourly prices
        today_prices = parser.parse_hourly_prices(raw_data, area)
        logger.info(f"Today hourly prices: {len(today_prices)}")
        logger.info(f"Sample today prices: {list(today_prices.items())[:5]}")
        
        # Parse tomorrow's hourly prices
        tomorrow_prices = parser.parse_tomorrow_prices(raw_data, area)
        logger.info(f"Tomorrow hourly prices: {len(tomorrow_prices)}")
        logger.info(f"Sample tomorrow prices: {list(tomorrow_prices.items())[:5] if tomorrow_prices else 'None'}")
        
        # Create a data structure with tomorrow data in the expected format
        tomorrow_data_wrapper = {"tomorrow": raw_data["tomorrow"]}
        tomorrow_prices_fixed = parser.parse_tomorrow_prices(tomorrow_data_wrapper, area)
        logger.info(f"Tomorrow hourly prices (fixed): {len(tomorrow_prices_fixed)}")
        logger.info(f"Sample tomorrow prices (fixed): {list(tomorrow_prices_fixed.items())[:5] if tomorrow_prices_fixed else 'None'}")
        
        # Process the data using _process_data
        logger.info("Processing data using _process_data")
        processed_data = await _process_data(raw_data, area, Currency.EUR, 0, False, None, hass, session, config)
        
        if not processed_data:
            logger.error("No processed data returned")
            return None
        
        # Log the processed data structure
        logger.info(f"Processed data keys: {processed_data.keys()}")
        
        # Check if we have hourly_prices
        if "hourly_prices" in processed_data:
            logger.info(f"Processed hourly prices: {len(processed_data['hourly_prices'])}")
            logger.info(f"Sample processed hourly prices: {list(processed_data['hourly_prices'].items())[:5]}")
        
        # Check if we have tomorrow_hourly_prices
        if "tomorrow_hourly_prices" in processed_data:
            logger.info(f"Processed tomorrow hourly prices: {len(processed_data['tomorrow_hourly_prices'])}")
            logger.info(f"Sample processed tomorrow hourly prices: {list(processed_data['tomorrow_hourly_prices'].items())[:5]}")
        else:
            logger.warning("No tomorrow_hourly_prices in processed data")
        
        return {
            "raw_data": raw_data,
            "today_prices": today_prices,
            "tomorrow_prices": tomorrow_prices,
            "tomorrow_prices_fixed": tomorrow_prices_fixed,
            "processed_data": processed_data
        }
    
    except Exception as e:
        logger.error(f"Error debugging Nordpool parser: {e}", exc_info=True)
        return None
    finally:
        # Close the session
        if session and not session.closed:
            await session.close()
        # Close the client
        if client:
            await client.close()

async def main():
    """Run the debug script."""
    parser = argparse.ArgumentParser(description="Debug Nordpool parser")
    parser.add_argument("--area", default="SE3", help="Area code to test")
    args = parser.parse_args()
    
    # Debug Nordpool parser
    await debug_nordpool_parser(args.area)
    
    return 0

if __name__ == "__main__":
    asyncio.run(main())
