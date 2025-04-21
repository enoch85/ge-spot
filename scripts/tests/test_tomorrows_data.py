#!/usr/bin/env python3
"""Comprehensive test script for tomorrow's data functionality.

This script provides a unified testing approach for all parsers and APIs,
testing their ability to extract and validate tomorrow's price data.
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
    from custom_components.ge_spot.coordinator.tomorrow_data_manager import TomorrowDataManager
    from custom_components.ge_spot.price.cache import PriceCache
    from custom_components.ge_spot.timezone import TimezoneService
    from scripts.tests.api.tomorrow_api_testing import test_tomorrow_api_data
    # Note: ImprovedElectricityPriceAdapter has been merged into the standard ElectricityPriceAdapter
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
    """Test parsers with API access for tomorrow's data.
    
    Args:
        parsers: List of parsers to test, each a dict with 'name' and 'area' keys
        timeout: API request timeout in seconds
        debug: Whether to enable debug mode (always use real API data)
        
    Returns:
        Dictionary with test results
    """
    logger.info("Testing parsers with API access for tomorrow's data")
    
    # Define default parsers and areas to test if none provided
    if not parsers:
        parsers = [
            {"name": "entsoe", "area": "SE4"},
            {"name": "nordpool", "area": "SE4"},
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
            
            # Try cache first
            use_cache = False
            if os.path.exists(cache_file):
                file_time = os.path.getmtime(cache_file)
                file_age = datetime.now().timestamp() - file_time
                if file_age < 24 * 60 * 60:  # 24 hours in seconds
                    use_cache = True
                    
            data = None
            if use_cache:
                logger.info(f"Using cached data for {api_name} ({area})")
                try:
                    with open(cache_file, "r") as f:
                        data = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load cache for {api_name} ({area}): {e}")
                    use_cache = False
            
            # Fall back to API if cache missing or failed
            if not use_cache or not data:
                logger.info(f"Fetching live data from {api_name} API for {area}")
                try:
                    # Test with API data
                    api_result = await test_tomorrow_api_data(
                        api_name=api_name,
                        area=area,
                        timeout=timeout,
                        debug=debug
                    )
                    
                    # Cache the result for future use
                    with open(cache_file, "w") as f:
                        json.dump(api_result, f, cls=DateTimeEncoder)
                    
                    # Store the result
                    results[api_name] = {
                        "area": area,
                        "has_tomorrow_data": api_result.get("has_tomorrow_data", False),
                        "tomorrow_valid": api_result.get("tomorrow_valid", False),
                        "tomorrow_hours": api_result.get("tomorrow_hours", 0),
                        "status": api_result.get("status", "unknown"),
                        "data_source": "api",
                        "cache_test": api_result.get("cache_test", {}),
                        "timezone_info": api_result.get("timezone_info", {})
                    }
                except Exception as e:
                    logger.error(f"Error fetching data from {api_name} API: {e}")
                    results[api_name] = {
                        "area": area,
                        "error": str(e),
                        "data_source": "api_error"
                    }
            else:
                # Process cached data
                results[api_name] = {
                    "area": area,
                    "has_tomorrow_data": data.get("has_tomorrow_data", False),
                    "tomorrow_valid": data.get("tomorrow_valid", False),
                    "tomorrow_hours": data.get("tomorrow_hours", 0),
                    "status": data.get("status", "unknown"),
                    "data_source": "cache"
                }
            
            # Count valid results
            if results[api_name].get("tomorrow_valid", False):
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

async def test_api_direct(api_name: str, area: str) -> Dict[str, Any]:
    """Test any API directly for tomorrow's data, similar to test_nordpool_direct_api.
    
    Args:
        api_name: Name of the API to test
        area: Area code to test
        
    Returns:
        Dictionary with test results
    """
    logger.info(f"Testing {api_name} API directly for tomorrow's data (area: {area})")
    
    results = {
        "area": area,
        "api": api_name,
        "direct_api_success": False,
        "adapter_success": False,
        "tomorrow_hours": 0,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        # Set up test
        mock_hass = MockHass()
        config = build_api_key_config(api_name, area)
        
        # Fetch data from the API
        data = await fetch_day_ahead_prices(
            source_type=api_name,
            config=config,
            area=area,
            currency=Currency.EUR,
            hass=mock_hass
        )
        
        if not data:
            logger.error(f"No data returned from {api_name} API")
            return results
        
        # Log the raw data structure
        logger.info(f"Raw data keys: {data.keys()}")
        
            # We're only focusing on tomorrow's data in this test
        
        # Check if we have tomorrow_hourly_prices
        if "tomorrow_hourly_prices" in data:
            tomorrow_hourly_prices = data["tomorrow_hourly_prices"]
            results["tomorrow_hours"] = len(tomorrow_hourly_prices)
            logger.info(f"Tomorrow hourly prices: {len(tomorrow_hourly_prices)} entries")
            
            # Log sample entries
            sample_entries = list(tomorrow_hourly_prices.items())[:5]
            logger.info(f"Sample tomorrow hourly prices: {sample_entries}")
            
            # Direct API has tomorrow data
            results["direct_api_success"] = True
        else:
            logger.warning(f"No tomorrow_hourly_prices found in {api_name} data")
        
        # Test with standard adapter
        adapter = ElectricityPriceAdapter(mock_hass, [data], False)
        
        # Log details about adapter data
        logger.info(f"Adapter hourly price keys: {list(adapter.today_hourly_prices.keys())[:5]}")
        
        # Check if adapter has tomorrow prices
        tomorrow_prices = adapter.tomorrow_prices
        if tomorrow_prices:
            logger.info(f"Adapter tomorrow price keys: {list(tomorrow_prices.keys())[:5]}")
            logger.info(f"Adapter tomorrow hours: {len(tomorrow_prices)}")
        else:
            logger.info("Adapter tomorrow price keys: None")
        
        # Check if tomorrow's data is correctly identified by the adapter
        is_tomorrow_valid = adapter.is_tomorrow_valid()
        logger.info(f"Tomorrow data validation: {is_tomorrow_valid}")
        
        # Store the result
        results["adapter_success"] = is_tomorrow_valid
        results["adapter_tomorrow_hours"] = len(tomorrow_prices) if tomorrow_prices else 0
        
        # Note: The improved adapter has been merged into the standard adapter
        
        # Make direct API calls for all APIs to get tomorrow's data
        await test_direct_api_call(api_name, area, results)
            
    except Exception as e:
        logger.error(f"Error during {api_name} direct test: {e}")
        results["error"] = str(e)
    
    return results

async def test_nordpool_direct_api() -> Dict[str, Any]:
    """Test Nordpool API directly for tomorrow's data.
    
    Returns:
        Dictionary with test results
    """
    return await test_api_direct("nordpool", "SE3")

async def test_direct_api_call(api_name: str, area: str, results: Dict[str, Any]) -> None:
    """Test any API directly using low-level calls to get tomorrow's data.
    
    Args:
        api_name: Name of the API to test
        area: Area code to test
        results: Dictionary to update with test results
    """
    try:
        # Create a new session for direct API access
        async with aiohttp.ClientSession() as session:
            # Get tomorrow's date
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            
            if api_name == "nordpool":
                # Base URL for Nordpool API
                base_url = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
                
                # Fetch tomorrow's data
                tomorrow_url = f"{base_url}?currency=EUR&date={tomorrow}&market=DayAhead&deliveryArea={area}"
                logger.info(f"Fetching tomorrow's data from: {tomorrow_url}")
                
                async with session.get(tomorrow_url) as response:
                    if response.status == 200:
                        tomorrow_data = await response.json()
                        tomorrow_entries = len(tomorrow_data.get('multiAreaEntries', []))
                        logger.info(f"Successfully fetched tomorrow's data: {tomorrow_entries} entries")
                        results["direct_api_tomorrow_entries"] = tomorrow_entries
                        results["direct_api_tomorrow_success"] = True
                    else:
                        logger.error(f"Failed to fetch tomorrow's data: {response.status}")
                        results["direct_api_tomorrow_error"] = f"HTTP {response.status}"
            
            elif api_name == "entsoe":
                # For ENTSOE, we need an API key which we don't have in this function
                # Just log that we can't make a direct API call without an API key
                logger.info("ENTSOE API requires an API key for direct calls")
                results["direct_api_tomorrow_entries"] = 0
                results["direct_api_tomorrow_success"] = False
            
            elif api_name == "epex":
                # EPEX doesn't have a public API for direct calls
                logger.info("EPEX doesn't have a public API for direct calls")
                results["direct_api_tomorrow_entries"] = 0
                results["direct_api_tomorrow_success"] = False
            
            elif api_name == "omie":
                # Get tomorrow's date in the format required by OMIE
                tomorrow_omie = (datetime.now() + timedelta(days=1)).strftime("%d_%m_%Y")
                
                # Construct the URL for OMIE
                tomorrow_url = f"https://www.omie.es/en/file-download?parents%5B0%5D=&filename=marginalpdbc_{tomorrow_omie}.1"
                logger.info(f"Fetching tomorrow's data from: {tomorrow_url}")
                
                async with session.get(tomorrow_url) as response:
                    if response.status == 200:
                        # OMIE returns a CSV file, not JSON
                        tomorrow_data = await response.text()
                        # Count the number of lines as a rough estimate of entries
                        tomorrow_entries = len(tomorrow_data.splitlines())
                        logger.info(f"Successfully fetched tomorrow's data: {tomorrow_entries} lines")
                        results["direct_api_tomorrow_entries"] = tomorrow_entries
                        results["direct_api_tomorrow_success"] = True
                    else:
                        logger.error(f"Failed to fetch tomorrow's data: {response.status}")
                        results["direct_api_tomorrow_error"] = f"HTTP {response.status}"
            
            elif api_name == "energi_data_service":
                # Get tomorrow's and day after tomorrow's dates
                tomorrow_eds = tomorrow
                day_after_tomorrow = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
                
                # Construct the URL for Energi Data Service
                tomorrow_url = f"https://api.energidataservice.dk/dataset/Elspotprices?start={tomorrow_eds}&end={day_after_tomorrow}&filter=%7B%22PriceArea%22:%22{area}%22%7D"
                logger.info(f"Fetching tomorrow's data from: {tomorrow_url}")
                
                async with session.get(tomorrow_url) as response:
                    if response.status == 200:
                        tomorrow_data = await response.json()
                        tomorrow_entries = len(tomorrow_data.get('records', []))
                        logger.info(f"Successfully fetched tomorrow's data: {tomorrow_entries} entries")
                        results["direct_api_tomorrow_entries"] = tomorrow_entries
                        results["direct_api_tomorrow_success"] = True
                    else:
                        logger.error(f"Failed to fetch tomorrow's data: {response.status}")
                        results["direct_api_tomorrow_error"] = f"HTTP {response.status}"
            
            else:
                # For other APIs, we don't have direct API call implementations yet
                logger.info(f"Direct API call not implemented for {api_name}")
                results["direct_api_tomorrow_entries"] = 0
                results["direct_api_tomorrow_success"] = False
    
    except Exception as e:
        logger.error(f"Error in direct API test for {api_name}: {e}")
        results["direct_api_error"] = str(e)
        results["direct_api_tomorrow_entries"] = 0
        results["direct_api_tomorrow_success"] = False

async def test_direct_nordpool_api(results: Dict[str, Any]) -> None:
    """Test Nordpool API directly using low-level aiohttp calls.
    
    Args:
        results: Dictionary to update with test results
    """
    # This function is kept for backward compatibility
    # Now we use the more general test_direct_api_call function
    await test_direct_api_call("nordpool", results["area"], results)

async def test_tdm_with_real_api(
    api_name: str, 
    area: str, 
    api_key: str = None
) -> Dict[str, Any]:
    """Test the TomorrowDataManager with a real API and cache testing.
    
    Args:
        api_name: Name of the API to test
        area: Area code to test
        api_key: API key to use
        
    Returns:
        Dictionary with test results
    """
    logger.info(f"Testing TomorrowDataManager with {api_name} API for area {area}")
    
    results = {
        "api": api_name,
        "area": area,
        "tdm_success": False,
        "has_tomorrow_data": False,
        "tomorrow_hours": 0,
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
        
        # Create TomorrowDataManager
        tdm = TomorrowDataManager(
            hass=mock_hass,
            api_client=None,
            source=getattr(Source, api_name.upper(), None),
            area=area,
            currency=Currency.EUR,
            should_search_tomorrow=True,
            has_data_now=False,
            config=config,
            price_cache=price_cache,
            tz_service=tz_service
        )
        
        # Fetch tomorrow data
        has_data = await tdm.fetch_data()
        
        # Get data from TDM
        data = tdm.get_data()
        
        # Process results
        results["tdm_success"] = has_data
        
        if has_data and data:
            # Try with standard adapter first
            adapter = ElectricityPriceAdapter(mock_hass, [data], False)
            is_tomorrow_valid = adapter.is_tomorrow_valid()
            tomorrow_prices = adapter.tomorrow_prices
            
            results["tomorrow_valid"] = is_tomorrow_valid
            results["tomorrow_hours"] = len(tomorrow_prices) if tomorrow_prices else 0
            results["has_tomorrow_data"] = is_tomorrow_valid and results["tomorrow_hours"] > 0
            
            # Note: The improved adapter has been merged into the standard adapter
            results["has_tomorrow_data"] = is_tomorrow_valid and results["tomorrow_hours"] > 0
            
            # Inspect cache structure
            cache_structure = {}
            if hasattr(price_cache, "_cache"):
                today_str = datetime.now().strftime("%Y-%m-%d")
                tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                
                # Check for today's cache entry
                if area in price_cache._cache and today_str in price_cache._cache[area]:
                    cache_structure["today_in_cache"] = True
                    
                    # Check for sources in today's cache
                    sources = list(price_cache._cache[area][today_str].keys())
                    cache_structure["sources_in_today"] = sources
                    
                    # Check for tomorrow data in today's cache
                    for source in sources:
                        source_data = price_cache._cache[area][today_str][source]
                        if "tomorrow_hourly_prices" in source_data:
                            cache_structure["tomorrow_in_today_cache"] = True
                            cache_structure["tomorrow_hour_keys"] = list(source_data["tomorrow_hourly_prices"].keys())
                            break
                
                # Check for tomorrow's cache entry
                if area in price_cache._cache and tomorrow_str in price_cache._cache[area]:
                    cache_structure["tomorrow_cache_entry"] = True
                    
                    # Check for sources in tomorrow's cache
                    sources = list(price_cache._cache[area][tomorrow_str].keys())
                    cache_structure["sources_in_tomorrow"] = sources
                    
                    # Check for hourly prices in tomorrow's cache
                    for source in sources:
                        source_data = price_cache._cache[area][tomorrow_str][source]
                        if "hourly_prices" in source_data:
                            cache_structure["hourly_prices_in_tomorrow"] = True
                            cache_structure["hourly_price_keys_in_tomorrow"] = list(source_data["hourly_prices"].keys())
                            break
            
            # Add cache results to output
            results["cache_test"] = {
                "cache_structure": cache_structure,
                "tomorrow_valid_from_cache": is_tomorrow_valid
            }
            
            # Add timezone information
            results["timezone_info"] = {
                "area_timezone": str(tz_service.area_timezone) if tz_service.area_timezone else None,
                "ha_timezone": str(mock_hass.config.time_zone) if hasattr(mock_hass, "config") and hasattr(mock_hass.config, "time_zone") else None,
                "is_dst_transition": tz_service.is_dst_transition_day(datetime.now())
            }
        
    except Exception as e:
        logger.error(f"Error testing TomorrowDataManager with {api_name}: {e}")
        results["error"] = str(e)
    
    return results

def parse_args() -> argparse.Namespace:
    """Parse command line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(description="Test tomorrow's data functionality for all parsers and APIs")
    
    # Test selection options
    parser.add_argument("--test-all", action="store_true", help="Run all tests")
    parser.add_argument("--test-direct-api", action="store_true", help="Test APIs directly")
    parser.add_argument("--test-tdm", action="store_true", help="Test TomorrowDataManager with real API")
    
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
    direct_api_results: Dict[str, Dict[str, Any]] = None,
    tdm_results: Dict[str, Any] = None
) -> None:
    """Print a summary of the test results.
    
    Args:
        all_results: Results from testing all parsers
        direct_api_results: Results from testing APIs directly
        tdm_results: Results from testing TomorrowDataManager
    """
    print("\n" + "=" * 80)
    print("TOMORROW DATA TEST SUMMARY")
    print("=" * 80)
    
    if all_results:
        print("\n=== All Parsers Summary ===")
        for api_name, api_result in all_results.items():
            if api_name != "summary":
                tomorrow_valid = api_result.get("tomorrow_valid", False)
                tomorrow_hours = api_result.get("tomorrow_hours", 0)
                data_source = api_result.get("data_source", "unknown")
                print(f"{api_name} ({api_result.get('area')}): Tomorrow valid: {tomorrow_valid}, Tomorrow hours: {tomorrow_hours}, Source: {data_source}")
                
                # Print cache test results if available
                cache_test = api_result.get("cache_test", {})
                if cache_test:
                    cache_structure = cache_test.get("cache_structure", {})
                    tomorrow_in_today_cache = cache_structure.get("tomorrow_in_today_cache", False)
                    tomorrow_cache_entry = cache_structure.get("tomorrow_cache_entry", False)
                    print(f"  Cache test: Tomorrow in today's cache: {tomorrow_in_today_cache}, Tomorrow cache entry: {tomorrow_cache_entry}")
        
        valid_count = all_results.get("summary", {}).get("valid_count", 0)
        total_count = all_results.get("summary", {}).get("total_count", 0)
        print(f"{valid_count} out of {total_count} parsers have valid tomorrow data")
    
    if direct_api_results:
        for api_name, results in direct_api_results.items():
            print(f"\n=== {api_name.capitalize()} Direct API Summary ===")
            print(f"Area: {results.get('area', 'unknown')}")
            print(f"Direct API success: {results.get('direct_api_success', False)}")
            print(f"Adapter success: {results.get('adapter_success', False)} ({results.get('adapter_tomorrow_hours', 0)} hours)")
            print(f"Tomorrow hours: {results.get('tomorrow_hours', 0)}")
            
            # Print cache test results if available
            cache_test = results.get("cache_test", {})
            if cache_test:
                cache_structure = cache_test.get("cache_structure", {})
                tomorrow_in_today_cache = cache_structure.get("tomorrow_in_today_cache", False)
                tomorrow_cache_entry = cache_structure.get("tomorrow_cache_entry", False)
                print(f"  Cache test: Tomorrow in today's cache: {tomorrow_in_today_cache}, Tomorrow cache entry: {tomorrow_cache_entry}")
            
            # Always show direct API entries (0 if not available)
            print(f"Direct tomorrow API entries: {results.get('direct_api_tomorrow_entries', 0)}")
    
    if tdm_results:
        print("\n=== TomorrowDataManager Test Summary ===")
        print(f"API: {tdm_results.get('api')} ({tdm_results.get('area')})")
        print(f"TDM success: {tdm_results.get('tdm_success', False)}")
        print(f"Tomorrow valid: {tdm_results.get('tomorrow_valid', False)}")
        print(f"Tomorrow hours: {tdm_results.get('tomorrow_hours', 0)}")
        
        # The improved adapter has been merged into the standard adapter
        
        # Print cache test results if available
        cache_test = tdm_results.get("cache_test", {})
        if cache_test:
            cache_structure = cache_test.get("cache_structure", {})
            if cache_structure:
                tomorrow_in_today_cache = cache_structure.get("tomorrow_in_today_cache", False)
                tomorrow_cache_entry = cache_structure.get("tomorrow_cache_entry", False)
                print(f"  Cache test: Tomorrow in today's cache: {tomorrow_in_today_cache}, Tomorrow cache entry: {tomorrow_cache_entry}")
                
                if "sources_in_today" in cache_structure:
                    sources_in_today = cache_structure.get("sources_in_today", [])
                    print(f"  Sources in today's cache: {sources_in_today}")
                
                if "sources_in_tomorrow" in cache_structure:
                    sources_in_tomorrow = cache_structure.get("sources_in_tomorrow", [])
                    print(f"  Sources in tomorrow's cache: {sources_in_tomorrow}")
                
                if "tomorrow_hour_keys" in cache_structure:
                    tomorrow_hour_keys = cache_structure.get("tomorrow_hour_keys", [])
                    print(f"  Tomorrow hour keys in today's cache: {tomorrow_hour_keys[:5]}...")
                
                if "hourly_price_keys_in_tomorrow" in cache_structure:
                    hourly_price_keys = cache_structure.get("hourly_price_keys_in_tomorrow", [])
                    print(f"  Hourly price keys in tomorrow's cache: {hourly_price_keys[:5]}...")
    
    print("\nFor detailed results, check the files in the test_results directory.")

