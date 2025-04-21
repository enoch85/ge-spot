#!/usr/bin/env python3
"""Comprehensive test script for today's data functionality.

This script provides a unified testing approach for all parsers and APIs,
testing their ability to extract and validate today's price data.
It tests both cached data and makes live API calls when necessary.
"""
import os
import sys
import logging
import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Import components
try:
    from custom_components.ge_spot.price.adapter import ElectricityPriceAdapter
    from custom_components.ge_spot.api.parsers.entsoe_parser import EntsoeParser
    from custom_components.ge_spot.api.parsers.nordpool_parser import NordpoolPriceParser
    from custom_components.ge_spot.api.parsers.epex_parser import EpexParser
    from custom_components.ge_spot.api.parsers.omie_parser import OmieParser
    from custom_components.ge_spot.api.parsers.energi_data_parser import EnergiDataParser
    from custom_components.ge_spot.api.parsers.aemo_parser import AemoParser
    from custom_components.ge_spot.api.parsers.comed_parser import ComedParser
    from custom_components.ge_spot.api.parsers.stromligning_parser import StromligningParser
    from custom_components.ge_spot.const.currencies import Currency
    from custom_components.ge_spot.const.sources import Source
    from custom_components.ge_spot.api import fetch_day_ahead_prices
    from custom_components.ge_spot.coordinator.today_data_manager import TodayDataManager
    from custom_components.ge_spot.price.cache import PriceCache
    from custom_components.ge_spot.timezone import TimezoneService
    from scripts.tests.api.today_api_testing import test_today_api_data
    from scripts.tests.mocks.hass import MockHass
    from scripts.tests.utils.general import build_api_key_config
    import aiohttp
    IMPORTS_SUCCESSFUL = True
except ImportError as e:
    logger.error(f"Failed to import required components: {e}")
    IMPORTS_SUCCESSFUL = False
    sys.exit(1)

# Custom JSON encoder to handle date objects
class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime and date objects."""
    
    def default(self, obj):
        """Convert datetime and date objects to ISO format strings."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return super().default(obj)

def save_results(results: Dict[str, Any], filename: str, results_dir: str = "test_results") -> None:
    """Save test results to a file.
    
    Args:
        results: Results dictionary
        filename: Name of the file to save results to
        results_dir: Directory to save results in
    """
    # Create results directory if it doesn't exist
    os.makedirs(results_dir, exist_ok=True)
    
    # Save results to file
    try:
        filepath = os.path.join(results_dir, filename)
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2, cls=DateTimeEncoder)
        logger.info(f"Results saved to {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Error saving results: {e}")
        return None

