#!/usr/bin/env python3
"""
Manual full chain test for Nordpool API.

This script performs an end-to-end test of the Nordpool API integration:
1. Fetches real data from the Nordpool API
2. Parses the raw data
3. Applies currency conversion
4. Validates and displays the results
5. Tests caching functionality (production-like behavior)

Usage:
    python nordpool_full_chain.py [area] [date]
    
    area: Optional area code (e.g., SE1, SE2, SE3, SE4, FI, DK1, etc.)
          Defaults to SE3 if not provided
    date: Optional date to fetch data for (format: YYYY-MM-DD)
          Defaults to today if not provided
"""

import sys
import os
import argparse
from datetime import datetime, timezone, timedelta, date
import asyncio
import pytz
import logging
import tempfile
import json
import time
from typing import Dict, Any, Optional

# Set up logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add the root directory to the path so we can import the component modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from custom_components.ge_spot.api.nordpool import NordpoolAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService
from custom_components.ge_spot.price.advanced_cache import AdvancedCache
from custom_components.ge_spot.coordinator.cache_manager import CacheManager
from custom_components.ge_spot.const.defaults import Defaults

# Common Nordpool areas
COMMON_AREAS = [
    'SE1', 'SE2', 'SE3', 'SE4',  # Sweden
    'FI',                        # Finland
    'DK1', 'DK2',                # Denmark
    'NO1', 'NO2', 'NO3', 'NO4', 'NO5',  # Norway
    'EE', 'LV', 'LT',            # Baltic states
    'Oslo', 'Kr.sand', 'Bergen', 'Molde', 'Tr.heim', 'Tromsø',  # Norway cities
    'SYS'                        # System price
]

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

# Wrapper for CacheManager to add enhanced debug logging
class DebugCacheManager(CacheManager):
    """Cache Manager with enhanced debug logging."""
    
    def __init__(self, hass, config):
        """Initialize the debug cache manager."""
        super().__init__(hass, config)
        logger.debug(f"Debug Cache Manager initialized with config: {json.dumps(config, default=str)}")
        logger.debug(f"Cache directory: {self._price_cache._get_cache_file_path()}")
    
    def store(self, area, source, data, timestamp=None):
        """Store data with debug logging."""
        cache_key = self._generate_cache_key(area, source, timestamp.date() if timestamp else datetime.now().date())
        logger.debug(f"CACHE STORE: Storing data for key '{cache_key}'")
        logger.debug(f"  - Timestamp: {timestamp}")
        logger.debug(f"  - Data size: {len(str(data))} bytes")
        logger.debug(f"  - Contains {len(data.get('hourly_prices', {}))} price points")
        
        # Call original method
        result = super().store(area, source, data, timestamp)
        
        # Log cache stats after storing
        cache_info = self._price_cache.get_info()
        logger.debug(f"CACHE STATS after store: {len(cache_info.get('entries', {}))} entries in cache")
        return result
    
    def get_data(self, area, target_date, source=None, max_age_minutes=None):
        """Get data with debug logging."""
        if source:
            cache_key = self._generate_cache_key(area, source, target_date)
            logger.debug(f"CACHE GET: Looking for specific key '{cache_key}'")
        else:
            logger.debug(f"CACHE GET: Looking for any source for area '{area}' and date '{target_date}'")
        
        if max_age_minutes:
            logger.debug(f"  - Max age filter: {max_age_minutes} minutes")
        
        # Call original method
        result = super().get_data(area, target_date, source, max_age_minutes)
        
        if result:
            logger.debug(f"CACHE HIT: Found data with {len(result.get('hourly_prices', {}))} price points")
            ts = result.get('last_updated')
            if ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    age = (datetime.now(dt.tzinfo) - dt).total_seconds() / 60
                    logger.debug(f"  - Data age: {age:.1f} minutes")
                except (ValueError, TypeError):
                    logger.debug(f"  - Last updated: {ts}")
        else:
            logger.debug("CACHE MISS: No valid data found in cache")
        
        return result
    
    def clear_cache(self, area=None, target_date=None):
        """Clear cache with debug logging."""
        if area:
            logger.debug(f"CACHE CLEAR: Clearing cache for area '{area}'")
            if target_date:
                logger.debug(f"  - Only clearing date: {target_date}")
        else:
            logger.debug("CACHE CLEAR: Clearing all cache entries")
            
        result = super().clear_cache(area, target_date)
        logger.debug(f"CACHE CLEAR result: {result}")
        return result
    
    def get_cache_stats(self):
        """Get cache stats with additional debug info."""
        stats = super().get_cache_stats()
        
        # Enhanced logging of cache entries
        entries = stats.get('entries', {})
        if entries:
            logger.debug(f"CACHE DETAIL: {len(entries)} entries in cache")
            
            # Group by area and source
            area_sources = {}
            for key, entry in entries.items():
                metadata = entry.get('metadata', {})
                area = metadata.get('area', 'unknown')
                source = metadata.get('source', 'unknown')
                target_date = metadata.get('target_date', 'unknown')
                
                if area not in area_sources:
                    area_sources[area] = {}
                
                if source not in area_sources[area]:
                    area_sources[area][source] = []
                
                area_sources[area][source].append(target_date)
            
            # Log the grouped entries
            for area, sources in area_sources.items():
                for source, dates in sources.items():
                    dates_str = ", ".join(sorted(dates))
                    logger.debug(f"  - Area: {area}, Source: {source}, Dates: {dates_str}")
        
        return stats

