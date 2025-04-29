#!/usr/bin/env python3
"""
Manual full chain test for Amber API (Australia).

This script performs an end-to-end test of the Amber API integration:
1. Fetches real data from the Amber API
2. Parses the raw data
3. Applies currency conversion
4. Validates and displays the results
5. Tests caching functionality (production-like behavior)

Usage:
    python amber_full_chain.py [area] [api_key]
    
    area: Optional area code (defaults to NSW)
    api_key: Optional Amber API key
             Can also be provided via AMBER_API_KEY environment variable
    --no-cache: Skip cache check and force fetch from API
    --clear-cache: Clear the cache before testing
"""

import sys
import os
import argparse
import getpass
from datetime import datetime, timezone
import asyncio
import pytz
import logging
import tempfile
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Add the root directory to the path so we can import the component modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from custom_components.ge_spot.api.amber import AmberAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService
from custom_components.ge_spot.utils.advanced_cache import AdvancedCache
from custom_components.ge_spot.coordinator.cache_manager import CacheManager
from custom_components.ge_spot.const.defaults import Defaults

# Mock Home Assistant instance for the cache manager
class MockHass:
    """Mock Home Assistant instance with minimal functionality needed for caching."""
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        # Create a mock config structure
        self.config = MockConfig(self.temp_dir)
        
    def get_path(self, key):
        """Mimic the Home Assistant get_path method for cache."""
        return self.temp_dir

