"""
Manual test for Nordpool API.

This script tests the full chain of the Nordpool API:
1. Connecting to the API
2. Fetching raw data
3. Parsing the data into a standardized format
4. Displaying the results

Usage:
    python -m tests.python3.api.nordpool_test [area_code]

Example:
    python -m tests.python3.api.nordpool_test SE3
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
import logging

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from custom_components.ge_spot.api.nordpool import NordpoolAPI
from custom_components.ge_spot.const.areas import Area

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

async def main():
    # Get area code from command line or use default
    area_code = sys.argv[1] if len(sys.argv) > 1 else "SE3"
    
    # Map area code to Nordpool area if it's a recognized code
    # mapped_area = Area.get_area_code(area_code, fail_silent=True) # Removed non-existent method call
    # if mapped_area:
    #     area_code = mapped_area
    
    logger.info(f"Testing Nordpool API for area: {area_code}")
    
    # Initialize API
    api = NordpoolAPI()
    
    # Test connection
    logger.info("Testing API connection...")
    try:
        # Fetch raw data
        logger.info("Fetching data from Nordpool API...")
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=2)
        
        # Pass only the area code, start/end are handled internally
        raw_data = await api.fetch_raw_data(area_code)
        logger.info("Successfully fetched raw data")
        
        # Parse data
        logger.info("Parsing raw data...")
        # Pass only raw_data, area is inside it
        parsed_data = await api.parse_raw_data(raw_data)
        
        if not parsed_data or not parsed_data.get("hourly_prices"):
            logger.error("Failed to parse data or no hourly prices returned")
            return 1
        
        # Display results
        logger.info("\nParsed Data:")
        logger.info(f"Source: {parsed_data.get('source')}")
        logger.info(f"Area: {parsed_data.get('area')}")
        logger.info(f"Currency: {parsed_data.get('currency')}")
        logger.info(f"API Timezone: {parsed_data.get('api_timezone')}")
        logger.info(f"Fetched at: {parsed_data.get('fetched_at')}")
        
        # Format hourly prices into a table
        logger.info("\nHourly Prices:")
        logger.info(f"{'Timestamp':<25} | {'Price':<10}")
        logger.info("-" * 38)
        
        for timestamp, price in sorted(parsed_data.get("hourly_prices", {}).items()):
            logger.info(f"{timestamp:<25} | {price:<10.5f}")
        
        logger.info("\nTest completed successfully")
        return 0
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))