async def main() -> int:
    """Run the consolidated test.
    
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
    run_all = args.test_all or not (args.test_direct_api or args.test_tdm)
    run_direct_api = run_all or args.test_direct_api
    run_tdm = run_all and api_key or args.test_tdm
    
    # Define which APIs to test
    api_list = ["entsoe", "nordpool", "epex", "omie", "energi_data_service"]
    
    # Filter API list if parser is specified
    if args.parser:
        if args.parser in api_list:
            api_list = [args.parser]
        else:
            logger.warning(f"Unknown parser: {args.parser}, will test all APIs")
    
    # Store all results
    all_results = None
    direct_api_results = {}
    tdm_results = None
    
    # Always run the parser tests, since it's our main functionality
    logger.info("=== Testing parsers for tomorrow's data ===")
    
    # Filter parsers if specified
    parsers = None
    if args.parser:
        logger.info(f"Filtering tests to parser: {args.parser}")
        area = args.area or {"entsoe": "SE4", "nordpool": "SE3", "epex": "DE", 
                            "omie": "ES", "energi_data_service": "DK1", 
                            "aemo": "NSW1", "comed": "US", "stromligning": "NO1"}.get(args.parser)
        parsers = [{"name": args.parser, "area": area}]
    
    all_results = await test_parsers_with_api(
        parsers=parsers,
        timeout=args.timeout,
        debug=args.debug
    )
    save_results(all_results, f"tomorrow_parsers_{timestamp}.json", args.results_dir)
    
    if run_direct_api:
        logger.info("=== Testing APIs directly ===")
        
        for api_name in api_list:
            if args.area:
                area = args.area
            else:
                area = {"entsoe": "SE4", "nordpool": "SE3", "epex": "DE", 
                      "omie": "ES", "energi_data_service": "DK1"}.get(api_name, "SE4")
            
            logger.info(f"Testing {api_name} API directly for area {area}")
            
            # Test this API directly
            api_results = await test_api_direct(api_name, area)
            direct_api_results[api_name] = api_results
            
            # Save results for this API
            save_results(api_results, f"tomorrow_{api_name}_{timestamp}.json", args.results_dir)
    
    if run_tdm and api_key:
        logger.info("=== Testing TomorrowDataManager with real API ===")
        api_name = args.parser or "entsoe"
        area = args.area or {"entsoe": "SE4", "nordpool": "SE3"}.get(api_name, "SE4")
        
        tdm_results = await test_tdm_with_real_api(
            api_name=api_name,
            area=area,
            api_key=api_key
        )
        save_results(tdm_results, f"tomorrow_tdm_{api_name}_{timestamp}.json", args.results_dir)
    
    # Print summary
    print_summary(all_results, direct_api_results, tdm_results)
    
    logger.info("All tests completed successfully")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