class MockConfig:
    """Mock Home Assistant config with path method."""
    def __init__(self, config_dir):
        self.config_dir = config_dir
        
    def path(self, *args):
        """Mimic the Home Assistant config.path method."""
        if args:
            return os.path.join(self.config_dir, *args)
        return self.config_dir

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test Amber API integration')
    parser.add_argument('area', nargs='?', default='NSW',
                        help='Area code (defaults to NSW)')
    parser.add_argument('api_key', nargs='?', default=None,
                        help='Amber API key (optional if environment variable is set)')
    parser.add_argument('--no-cache', action='store_true', help='Skip cache check and force fetch from API')
    parser.add_argument('--clear-cache', action='store_true', help='Clear the cache before testing')
    args = parser.parse_args()
    
    area = args.area
    force_fetch = args.no_cache
    clear_cache = args.clear_cache
    
    # Get API key from arguments, environment, or prompt
    api_key = args.api_key or os.environ.get("AMBER_API_KEY")
    if not api_key:
        api_key = getpass.getpass("Enter your Amber API key: ")
    
    logger.info(f"\n===== Amber API Full Chain Test for {area} =====\n")
    
    # Setup cache with production-like behavior
    logger.info("Setting up cache manager (production-like behavior)...")
    mock_hass = MockHass()
    cache_config = {
        "cache_ttl": Defaults.CACHE_TTL,
        "cache_max_entries": Defaults.CACHE_MAX_ENTRIES,
        "persist_cache": True,
    }
    cache_manager = CacheManager(mock_hass, cache_config)
    
    if clear_cache:
        logger.info("Clearing existing cache...")
        cache_manager.clear_cache()
    
    # Initialize the API client with the API key
    api = AmberAPI(config={"api_key": api_key})
    target_date = datetime.now().date()
    
    try:
        # Production-like behavior: Check cache first unless forced to skip
        processed_data = None
        if not force_fetch:
            logger.info("Checking cache for existing data...")
            cached_data = cache_manager.get_data(area=area, target_date=target_date, source=Source.AMBER)
            
            if cached_data:
                logger.info("✓ Found data in cache!")
                logger.info(f"Cache timestamp: {cached_data.get('last_updated', 'unknown')}")
                cached_hourly_prices = cached_data.get('hourly_prices', {})
                logger.info(f"Cached data contains {len(cached_hourly_prices)} price points")
                processed_data = cached_data
                logger.info("Using cached data (as would happen in production)")
            else:
                logger.info("No valid cache entry found, will fetch from API")
        else:
            logger.info("Cache check skipped due to --no-cache flag")
        
        # If no cached data or forced refresh, fetch from API
        if processed_data is None:
            # Step 1: Fetch raw data
            logger.info(f"Fetching Amber data for area: {area}")
            raw_data = await api.fetch_raw_data(area=area)
            
            if not raw_data:
                logger.error("Error: Failed to fetch data from Amber API")
                return 1
                
            # Print a sample of the raw data (truncated for readability)
            if isinstance(raw_data, list):
                logger.info(f"Received {len(raw_data)} data points")
                if raw_data:
                    logger.info(f"First data point sample: {raw_data[0]}")
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
            
            # Check if hourly prices are available
            hourly_prices = parsed_data.get("hourly_prices", {})
            if not hourly_prices:
                logger.warning("Warning: No hourly prices found in the parsed data")
                return 1
                
            logger.info(f"Found {len(hourly_prices)} hourly prices")
            
            # Step 3: Currency conversion (AUD -> USD)
            logger.info("\nConverting prices from AUD to USD...")
            exchange_service = ExchangeRateService()
            await exchange_service.get_rates(force_refresh=True)
            
            # Convert prices from AUD to USD and from MWh to kWh
            converted_prices = {}
            for ts, price in hourly_prices.items():
                # Convert from AUD to USD
                price_usd = await exchange_service.convert(
                    price, 
                    parsed_data.get("currency", Currency.AUD), 
                    Currency.USD
                )
                # Convert from MWh to kWh
                price_usd_kwh = price_usd / 1000
                converted_prices[ts] = price_usd_kwh
            
            # Prepare processed data for caching (production-like behavior)
            timestamp = datetime.now(timezone.utc)
            processed_data = {
                "source": Source.AMBER,
                "area": area,
                "currency": parsed_data.get("currency", Currency.AUD), 
                "target_currency": Currency.USD,
                "hourly_prices": hourly_prices,
                "converted_prices": converted_prices,
                "source_timezone": parsed_data.get('api_timezone'),
                "api_timezone": parsed_data.get('api_timezone'),
                "last_updated": timestamp.isoformat(),
                "using_cached_data": False
            }
            
            # Store in cache for future use (production behavior)
            logger.info("\nStoring data in cache for future use...")
            cache_manager.store(
                area=area,
                source=Source.AMBER,
                data=processed_data,
                timestamp=timestamp
            )
            logger.info("✓ Data stored in cache")
            
            # Show cache statistics
            cache_stats = cache_manager.get_cache_stats()
            logger.info(f"Cache now contains {len(cache_stats.get('entries', {}))} entries")
        
        # Determine if we're using cached data
        using_cached = processed_data.get('using_cached_data', False)
        if using_cached:
            logger.info("\n=== Using cached data ===")
            hourly_prices = processed_data.get('hourly_prices', {})
            original_currency = processed_data.get('currency', Currency.AUD)
            target_currency = processed_data.get('target_currency', Currency.USD)
            converted_prices = processed_data.get('converted_prices', {})
            # If no converted prices in cache, regenerate them
            if not converted_prices:
                logger.info("Regenerating converted prices from cached hourly prices...")
                converted_prices = {}
                exchange_service = ExchangeRateService()
                await exchange_service.get_rates()
                for ts, price in hourly_prices.items():
                    price_usd = await exchange_service.convert(price, original_currency, target_currency)
                    price_usd_kwh = price_usd / 1000
                    converted_prices[ts] = price_usd_kwh
        
        # Step 4: Display results (whether from cache or fresh fetch)
        logger.info("\nPrice Information:")
        logger.info(f"Original Currency: {processed_data.get('currency', Currency.AUD)}/MWh")
        logger.info(f"Converted Currency: {Currency.USD}/kWh")
        logger.info(f"Data source: {'Cache' if using_cached else 'Live API'}")
        
        # Group prices by date
        api_timezone = processed_data.get('api_timezone', 'Australia/Sydney')
        au_tz = pytz.timezone(api_timezone)
        prices_by_date = {}
        
        for ts, price in hourly_prices.items():
            # Parse the timestamp and convert to local timezone
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(au_tz)
            date_str = dt.strftime('%Y-%m-%d')
            hour_str = dt.strftime('%H:%M')
            
            if date_str not in prices_by_date:
                prices_by_date[date_str] = {}
                
            prices_by_date[date_str][hour_str] = {
                'original': price,
                'converted': converted_prices.get(ts)
            }
        
        # Print prices grouped by date
        for date, hours in sorted(prices_by_date.items()):
            logger.info(f"\nPrices for {date}:")
            logger.info(f"{'Time':<10} {'AUD/MWh':<15} {'USD/kWh':<15}")
            logger.info("-" * 40)
            
            for hour, prices in sorted(hours.items()):
                logger.info(f"{hour:<10} {prices['original']:<15.4f} {prices['converted']:<15.6f}")
        
        # Validate that we have data for the current day
        today = datetime.now(au_tz).strftime('%Y-%m-%d')
        if today in prices_by_date:
            today_prices = prices_by_date[today]
            logger.info(f"\nFound {len(today_prices)} price points for today ({today})")
        else:
            logger.warning(f"\nWarning: No prices found for today ({today})")
        
        logger.info("\nTest completed successfully!")
        return 0
        
    except Exception as e:
        logger.error(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    logger.info("Starting Amber API full chain test...")
    sys.exit(asyncio.run(main()))
