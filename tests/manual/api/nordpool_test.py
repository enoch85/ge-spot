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
import json
import aiohttp

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from custom_components.ge_spot.api.nordpool import NordpoolAPI
from custom_components.ge_spot.const.areas import Area
from custom_components.ge_spot.timezone.service import TimezoneService
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

async def main():
    # Get area code from command line or use default
    area_code = sys.argv[1] if len(sys.argv) > 1 else "SE3"
    
    logger.info(f"Testing Nordpool API for area: {area_code}")
    
    # Initialize timezone service
    timezone_service = TimezoneService(area=area_code)
    
    # Initialize API with timezone service
    async with aiohttp.ClientSession() as session:
        api = NordpoolAPI(timezone_service=timezone_service, session=session)
        
        # Test connection
        logger.info("Testing API connection...")
        try:
            # Fetch raw data
            logger.info("Fetching data from Nordpool API...")
            
            # Call the fetch_raw_data method with the area code
            raw_data = await api.fetch_raw_data(area_code)
            
            # Debug: Print raw data keys
            logger.info(f"Raw data keys: {list(raw_data.keys()) if raw_data else 'None'}")
            
            # Check more detailed content of raw_data
            if raw_data and "raw_data" in raw_data:
                if "today" in raw_data["raw_data"]:
                    logger.info("Today's data found in response")
                else:
                    logger.info("Today's data NOT found in response")
                    
                if "tomorrow" in raw_data["raw_data"]:
                    logger.info("Tomorrow's data found in response")
                else:
                    logger.info("Tomorrow's data NOT found in response")
                    
                # Print a snippet of the raw data for debugging
                logger.info("\nRaw data sample (first 500 chars):")
                logger.info(str(raw_data)[:500] + "...")
            
            # Check if we have data - more flexible check
            if not raw_data:
                logger.error("Failed to fetch any data from Nordpool API")
                return 1
                
            if "hourly_raw" in raw_data and raw_data["hourly_raw"]:
                logger.info(f"Successfully fetched {len(raw_data['hourly_raw'])} hourly price points")
            elif not raw_data.get("raw_data", {}).get("today"):
                logger.error("Failed to fetch today's data from Nordpool API")
                return 1
            else:
                logger.info("Found raw data but no hourly prices extracted")
                
            logger.info("Successfully fetched raw data")
            
            # Instead of using parse_raw_data, we'll work with the hourly_raw data directly
            logger.info("Processing raw data...")
            hourly_prices = raw_data.get('hourly_raw', {})
            
            if not hourly_prices:
                logger.error("No hourly prices available in the raw data")
                return 1
            
            # Convert prices from EUR to SEK
            logger.info("Converting prices from EUR to SEK...")
            exchange_service = ExchangeRateService(session=session)
            # Use get_rates instead of update
            await exchange_service.get_rates(force_refresh=True)
            
            # Format data for display
            formatted_prices = {}
            for timestamp_utc, price_data in hourly_prices.items():
                # Convert UTC timestamp to local time (Europe/Stockholm for SE areas)
                utc_dt = datetime.fromisoformat(timestamp_utc.replace('+00:00', ''))
                local_dt = utc_dt.astimezone(timezone_service.area_timezone)
                local_time_str = local_dt.strftime('%Y-%m-%d %H:%M')
                
                if isinstance(price_data, dict):
                    price_eur = price_data.get('price', 0)
                else:
                    price_eur = price_data
                
                # Convert EUR/MWh to SEK/kWh
                price_sek = await exchange_service.convert(price_eur, 'EUR', 'SEK') 
                price_sek_kwh = price_sek / 1000  # Convert from MWh to kWh
                
                formatted_prices[local_time_str] = {
                    'price_eur_mwh': price_eur,
                    'price_sek_mwh': price_sek,
                    'price_sek_kwh': price_sek_kwh,
                    'price_ore_kwh': price_sek_kwh * 100  # Convert to öre/kWh (1 SEK = 100 öre)
                }
            
            num_hourly_prices = len(formatted_prices)
            logger.info(f"Successfully processed {num_hourly_prices} hourly prices.")
            
            # Group by date
            prices_by_date = {}
            for timestamp, price_info in formatted_prices.items():
                date = timestamp.split(' ')[0]
                if date not in prices_by_date:
                    prices_by_date[date] = {}
                hour = timestamp.split(' ')[1]
                prices_by_date[date][hour] = price_info
            
            # Display results
            logger.info("\nParsed Data:")
            logger.info(f"Source: nordpool")
            logger.info(f"Area: {area_code}")
            logger.info(f"Currency: EUR (original), SEK (converted)")
            logger.info(f"API Timezone: {raw_data.get('timezone', 'Unknown')}")
            logger.info(f"Local Timezone: {timezone_service.area_timezone}")
            
            # Format hourly prices into a table
            logger.info("\nHourly Prices:")
            logger.info(f"{'Timestamp':<20} | {'EUR/MWh':<10} | {'SEK/kWh':<10} | {'öre/kWh':<10}")
            logger.info("-" * 60)
            
            # Format for display with date as header and hours below
            for date in sorted(prices_by_date.keys()):
                logger.info(f"\nDate: {date}")
                for hour in sorted(prices_by_date[date].keys()):
                    price_info = prices_by_date[date][hour]
                    logger.info(f"{hour:<20} | {price_info['price_eur_mwh']:<10.2f} | {price_info['price_sek_kwh']:<10.5f} | {price_info['price_ore_kwh']:<10.2f}")
            
            logger.info("\nTest completed successfully")
            return 0

        except Exception as e:
            logger.error(f"Error: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))