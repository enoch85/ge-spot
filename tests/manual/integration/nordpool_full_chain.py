#!/usr/bin/env python3
"""
Manual full chain test for Nordpool API.

This script performs an end-to-end test of the Nordpool API integration:
1. Fetches real data from the Nordpool API
2. Parses the raw data
3. Applies timezone conversion
4. Applies currency conversion
5. Validates and displays the results
6. Tests caching functionality (production-like behavior)

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
from custom_components.ge_spot.utils.advanced_cache import AdvancedCache
from custom_components.ge_spot.coordinator.cache_manager import CacheManager
from custom_components.ge_spot.const.defaults import Defaults
from custom_components.ge_spot.timezone.service import TimezoneService
from custom_components.ge_spot.timezone.timezone_converter import TimezoneConverter

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
    
    # Initialize timezone service
    logger.info("Setting up timezone service...")
    # Determine the local timezone based on the area for the timezone service
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
    
    # Create a timezone service object that will be passed to our TimezoneConverter
    tz_config = {
        "timezone_reference": "area"  # Use area timezone as reference
    }
    tz_service = TimezoneService(area=area, config=tz_config)
    logger.info(f"Timezone service initialized for area: {area} using {local_tz_name}")
    
    # Create the TimezoneConverter that will be used for normalization
    tz_converter = TimezoneConverter(tz_service)
    logger.info("TimezoneConverter initialized")
    
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
            
            # Step 2: Process raw data and normalize timezones using the centralized converter
            logger.info("\nProcessing raw data and normalizing timezones...")
            hourly_raw = raw_data.get("hourly_raw", {})
            source_timezone = raw_data.get('timezone')
            logger.info(f"Source: {raw_data.get('source_name')}")
            logger.info(f"Area: {area}")
            logger.info(f"Currency: {raw_data.get('currency')}")
            logger.info(f"API Timezone: {source_timezone}")
            if not hourly_raw:
                logger.error("Error: No hourly prices found in the raw data")
                return 1
                
            logger.info(f"Found {len(hourly_raw)} hourly prices")
            
            # Apply the timezone conversion using the new TimezoneConverter API
            logger.info(f"Normalizing timestamps from {source_timezone} to {local_tz_name}...")
            
            # Use the normalize_hourly_prices method from the TimezoneConverter class
            normalized_prices = tz_converter.normalize_hourly_prices(
                hourly_prices=hourly_raw,
                source_timezone_str=source_timezone,
                preserve_date=True  # Important: preserve date to differentiate today/tomorrow
            )
            
            logger.info(f"After normalization: {len(normalized_prices)} price points")
            
            # Step 3: Currency conversion (local currency -> EUR if needed)
            original_currency = raw_data.get('currency', Currency.EUR)
            target_currency = Currency.SEK if area.startswith('SE') else Currency.EUR
            
            logger.info(f"\nConverting prices from {original_currency} to {target_currency}...")
            exchange_service = DebugExchangeRateService()
            await exchange_service.get_rates(force_refresh=True)
            
            # Convert prices and from MWh to kWh
            converted_prices = {}
            for hour_key, price_info in normalized_prices.items():
                # Extract price from dict structure
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
                converted_prices[hour_key] = price_kwh
            
            # Use the split_into_today_tomorrow method from TimezoneConverter
            today_prices, tomorrow_prices = tz_converter.split_into_today_tomorrow(normalized_prices)
            logger.info(f"Split into today ({len(today_prices)} hours) and tomorrow ({len(tomorrow_prices)} hours)")
            
            # Prepare processed data for caching (similar to what DataProcessor would do)
            timestamp = datetime.now(timezone.utc)
            processed_data = {
                "source": Source.NORDPOOL,
                "area": area,
                "currency": original_currency, 
                "target_currency": target_currency,
                "hourly_prices": today_prices,
                "tomorrow_hourly_prices": tomorrow_prices,
                "converted_prices": converted_prices,
                "source_timezone": raw_data.get('timezone'),
                "target_timezone": local_tz_name,
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
            tomorrow_prices = processed_data.get('tomorrow_hourly_prices', {})
            original_currency = processed_data.get('currency', Currency.EUR)
            target_currency = processed_data.get('target_currency', original_currency)
            converted_prices = processed_data.get('converted_prices', {})
            # If no converted prices in cache, use hourly prices
            if not converted_prices:
                converted_prices = {}
                # Convert hourly prices from today
                for hour, value in hourly_prices.items():
                    price = value["price"] if isinstance(value, dict) else value
                    converted_prices[hour] = price / 1000  # Simple MWh to kWh conversion
                # Convert hourly prices from tomorrow
                for hour, value in tomorrow_prices.items():
                    price = value["price"] if isinstance(value, dict) else value
                    converted_prices[hour] = price / 1000  # Simple MWh to kWh conversion
        
        # Step 4: Display results (whether from cache or fresh fetch)
        logger.info("\nPrice Information:")
        logger.info(f"Original Currency: {original_currency}/MWh")
        logger.info(f"Converted Currency: {target_currency}/kWh")
        logger.info(f"Data source: {'Cache' if using_cached else 'Live API'}")
        
        # Combine today and tomorrow prices for display
        all_hourly_prices = {**processed_data.get('hourly_prices', {}), **processed_data.get('tomorrow_hourly_prices', {})}
        
        # Create a nice display of prices by hour
        logger.info("\nHourly Prices (formatted as HH:00 in target timezone):")
        logger.info(f"{'Hour':<10} {f'{original_currency}/MWh':<15} {f'{target_currency}/kWh':<15}")
        logger.info("-" * 40)
        
        for hour_key, price in sorted(all_hourly_prices.items()):
            price_value = price["price"] if isinstance(price, dict) else price
            converted_value = converted_prices.get(hour_key, price_value / 1000)
            logger.info(f"{hour_key:<10} {price_value:<15.4f} {converted_value:<15.6f}")
        
        # Validate that we have data for today and tomorrow
        today_hour_range = tz_service.get_today_range()
        tomorrow_hour_range = tz_service.get_tomorrow_range()
        
        today_hours = set(processed_data.get('hourly_prices', {}).keys())
        tomorrow_hours = set(processed_data.get('tomorrow_hourly_prices', {}).keys())
        
        # Check today's data completeness
        today_complete = today_hours.issuperset(today_hour_range)
        tomorrow_complete = tomorrow_hours.issuperset(tomorrow_hour_range)
        
        logger.info(f"\nData completeness:")
        logger.info(f"Today: {len(today_hours)}/{len(today_hour_range)} hours {'✓' if today_complete else '⚠'}")
        logger.info(f"Tomorrow: {len(tomorrow_hours)}/{len(tomorrow_hour_range)} hours {'✓' if tomorrow_complete else '⚠'}")
        
        if not today_complete:
            missing_today = set(today_hour_range) - today_hours
            logger.warning(f"Missing today hours: {', '.join(sorted(missing_today))}")
            
        if not tomorrow_complete:
            # Only warn about missing tomorrow hours after 13:00 CET when they should be available
            now_utc = datetime.now(timezone.utc)
            now_cet = now_utc.astimezone(pytz.timezone('Europe/Oslo'))
            
            if now_cet.hour >= 13 or reference_date:
                missing_tomorrow = set(tomorrow_hour_range) - tomorrow_hours
                logger.warning(f"Missing tomorrow hours: {', '.join(sorted(missing_tomorrow))}")
        
        # Final validation - check if we have enough data overall to consider the test successful
        total_prices = len(today_hours) + len(tomorrow_hours)
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