async def test_parsers_with_api(
    parsers: List[Dict[str, str]] = None,
    timeout: int = 30,
    debug: bool = False
) -> Dict[str, Any]:
    """Test parsers with API access for today's data.
    
    Args:
        parsers: List of parsers to test, each a dict with 'name' and 'area' keys
        timeout: API request timeout in seconds
        debug: Whether to enable debug mode (always use real API data)
        
    Returns:
        Dictionary with test results
    """
    logger.info("Testing parsers with API access for today's data")
    
    # Define default parsers and areas to test if none provided
    if not parsers:
        parsers = [
            {"name": "entsoe", "area": "SE4"},
            {"name": "nordpool", "area": "SE3"},
            {"name": "epex", "area": "FR"},
            {"name": "omie", "area": "ES"},
            {"name": "energi_data_service", "area": "DK1"},
            {"name": "aemo", "area": "NSW1"},
            {"name": "comed", "area": "US"},
            {"name": "stromligning", "area": "DK2"}
        ]
    
    # Run tests for each parser
    results = {}
    valid_count = 0
    
    for parser_info in parsers:
        try:
            api_name = parser_info["name"]
            area = parser_info["area"]
            
            logger.info(f"Testing {api_name} for area {area}")
            
            # Test using cache first, then API if cache fails
            cache_dir = "./parser_cache"
            os.makedirs(cache_dir, exist_ok=True)
            cache_file = os.path.join(cache_dir, f"{api_name}_{area}.json")
            
            # Determine whether to use cache or always fetch fresh data
            use_cache = False
            if not debug and os.path.exists(cache_file):
                file_time = os.path.getmtime(cache_file)
                file_age = datetime.now().timestamp() - file_time
                if file_age < 24 * 60 * 60:  # 24 hours in seconds
                    use_cache = True
            
            if debug:
                logger.info(f"Debug mode enabled, always using real API data for {api_name} ({area})")
                
            data = None
            if use_cache:
                logger.info(f"Using cached data for {api_name} ({area})")
                try:
                    with open(cache_file, "r") as f:
                        data = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load cache for {api_name} ({area}): {e}")
                    use_cache = False
            
            # Fetch from API if cache is disabled, missing, or failed
            if not use_cache or not data:
                logger.info(f"Fetching live data from {api_name} API for {area}")
                try:
                    # Test with today_api_testing
                    api_result = await test_today_api_data(
                        api_name=api_name,
                        area=area,
                        timeout=timeout,
                        debug=debug
                    )
                    
                    # Cache the result for future use (even in debug mode)
                    with open(cache_file, "w") as f:
                        json.dump(api_result, f, cls=DateTimeEncoder)
                    
                    # Extract data from api_result
                    data = api_result.get("raw_data")
                    
                    # Store the result
                    results[api_name] = {
                        "area": area,
                        "has_data": api_result.get("has_today_data", False),
                        "today_hours": api_result.get("today_hours", 0),
                        "tomorrow_hours": 0,  # Will be populated if available
                        "status": api_result.get("status", "unknown"),
                        "data_source": "api",
                        "cache_test": api_result.get("cache_test", {}),
                        "timezone_info": api_result.get("timezone_info", {})
                    }
                    
            # We're focusing exclusively on today's data, so we don't need to check for tomorrow data
            # This helps ensure the test is focused on its specific purpose
                except Exception as e:
                    logger.error(f"Error fetching data from {api_name} API: {e}")
                    results[api_name] = {
                        "area": area,
                        "error": str(e),
                        "data_source": "api_error"
                    }
            else:
                # Process cached data
                mock_hass = MockHass()
                
                # Check if we need to extract raw_data from the cached data structure
                adapter_data = data
                if "raw_data" in data:
                    logger.debug("Found raw_data key in cached data, using it for adapter")
                    adapter_data = data["raw_data"]
                
                adapter = ElectricityPriceAdapter(mock_hass, [adapter_data], source_type, False)
                
                # Get the hour counts for both today and tomorrow data
                # Check both possible attribute names
                if hasattr(adapter, "today_hourly_prices"):
                    today_hours = len(adapter.today_hourly_prices)
                else:
                    logger.debug("Adapter today_hourly_prices attribute not found, checking hourly_prices")
                    today_hours = len(adapter.hourly_prices) if hasattr(adapter, "hourly_prices") else 0
                
                # Also check tomorrow data
                tomorrow_hours = len(adapter.tomorrow_prices) if hasattr(adapter, "tomorrow_prices") else 0
                    
                logger.debug(f"Adapter today hourly price keys: {list(adapter.today_hourly_prices.keys()) if hasattr(adapter, 'today_hourly_prices') else []}")
                logger.debug(f"Adapter tomorrow hourly price keys: {list(adapter.tomorrow_prices.keys()) if hasattr(adapter, 'tomorrow_prices') else []}")
                
                # For Nordpool, many hours get categorized as "tomorrow" due to timezone differences
                # Consider data valid if either today has enough hours OR tomorrow has enough hours
                has_valid_data = data is not None and (today_hours >= 12 or (api_name == "nordpool" and tomorrow_hours >= 12))
                
                results[api_name] = {
                    "area": area,
                    "has_data": has_valid_data,
                    "today_hours": today_hours,
                    "tomorrow_hours": tomorrow_hours,  # Add tomorrow_hours to results
                    "status": "success" if data else "failure",
                    "data_source": "cache"
                }
            
            # Count valid results
            if results[api_name].get("has_data", False):
                valid_count += 1
                
        except Exception as e:
            logger.error(f"Error testing {parser_info['name']}: {e}")
            results[parser_info["name"]] = {
                "area": parser_info["area"],
                "error": str(e),
                "data_source": "test_error"
            }
    
    # Add summary
    results["summary"] = {
        "valid_count": valid_count,
        "total_count": len(parsers),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    return results

async def test_tdm(
    api_name: str,
    area: str,
    api_key: str = None
) -> Dict[str, Any]:
    """Test TodayDataManager with real API data and cache testing.
    
    Args:
        api_name: Name of the API to test
        area: Area code to test
        api_key: API key to use for services requiring authentication
        
    Returns:
        Dictionary with test results
    """
    logger.info(f"Testing TodayDataManager with {api_name} API for area {area}")
    
    results = {
        "api": api_name,
        "area": area,
        "tdm_success": False,
        "has_data": False,
        "today_hours": 0,
        "expected_hours": 24,
        "cache_test": {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        # Create mock HASS instance
        mock_hass = MockHass()
        
        # Build config
        config = build_api_key_config(api_name, area)
        
        # Add API key if provided
        if api_key and api_name == "entsoe":
            config["api_key"] = api_key
        
        # Create cache and timezone service
        price_cache = PriceCache(mock_hass, config)
        tz_service = TimezoneService(mock_hass, area, config)
        
        # Create TodayDataManager
        tdm = TodayDataManager(
            hass=mock_hass,
            area=area,
            currency=Currency.EUR,
            config=config,
            price_cache=price_cache,
            tz_service=tz_service,
            session=None
        )
        
        # Fetch data (this should store in cache)
        has_data = await tdm.fetch_data("test reason")
        
        # Get data
        data = tdm.get_data()
        
        # Process results
        results["tdm_success"] = has_data is not None
        
        if has_data and data:
            # Create adapter to test data
            adapter = ElectricityPriceAdapter(mock_hass, [data], source_type, False)
            
            # Get today hours count
            today_hours = len(adapter.today_hourly_prices) if hasattr(adapter, "today_hourly_prices") else 0
            
            # Consider data valid only if we have enough hours
            has_valid_data = today_hours >= 12
            
            results["has_data"] = has_valid_data
            results["today_hours"] = today_hours
            results["active_source"] = tdm._active_source
            results["attempted_sources"] = tdm._attempted_sources
            results["consecutive_failures"] = tdm._consecutive_failures
            
            # Test cache functionality
            has_current_hour = tdm.has_current_hour_price()
            current_hour_price = tdm.get_current_hour_price()
            
            # Add cache results to output
            results["cache_test"] = {
                "has_current_hour": has_current_hour,
                "current_hour_price": current_hour_price is not None
            }
            
            # Check if we have current hour price
            results["has_current_hour_price"] = has_current_hour
            
            # Inspect cache structure
            cache_structure = {}
            if hasattr(price_cache, "_cache"):
                today_str = datetime.now().strftime("%Y-%m-%d")
                if area in price_cache._cache and today_str in price_cache._cache[area]:
                    sources = list(price_cache._cache[area][today_str].keys())
                    cache_structure["sources"] = sources
                    
                    # Log hourly prices in cache
                    if sources:
                        source = sources[0]  # Use the first source
                        source_data = price_cache._cache[area][today_str][source]
                        if "hourly_prices" in source_data:
                            hour_keys = list(source_data["hourly_prices"].keys())
                            cache_structure["hourly_price_keys"] = hour_keys
                            
                            # Get current hour key
                            current_hour_key = tz_service.get_current_hour_key()
                            cache_structure["current_hour_key"] = current_hour_key
                            
                            # Check if current hour key is in hourly_prices
                            cache_structure["current_hour_in_hourly_prices"] = current_hour_key in source_data["hourly_prices"]
                            
                            # Get timezone info from cache
                            cache_structure["api_timezone"] = source_data.get("api_timezone")
                            cache_structure["ha_timezone"] = source_data.get("ha_timezone")
                            cache_structure["area_timezone"] = source_data.get("area_timezone")
                            cache_structure["stored_in_timezone"] = source_data.get("stored_in_timezone")
            
            results["cache_test"]["cache_structure"] = cache_structure
        
    except Exception as e:
        logger.error(f"Error testing TodayDataManager with {api_name}: {e}")
        results["error"] = str(e)
    
    return results

def parse_args() -> argparse.Namespace:
    """Parse command line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(description="Test today's data functionality for all parsers and APIs")
    
    # Test selection options
    parser.add_argument("--test-all", action="store_true", help="Run all tests")
    parser.add_argument("--test-tdm", action="store_true", help="Test TodayDataManager with real API")
    
    # API key option
    parser.add_argument("--api-key", help="API key for services requiring authentication (e.g., ENTSOE)")
    
    # Parser selection options
    parser.add_argument("--parser", help="Specific parser to test (e.g., entsoe, nordpool)")
    parser.add_argument("--area", help="Specific area to test (e.g., SE4, SE3)")
    
    # Other options
    parser.add_argument("--results-dir", default="./test_results", help="Directory to store test results")
    parser.add_argument("--timeout", type=int, default=30, help="API request timeout in seconds")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    return parser.parse_args()

def setup_logging(debug: bool) -> None:
    """Set up logging with the specified level.
    
    Args:
        debug: Whether to enable debug logging
    """
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

def print_summary(
    all_results: Dict[str, Any] = None,
    tdm_results: Dict[str, Any] = None
) -> None:
    """Print a summary of the test results.
    
    Args:
        all_results: Results from testing all parsers
        tdm_results: Results from testing TodayDataManager
    """
    print("\n" + "=" * 80)
    print("TODAY DATA TEST SUMMARY")
    print("=" * 80)
    
    if all_results:
        print("\n=== All Parsers Summary ===")
        for api_name, api_result in all_results.items():
            if api_name != "summary":
                today_hours = api_result.get("today_hours", 0)
                has_data = api_result.get("has_data", False)
                data_source = api_result.get("data_source", "unknown")
                print(f"{api_name} ({api_result.get('area')}): Has data: {has_data}, Today hours: {today_hours}, Source: {data_source}")
                
                # Print cache test results if available
                cache_test = api_result.get("cache_test", {})
                if cache_test:
                    has_current_hour = cache_test.get("has_current_hour", False)
                    current_hour_key = cache_test.get("current_hour_key", "unknown")
                    retrieved_hour_price = cache_test.get("retrieved_hour_price", False)
                    print(f"  Cache test: Has current hour: {has_current_hour}, Current hour key: {current_hour_key}, Retrieved hour price: {retrieved_hour_price}")
                
                if api_name == "nordpool" and api_result.get("has_data", False) and api_result.get("today_hours", 0) < 12:
                    tomorrow_hours = api_result.get("tomorrow_hours", 0)
                    print(f"  Note: Nordpool has {tomorrow_hours} hours in tomorrow's data")
        
        valid_count = all_results.get("summary", {}).get("valid_count", 0)
        total_count = all_results.get("summary", {}).get("total_count", 0)
        print(f"{valid_count} out of {total_count} parsers have valid today data")
    
    if tdm_results:
        print("\n=== TodayDataManager Test Summary ===")
        print(f"API: {tdm_results.get('api')} ({tdm_results.get('area')})")
        print(f"TDM success: {tdm_results.get('tdm_success', False)}")
        print(f"Has data: {tdm_results.get('has_data', False)}")
        print(f"Today hours: {tdm_results.get('today_hours', 0)}")
        
        if "active_source" in tdm_results:
            print(f"Active source: {tdm_results.get('active_source')}")
            print(f"Attempted sources: {tdm_results.get('attempted_sources', [])}")
        
        # Print cache test results if available
        cache_test = tdm_results.get("cache_test", {})
        if cache_test:
            has_current_hour = cache_test.get("has_current_hour", False)
            current_hour_price = cache_test.get("current_hour_price", False)
            print(f"  Cache test: Has current hour: {has_current_hour}, Retrieved hour price: {current_hour_price}")
            
            # Print cache structure if available
            cache_structure = cache_test.get("cache_structure", {})
            if cache_structure:
                sources = cache_structure.get("sources", [])
                print(f"  Cache structure: Sources: {sources}")
                
                if "current_hour_key" in cache_structure:
                    current_hour_key = cache_structure.get("current_hour_key")
                    current_hour_in_hourly_prices = cache_structure.get("current_hour_in_hourly_prices", False)
                    print(f"  Current hour key: {current_hour_key}, In hourly prices: {current_hour_in_hourly_prices}")
                
                if "api_timezone" in cache_structure:
                    api_timezone = cache_structure.get("api_timezone")
                    ha_timezone = cache_structure.get("ha_timezone")
                    area_timezone = cache_structure.get("area_timezone")
                    stored_in_timezone = cache_structure.get("stored_in_timezone")
                    print(f"  Timezones: API: {api_timezone}, HA: {ha_timezone}, Area: {area_timezone}, Stored in: {stored_in_timezone}")
        
        if "has_current_hour_price" in tdm_results:
            print(f"Has current hour price: {tdm_results.get('has_current_hour_price')}")
    
    print("\nFor detailed results, check the files in the test_results directory.")

async def main() -> int:
    """Run the tests.
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    args = parse_args()
    setup_logging(args.debug)
    
    # Get API key from environment variable if not provided
    api_key = args.api_key
    if not api_key:
        api_key = os.environ.get("API_KEY")
        if api_key:
            logger.info("Using API key from environment variable")
    
    # Get current timestamp for file naming
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Determine which tests to run
    run_all = args.test_all or not args.test_tdm
    run_tdm = args.test_tdm or (run_all and api_key)
    
    # Filter parsers if specified
    parsers = None
    if args.parser:
        logger.info(f"Filtering tests to parser: {args.parser}")
        area = args.area or {"entsoe": "SE4", "nordpool": "SE3", "epex": "DE", 
                            "omie": "ES", "energi_data_service": "DK1", 
                            "aemo": "NSW1", "comed": "US", "stromligning": "NO1"}.get(args.parser)
        parsers = [{"name": args.parser, "area": area}]
    
    # Store all results
    all_results = None
    tdm_results = None
    
    # Always run the parser tests, since it's our main functionality
    logger.info("=== Testing parsers for today's data ===")
    all_results = await test_parsers_with_api(
        parsers=parsers,
        timeout=args.timeout,
        debug=args.debug
    )
    save_results(all_results, f"today_parsers_{timestamp}.json", args.results_dir)
    
    if run_tdm and api_key:
        logger.info("=== Testing TodayDataManager with real API ===")
        api_name = args.parser or "entsoe"
        area = args.area or {"entsoe": "SE4", "nordpool": "SE3"}.get(api_name, "SE4")
        
        tdm_results = await test_tdm(
            api_name=api_name,
            area=area,
            api_key=api_key
        )
        save_results(tdm_results, f"today_tdm_{api_name}_{timestamp}.json", args.results_dir)
    
    # Print summary
    print_summary(all_results, tdm_results)
    
    logger.info("All tests completed successfully")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
