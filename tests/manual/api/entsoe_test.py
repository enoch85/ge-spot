"""
Manual test for ENTSOE API.

This script tests the full chain of the ENTSOE API:
1. Connecting to the API
2. Fetching raw data
3. Parsing the data into a standardized format
4. Displaying the results

Usage:
    python -m tests.python3.api.entsoe_test [area_code]

Example:
    python -m tests.python3.api.entsoe_test SE3
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
import logging

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from custom_components.ge_spot.api.entsoe import EntsoeAPI
from custom_components.ge_spot.const.areas import AreaMapping
from custom_components.ge_spot.const.config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

async def main():
    # Get API key from environment variable or prompt
    api_key = os.environ.get('ENTSOE_API_KEY')
    if not api_key:
        api_key = input("Enter your ENTSOE API key: ")
        if not api_key:
            logger.error("No API key provided. Exiting.")
            return 1

    # Get area code from command line or use default
    area_code = sys.argv[1] if len(sys.argv) > 1 else "SE3"

    # Map area code to ENTSOE EIC code if possible
    entsoe_code = AreaMapping.ENTSOE_MAPPING.get(area_code, area_code)
    logger.info(f"Testing ENTSOE API for area: {area_code} (EIC: {entsoe_code})")

    # Initialize API
    api = EntsoeAPI(api_key)

    # Test connection
    logger.info("Testing API connection...")
    try:
        # Fetch raw data
        logger.info("Fetching data from ENTSOE API...")
        raw_data = await api.fetch_raw_data(entsoe_code)
        if not isinstance(raw_data, dict):
            logger.error(f"ENTSOE API returned a non-dict response: {raw_data}")
            return 1
        logger.info("Successfully fetched raw data")
        # Parse data
        logger.info("Parsing raw data...")
        parsed_data = await api.parse_raw_data(raw_data)

        if not parsed_data or not parsed_data.get("interval_prices"):
            logger.error("Failed to parse data or no interval prices returned")
            return 1

        # Display results
        logger.info("\nParsed Data:")
        logger.info(f"Source: {parsed_data.get('source')}")
        logger.info(f"Area: {parsed_data.get('area')}")
        logger.info(f"Currency: {parsed_data.get('currency')}")
        logger.info(f"API Timezone: {parsed_data.get('api_timezone')}")
        logger.info(f"Fetched at: {parsed_data.get('fetched_at')}")

        # Format interval prices into a table
        logger.info("\nInterval Prices:")
        logger.info(f"{'Timestamp':<25} | {'Price':<10}")
        logger.info("-" * 38)

        for timestamp, price in sorted(parsed_data.get("interval_prices", {}).items()):
            logger.info(f"{timestamp:<25} | {price:<10.5f}")

        logger.info("\nTest completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))