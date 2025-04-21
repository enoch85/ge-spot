#!/usr/bin/env python3
"""Test script for verifying Nordpool's handling of tomorrow's data.

This script tests the Nordpool API's ability to correctly extract tomorrow's data
from their API responses.
"""
import sys
import os
import logging
import json
import argparse
import asyncio
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
    from custom_components.ge_spot.api.parsers.nordpool_parser import NordpoolPriceParser
    from custom_components.ge_spot.const.config import Config
    from custom_components.ge_spot.const.currencies import Currency
    from custom_components.ge_spot.api.nordpool import fetch_day_ahead_prices
    from scripts.tests.mocks.hass import MockHass
    from scripts.tests.core.adapter_testing import ImprovedElectricityPriceAdapter
    import aiohttp
    IMPORTS_SUCCESSFUL = True
except ImportError as e:
    logger.error(f"Failed to import from custom_components: {e}")
    IMPORTS_SUCCESSFUL = False
    sys.exit(1)

async def test_nordpool_api(area: str = "SE3"):
    """Test the Nordpool API for tomorrow's data.
    
    Args:
        area: Area code to test
        
    Returns:
        Dictionary with test results
    """
    logger.info(f"Testing Nordpool API for area {area}")
    
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
        
        # Fetch data from the API
        data = await fetch_day_ahead_prices(
            source_type="nordpool",
            config=config,
            area=area,
            currency=Currency.EUR,
            hass=hass,
            session=None  # Don't pass the session, let the function create its own
        )
        
        if not data:
            logger.error("No data returned from Nordpool API")
            return None
        
        # Log the raw data structure
        logger.info(f"Raw data keys: {data.keys()}")
        
        # Check if we have hourly_prices
        if "hourly_prices" in data:
            hourly_prices = data["hourly_prices"]
            logger.info(f"Hourly prices: {len(hourly_prices)} entries")
            
            # Log the first few entries
            sample_entries = list(hourly_prices.items())[:5]
            logger.info(f"Sample hourly prices: {sample_entries}")
        
        # Check if we have tomorrow_hourly_prices
        if "tomorrow_hourly_prices" in data:
            tomorrow_hourly_prices = data["tomorrow_hourly_prices"]
            logger.info(f"Tomorrow hourly prices: {len(tomorrow_hourly_prices)} entries")
            
            # Log the first few entries
            sample_entries = list(tomorrow_hourly_prices.items())[:5]
            logger.info(f"Sample tomorrow hourly prices: {sample_entries}")
        else:
            logger.warning("No tomorrow_hourly_prices found in data")
        
        # Create adapter to test tomorrow data extraction
        adapter = ElectricityPriceAdapter(hass, [data], Source.NORDPOOL, False)
        
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
        
        # Create improved adapter to test tomorrow data extraction
        improved_adapter = ImprovedElectricityPriceAdapter(hass, [data], Source.NORDPOOL, False)
        
        # Check if improved adapter correctly extracts tomorrow's data
        improved_tomorrow_prices = improved_adapter.tomorrow_prices
        
        # Log the keys to see what format they are in
        logger.info(f"Improved adapter hourly price keys: {list(improved_adapter.hourly_prices.keys())[:5]}")
        logger.info(f"Improved adapter tomorrow price keys: {list(improved_tomorrow_prices.keys())[:5] if improved_tomorrow_prices else 'None'}")
        
        # Check if tomorrow's data is correctly identified
        improved_is_tomorrow_valid = improved_adapter.is_tomorrow_valid()
        
        # Log the results
        logger.info(f"Improved adapter tomorrow data validation: {improved_is_tomorrow_valid}")
        logger.info(f"Improved adapter today hours: {len(improved_adapter.hourly_prices)}, Tomorrow hours: {len(improved_tomorrow_prices)}")
        
        # Try to directly access the Nordpool API to see if tomorrow's data is available
        logger.info("Trying direct API access to check for tomorrow's data")
        
        # Get today's and tomorrow's dates
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Delivery area is the same as region for SE1 and SE4
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
            else:
                logger.error(f"Failed to fetch tomorrow's data: {response.status}")
                tomorrow_data = None
        
        # Return results
        return {
            "adapter_tomorrow_valid": is_tomorrow_valid,
            "adapter_tomorrow_hours": len(tomorrow_prices),
            "improved_adapter_tomorrow_valid": improved_is_tomorrow_valid,
            "improved_adapter_tomorrow_hours": len(improved_tomorrow_prices),
            "direct_api_today_success": today_data is not None,
            "direct_api_tomorrow_success": tomorrow_data is not None
        }
    
    except Exception as e:
        logger.error(f"Error testing Nordpool API: {e}", exc_info=True)
        return None
    finally:
        # Close the session
        if session and not session.closed:
            await session.close()

async def main():
    """Run the test."""
    parser = argparse.ArgumentParser(description="Test Nordpool API for tomorrow's data")
    parser.add_argument("--area", default="SE3", help="Area code to test")
    args = parser.parse_args()
    
    result = await test_nordpool_api(args.area)
    
    if result:
        logger.info("\n=== Test Results ===")
        for key, value in result.items():
            logger.info(f"{key}: {value}")
    
    return 0

if __name__ == "__main__":
    asyncio.run(main())
