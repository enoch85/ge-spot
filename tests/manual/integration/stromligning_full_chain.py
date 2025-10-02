#!/usr/bin/env python3
"""
Manual full chain test for Strømlikning API.

This script performs an end-to-end test of the Strømlikning API integration:
1. Fetches real data from the Strømlikning API
2. Parses the raw data
3. Applies currency conversion
4. Validates and displays the results

Usage:
    python stromligning_full_chain.py [area] --supplier [supplier]

    area: Optional area code (DK1, DK2)
          Defaults to DK1 if not provided
    supplier: Required supplier name (e.g., EWII, AndelEnergi)
"""

import sys
import os
import argparse
from datetime import datetime, timedelta
import asyncio
import pytz
import logging
import json  # Ensure json is imported if needed for pretty printing

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Add the root directory to the path so we can import the component modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from custom_components.ge_spot.api.stromligning import StromligningAPI
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService
# Import Config constant
from custom_components.ge_spot.const.config import Config

# Danish price areas
DANISH_AREAS = ['DK1', 'DK2']

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test Strømlikning API integration')
    parser.add_argument('area', nargs='?', default='DK1',
                        choices=DANISH_AREAS,
                        help='Area code (DK1, DK2)')
    # Add supplier argument
    parser.add_argument('--supplier', required=True,
                        help='Supplier name (e.g., EWII, AndelEnergi)')
    args = parser.parse_args()

    area = args.area
    supplier = args.supplier # Get supplier from args

    logger.info(f"\n===== Strømlikning API Full Chain Test for {area} with Supplier {supplier} =====\n")

    # Create config dictionary using the correct constant
    config = {
        Config.CONF_STROMLIGNING_SUPPLIER: supplier
    }

    # Initialize the API client with config
    api = StromligningAPI(config=config)

    try:
        # Step 1: Fetch raw data
        logger.info(f"Fetching Strømlikning data for area: {area}, supplier: {supplier}")
        # Pass config to fetch_raw_data if needed by underlying methods (though __init__ should handle it now)
        raw_data = await api.fetch_raw_data(area=area)
        logger.debug(f"[Stromligning RAW DATA - {area}] Full raw_data object: {json.dumps(raw_data, indent=2)}")  # Log the raw data structure

        if not raw_data:
            logger.error("Error: Failed to fetch data from Strømlikning API")
            return 1

        # Print a sample of the raw data (truncated for readability)
        if isinstance(raw_data, dict):
            logger.info(f"Raw data keys: {list(raw_data.keys())}")
            if "prices" in raw_data and isinstance(raw_data["prices"], list):
                logger.info(f"Received {len(raw_data['prices'])} price points")
                if raw_data["prices"]:
                    logger.info(f"First price point sample: {raw_data['prices'][0]}")
            else:
                raw_data_str = str(raw_data)
                logger.info(f"Raw data sample (truncated): {raw_data_str[:300]}...")
        else:
            logger.info(f"Raw data type: {type(raw_data)}")
            raw_data_str = str(raw_data)
            logger.info(f"Raw data sample (truncated): {raw_data_str[:300]}...")

        # Step 2: Parse raw data
        logger.info("\nParsing raw data...")
        parsed_data = await api.parse_raw_data(raw_data)

        logger.info(f"Parsed data keys: {list(parsed_data.keys())}")
        logger.info(f"Source: {parsed_data.get('source')}")
        logger.info(f"Area: {parsed_data.get('area')}")
        logger.info(f"Currency: {parsed_data.get('currency')}")
        logger.info(f"API Timezone: {parsed_data.get('api_timezone')}")

        # Check if interval prices are available
        interval_prices = parsed_data.get("interval_raw", {})  # Changed from hourly_raw
        if not interval_prices:
            logger.error("Error: No interval prices found in the parsed data")
            logger.error(f"Available keys: {list(parsed_data.keys())}")
            return 1

        logger.info(f"Found {len(interval_prices)} interval prices")

        # Step 3: Currency conversion (DKK -> EUR)
        logger.info(f"\nConverting prices from {parsed_data.get('currency', Currency.DKK)} to {Currency.EUR}...")
        exchange_service = ExchangeRateService()
        await exchange_service.get_rates(force_refresh=True)

        # Convert prices from DKK to EUR and from MWh to kWh
        converted_prices = {}
        for ts, price in interval_prices.items():  # Changed from hourly_prices
            # Convert from DKK to EUR
            price_eur = await exchange_service.convert(
                price,
                parsed_data.get("currency", Currency.DKK),
                Currency.EUR
            )
            # Convert from MWh to kWh
            price_eur_kwh = price_eur / 1000
            converted_prices[ts] = price_eur_kwh

        # Step 4: Display results
        logger.info("\nPrice Information:")
        logger.info(f"Original Currency: {parsed_data.get('currency', Currency.DKK)}/MWh")
        logger.info(f"Converted Currency: {Currency.EUR}/kWh")

        # Group prices by date
        dk_tz = pytz.timezone('Europe/Copenhagen')
        prices_by_date = {}

        for ts, price in interval_prices.items():
            try:
                # Parse the timestamp and convert to local timezone
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(dk_tz)
                date_str = dt.strftime('%Y-%m-%d')
                hour_str = dt.strftime('%H:%M')

                if date_str not in prices_by_date:
                    prices_by_date[date_str] = {}

                prices_by_date[date_str][hour_str] = {
                    'original': price,
                    'converted': converted_prices.get(ts)
                }
            except ValueError as e:
                logger.warning(f"Could not parse timestamp: {ts}, error: {e}")

        # Print prices grouped by date
        for date, hours in sorted(prices_by_date.items()):
            logger.info(f"\nPrices for {date}:")
            curr = parsed_data.get("currency", Currency.DKK)
            logger.info(f"{'Time':<10} {f'{curr}/MWh':<15} {f'{Currency.EUR}/kWh':<15}")
            logger.info("-" * 40)

            for hour, prices in sorted(hours.items()):
                logger.info(f"{hour:<10} {prices['original']:<15.4f} {prices['converted']:<15.6f}")

        # Validate that we have data for today and tomorrow
        today = datetime.now(dk_tz).strftime('%Y-%m-%d')
        tomorrow = (datetime.now(dk_tz) + timedelta(days=1)).strftime('%Y-%m-%d')

        # Check today's data
        if today in prices_by_date:
            today_prices = prices_by_date[today]
            logger.info(f"\nFound {len(today_prices)} price points for today ({today})")

            if len(today_prices) == 24:
                logger.info("✓ Complete set of 24 hourly prices for today")
            else:
                logger.warning(f"⚠ Incomplete data: Found only {len(today_prices)} hourly prices for today (expected 24)")

                # List missing hours for better debugging
                all_hours = set(f"{h:02d}:00" for h in range(24))
                found_hours = set(today_prices.keys())
                missing_hours = all_hours - found_hours
                if missing_hours:
                    logger.warning(f"Missing hours today: {', '.join(sorted(missing_hours))}")
        else:
            logger.warning(f"\nWarning: No prices found for today ({today})")

        # Check tomorrow's data - be more lenient as tomorrow's data may not be available yet
        now_local = datetime.now(dk_tz)
        expect_tomorrow_data = now_local.hour >= 13  # Usually publishes next day prices at ~13:00 CET

        if tomorrow in prices_by_date:
            tomorrow_prices = prices_by_date[tomorrow]
            logger.info(f"\nFound {len(tomorrow_prices)} price points for tomorrow ({tomorrow})")

            if len(tomorrow_prices) == 24:
                logger.info("✓ Complete set of 24 hourly prices for tomorrow")
            else:
                logger.warning(f"⚠ Incomplete data: Found only {len(tomorrow_prices)} hourly prices for tomorrow (expected 24)")

                # List missing hours for better debugging
                all_hours = set(f"{h:02d}:00" for h in range(24))
                found_hours = set(tomorrow_prices.keys())
                missing_hours = all_hours - found_hours
                if missing_hours:
                    logger.warning(f"Missing hours tomorrow: {', '.join(sorted(missing_hours))}")
        elif expect_tomorrow_data:
            logger.warning(f"\nWarning: No prices found for tomorrow ({tomorrow}) even though it's expected")
        else:
            logger.info(f"\nNote: No prices found for tomorrow ({tomorrow}), but that's expected before 13:00 local time")

        # Check if we have price components (Strømlikning specific)
        if parsed_data.get("price_components"):
            logger.info("\nPrice Components Found:")
            for component_name, value in parsed_data.get("price_components", {}).items():
                logger.info(f"- {component_name}: {value}")

        # Final validation - check if we have enough data overall to consider the test successful
        total_prices = len(interval_prices)
        if total_prices >= 22:  # At minimum, we should have most of today's hours
            logger.info("\nTest completed successfully!")
            return 0
        else:
            logger.error(f"\nTest failed: Insufficient price data. Found only {total_prices} prices (expected at least 22)")
            return 1

    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    logger.info("Starting Strømlikning API full chain test...")
    # Note: User needs to provide --supplier argument now
    # Example: python3 tests/manual/integration/stromligning_full_chain.py DK2 --supplier EWII
    sys.exit(asyncio.run(main()))