class DebugExchangeRateService(ExchangeRateService):
    """Exchange Rate Service with enhanced debug logging."""
    
    def __init__(self, session=None, cache_file=None):
        """Initialize with debug logging."""
        super().__init__(session, cache_file)
        actual_cache_path = cache_file or self._get_default_cache_path()
        logger.debug(f"EXCHANGE CACHE: Initialized with cache file: {actual_cache_path}")
        
    async def _load_cache(self):
        """Load exchange rates from cache with debug logging."""
        logger.debug(f"EXCHANGE CACHE: Attempting to load from {self.cache_file}")
        
        if not os.path.exists(self.cache_file):
            logger.debug("EXCHANGE CACHE: Cache file does not exist")
            return False
            
        try:
            modified_time = os.path.getmtime(self.cache_file)
            cache_age = time.time() - modified_time
            logger.debug(f"EXCHANGE CACHE: File exists, age: {cache_age:.1f}s")
            
            result = await super()._load_cache()
            
            if result:
                logger.debug(f"EXCHANGE CACHE: Successfully loaded {len(self.rates)} currency rates")
                for currency, rate in sorted(list(self.rates.items()))[:5]:
                    logger.debug(f"  - {currency}: {rate}")
                if len(self.rates) > 5:
                    logger.debug(f"  - ... and {len(self.rates)-5} more currencies")
            else:
                logger.debug("EXCHANGE CACHE: Failed to load cache (invalid format)")
            
            return result
            
        except Exception as e:
            logger.error(f"EXCHANGE CACHE: Error loading: {e}")
            return False
            
    async def _save_cache(self):
        """Save exchange rates to cache with debug logging."""
        logger.debug(f"EXCHANGE CACHE: Saving {len(self.rates)} currency rates to {self.cache_file}")
        result = await super()._save_cache()
        logger.debug(f"EXCHANGE CACHE: Save {'succeeded' if result else 'failed'}")
        return result
        
    async def get_rates(self, force_refresh=False):
        """Get exchange rates with debug logging."""
        logger.debug(f"EXCHANGE CACHE: Getting rates (force_refresh={force_refresh})")
        
        if not self.rates:
            logger.debug("EXCHANGE CACHE: No rates in memory, will try to load from cache")
        elif force_refresh:
            logger.debug("EXCHANGE CACHE: Force refresh requested")
        
        rates = await super().get_rates(force_refresh)
        logger.debug(f"EXCHANGE CACHE: Returned {len(rates)} currency rates")
        return rates
        
    async def convert(self, amount, from_currency, to_currency):
        """Convert currency with debug logging."""
        if from_currency == to_currency:
            return amount
            
        logger.debug(f"EXCHANGE CONVERT: {amount} {from_currency} → {to_currency}")
        result = await super().convert(amount, from_currency, to_currency)
        logger.debug(f"EXCHANGE CONVERT: Result = {result}")
        return result

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test Nordpool API integration')
    parser.add_argument('area', nargs='?', default='SE3', 
                        help=f'Area code (e.g., {", ".join(COMMON_AREAS[:5])})')
    parser.add_argument('date', nargs='?', default=None,
                        help='Date to fetch data for (format: YYYY-MM-DD, default: today)')
    parser.add_argument('--no-cache', action='store_true', help='Skip cache check and force fetch from API')
    parser.add_argument('--clear-cache', action='store_true', help='Clear the cache before testing')
    args = parser.parse_args()
    
    area = args.area
    reference_date = args.date
    force_fetch = args.no_cache
    clear_cache = args.clear_cache
    
    # Process reference date if provided
    reference_time = None
    target_date = datetime.now().date()
    if reference_date:
        try:
            # Parse the date and create a datetime at noon UTC for that date
            ref_date_obj = datetime.strptime(reference_date, '%Y-%m-%d')
            target_date = ref_date_obj.date()
            reference_time = ref_date_obj.replace(
                hour=12, minute=0, second=0
            ).astimezone(timezone.utc)
            logger.info(f"Using reference date: {reference_date} (reference time: {reference_time})")
        except ValueError:
            logger.error(f"Invalid date format: {reference_date}. Please use YYYY-MM-DD format.")
            return 1
    
    logger.info(f"\n===== Nordpool API Full Chain Test for {area} =====\n")
    
    # Setup cache with production-like behavior
    logger.info("Setting up cache manager (production-like behavior)...")
    mock_hass = MockHass()
    cache_config = {
        "cache_ttl": Defaults.CACHE_TTL,
        "cache_max_entries": Defaults.CACHE_MAX_ENTRIES,
        "persist_cache": True,
    }
    cache_manager = DebugCacheManager(mock_hass, cache_config)
    
    if clear_cache:
        logger.info("Clearing existing cache...")
        cache_manager.clear_cache()
    
    # Initialize the API client
    api = NordpoolAPI()
    
    try:
        # Production-like behavior: Check cache first unless forced to skip
        processed_data = None
        if not force_fetch:
            logger.info("Checking cache for existing data...")
            cached_data = cache_manager.get_data(area=area, target_date=target_date, source=Source.NORDPOOL)
            
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
            logger.info(f"Fetching Nordpool data for area: {area}")
            raw_data = await api.fetch_raw_data(area=area, reference_time=reference_time)
            if not raw_data:
                logger.error("Error: Failed to fetch data from Nordpool API")
                return 1
            
            logger.info(f"Raw data keys: {list(raw_data.keys())}")
            # Print a sample of the raw data (truncated for readability)
            if "raw_data" in raw_data and raw_data["raw_data"]:
                sample_data = str(raw_data["raw_data"])[:300]
                logger.info(f"Raw data sample (truncated): {sample_data}...")
            else:
                logger.warning("No 'raw_data' found in API response")
            
            # Step 2: Use hourly_raw directly (no parse_raw_data)
            logger.info("\nProcessing raw data...")
            hourly_prices = raw_data.get("hourly_raw", {})
            logger.info(f"Source: {raw_data.get('source_name')}")
            logger.info(f"Area: {area}")
            logger.info(f"Currency: {raw_data.get('currency')}")
            logger.info(f"API Timezone: {raw_data.get('timezone')}")
            if not hourly_prices:
                logger.error("Error: No hourly prices found in the raw data")
                return 1
                
            logger.info(f"Found {len(hourly_prices)} hourly prices")
            
            # Step 3: Currency conversion (local currency -> EUR if needed)
            original_currency = raw_data.get('currency', Currency.EUR)
            target_currency = Currency.SEK if area.startswith('SE') else Currency.EUR
            
            logger.info(f"\nConverting prices from {original_currency} to {target_currency}...")
            exchange_service = DebugExchangeRateService()
            await exchange_service.get_rates(force_refresh=True)
            
            # Convert prices and from MWh to kWh
            converted_prices = {}
            for ts, price_info in hourly_prices.items():
                # Support new dict structure from parser
                price = price_info["price"] if isinstance(price_info, dict) else price_info
                price_converted = price
                if original_currency != target_currency:
                    price_converted = await exchange_service.convert(
                        price, 
                        original_currency,
                        target_currency
                    )
                # Convert from MWh to kWh
                price_kwh = price_converted / 1000
                converted_prices[ts] = price_kwh
            
            # Prepare processed data for caching (similar to what DataProcessor would do)
            timestamp = datetime.now(timezone.utc)
            processed_data = {
                "source": Source.NORDPOOL,
                "area": area,
                "currency": original_currency, 
                "target_currency": target_currency,
                "hourly_prices": hourly_prices,
                "converted_prices": converted_prices,
                "source_timezone": raw_data.get('timezone'),
                "api_timezone": raw_data.get('timezone'),
                "last_updated": timestamp.isoformat(),
                "using_cached_data": False
            }
            
            # Store in cache for future use (production behavior)
            logger.info("\nStoring data in cache for future use...")
            cache_manager.store(
                area=area,
                source=Source.NORDPOOL,
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
            original_currency = processed_data.get('currency', Currency.EUR)
            target_currency = processed_data.get('target_currency', original_currency)
            converted_prices = processed_data.get('converted_prices', {})
            # If no converted prices in cache, use hourly prices
            if not converted_prices:
                converted_prices = {k: v/1000 for k, v in hourly_prices.items()}
        
        # Step 4: Display results (whether from cache or fresh fetch)
        logger.info("\nPrice Information:")
        logger.info(f"Original Currency: {original_currency}/MWh")
        logger.info(f"Converted Currency: {target_currency}/kWh")
        logger.info(f"Data source: {'Cache' if using_cached else 'Live API'}")
        
        # Determine the local timezone based on the area
        local_tz_name = 'Europe/Stockholm'  # Default for Swedish areas
        if area.startswith('FI'):
            local_tz_name = 'Europe/Helsinki'
        elif area.startswith('DK'):
            local_tz_name = 'Europe/Copenhagen'
        elif area.startswith('NO') or area in ['Oslo', 'Kr.sand', 'Bergen', 'Molde', 'Tr.heim', 'Tromsø']:
            local_tz_name = 'Europe/Oslo'
        elif area in ['EE']:
            local_tz_name = 'Europe/Tallinn'
        elif area in ['LV']:
            local_tz_name = 'Europe/Riga'
        elif area in ['LT']:
            local_tz_name = 'Europe/Vilnius'
        
        local_tz = pytz.timezone(local_tz_name)
        prices_by_date = {}
        
        for ts, price in hourly_prices.items():
            try:
                # Parse the timestamp and convert to local timezone
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(local_tz)
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
            logger.info(f"{'Time':<10} {f'{original_currency}/MWh':<15} {f'{target_currency}/kWh':<15}")
            logger.info("-" * 40)
            
            for hour, prices in sorted(hours.items()):
                original_val = prices['original']['price'] if isinstance(prices['original'], dict) else prices['original']
                logger.info(f"{hour:<10} {original_val:<15.4f} {prices['converted']:<15.6f}")
        
        # Validate that we have data for today and tomorrow
        today = datetime.now(local_tz).strftime('%Y-%m-%d')
        tomorrow = (datetime.now(local_tz) + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # If reference_date is provided, adjust today/tomorrow expectations
        if reference_date:
            ref_date_obj = datetime.strptime(reference_date, '%Y-%m-%d')
            today = ref_date_obj.strftime('%Y-%m-%d')
            tomorrow = (ref_date_obj + timedelta(days=1)).strftime('%Y-%m-%d')
            logger.info(f"Using reference dates: today={today}, tomorrow={tomorrow}")
        
        # Check today's data - be more flexible with the requirements
        if today in prices_by_date:
            today_prices = prices_by_date[today]
            logger.info(f"\nFound {len(today_prices)} price points for today ({today})")
            
            if len(today_prices) >= 22:  # Allow for some missing hours
                logger.info(f"✓ Found {len(today_prices)}/24 hourly prices for today")
            else:
                logger.warning(f"⚠ Incomplete data: Found only {len(today_prices)} hourly prices for today (expected at least 22)")
                
                # If we have coverage information, log it
                if "today_coverage" in raw_data:
                    logger.info(f"Today's coverage: {raw_data['today_coverage']:.1f}%")
                
                # List missing hours for better debugging
                all_hours = set(f"{h:02d}:00" for h in range(24))
                found_hours = set(today_prices.keys())
                missing_hours = all_hours - found_hours
                if missing_hours:
                    logger.warning(f"Missing hours today: {', '.join(sorted(missing_hours))}")
        else:
            logger.warning(f"\nWarning: No prices found for today ({today})")
        
        # Check tomorrow's data - be more lenient as tomorrow's data may not be available yet
        now_local = datetime.now(local_tz)
        expect_tomorrow_data = now_local.hour >= 13  # Nordpool usually publishes next day prices at ~13:00 CET
        
        # If we specifically requested a date, we should expect tomorrow's data
        if reference_date:
            expect_tomorrow_data = True
            logger.info("Reference date provided - expecting tomorrow's data to be available")
        
        if tomorrow in prices_by_date:
            tomorrow_prices = prices_by_date[tomorrow]
            logger.info(f"\nFound {len(tomorrow_prices)} price points for tomorrow ({tomorrow})")
            
            if len(tomorrow_prices) >= 22:  # Allow for some missing hours
                logger.info(f"✓ Found {len(tomorrow_prices)}/24 hourly prices for tomorrow")
            else:
                logger.warning(f"⚠ Incomplete data: Found only {len(tomorrow_prices)} hourly prices for tomorrow (expected 24)")
                
                # If we have coverage information, log it
                if "tomorrow_coverage" in raw_data:
                    logger.info(f"Tomorrow's coverage: {raw_data['tomorrow_coverage']:.1f}%")
                
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
        
        # Final validation - check if we have enough data overall to consider the test successful
        total_prices = len(hourly_prices)
        if total_prices >= 22:  # At minimum, we should have most of today's hours
            logger.info("\nTest completed successfully!")
            return 0
        else:
            logger.error(f"\nTest failed: Insufficient price data. Found only {total_prices} prices (expected at least 22)")
            return 1
        
    except Exception as e:
        logger.error(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    logger.info("Starting Nordpool API full chain test...")
    sys.exit(asyncio.run(main()))