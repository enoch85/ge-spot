"""
Manual test for Nordpool API.

This script tests the full chain of the Nordpool API:
1. Connecting to the API
2. Fetching raw data
3. Parsing the data into a standardized format
4. Displaying the results

Usage:
    python -m tests.manual.api.nordpool_test [area_code]

Example:
    python -m tests.manual.api.nordpool_test SE3
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
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
    
    logger.info(f"Testing Nordpool API for area: {area_code}")
    
    # Initialize API
    api = NordpoolAPI()
    
    # Test connection
    logger.info("Testing API connection...")
    try:
        # Fetch raw data
        logger.info("Fetching data from Nordpool API...")
        
        # Call the fetch_raw_data method with the area code
        raw_data = await api.fetch_raw_data(area_code)
        
        # Check if we have data
        if not raw_data or not raw_data.get("today"):
            logger.error("Failed to fetch today's data from Nordpool API")
            return 1
            
        logger.info("Successfully fetched raw data")
        
        # Parse data
        logger.info("Parsing raw data...")
        parsed_data = await api.parse_raw_data(raw_data)
        
        if not parsed_data or not parsed_data.get("hourly_prices"):
            logger.error("Failed to parse data or no hourly prices returned")
            return 1

        hourly_prices = parsed_data.get("hourly_prices", {})
        num_hourly_prices = len(hourly_prices)

        # Check for expected number of hours
        now_utc = datetime.now(timezone.utc)
        now_cet = now_utc.astimezone(timezone(timedelta(hours=1)))
        expect_tomorrow = now_cet.hour >= 13

        # Adjust expected hours based on time of day
        expected_hours = 24  # Today's hours at minimum
        if expect_tomorrow and "tomorrow_coverage" in parsed_data and parsed_data["tomorrow_coverage"] > 0:
            expected_hours += 24  # Tomorrow's hours if they should be available

        # More flexible criteria for test success
        if num_hourly_prices < 22:  # Allow for some missing hours
            logger.error(f"Insufficient data: Expected at least 22 hours, but got {num_hourly_prices}")
            # Log missing hours for today and tomorrow based on parsed_data metadata if available
            if "today_coverage" in parsed_data:
                logger.error(f"Today's coverage: {parsed_data['today_coverage']:.1f}%")
            if "tomorrow_coverage" in parsed_data and expect_tomorrow:
                logger.error(f"Tomorrow's coverage: {parsed_data['tomorrow_coverage']:.1f}%")
            return 1

        logger.info(f"Successfully fetched and parsed {num_hourly_prices} hourly prices.")

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

        for timestamp, price in sorted(hourly_prices.items()):
            logger.info(f"{timestamp:<25} | {price:<10.5f}")

        logger.info("\nTest completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))