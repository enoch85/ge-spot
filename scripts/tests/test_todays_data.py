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
    timeout: int = 30
) -> Dict[str, Any]:
    """Test parsers with API access for today's data.
    
    Args:
        parsers: List of parsers to test, each a dict with 'name' and 'area' keys
        timeout: API request timeout in seconds
        
    Returns:
        Dictionary with test results
    """
    logger.info("Testing parsers with API access for today's data")
    
    # Define default parsers and areas to test if none provided
    if not parsers:
        parsers = [
            {"name": "entsoe", "area": "SE4"},
            {"name": "nordpool", "area": "SE3"},
            {"name": "epex", "area": "DE"},
            {"name": "omie", "area": "ES"},
            {"name": "energi_data_service", "area": "DK1"},
            {"name": "aemo", "area": "NSW1"},
            {"name": "comed", "area": "US"},
            {"name": "stromligning", "area": "NO1"}
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
                    # Create mock HASS instance
                    mock_hass = MockHass()
                    
                    # Build config
                    config = build_api_key_config(api_name, area)
                    config["request_timeout"] = timeout
                    
                    # Fetch data
                    session = aiohttp.ClientSession()
                    try:
                        data = await fetch_day_ahead_prices(
                            source_type=api_name,
                            config=config,
                            area=area,
                            currency=Currency.EUR,
                            hass=mock_hass,
                            session=session
                        )
                        
                        # Cache the result for future use
                        with open(cache_file, "w") as f:
                            json.dump(data, f, cls=DateTimeEncoder)
                    finally:
                        if session and not session.closed:
                            await session.close()
                    
                    # Create adapter to test data
                    adapter = ElectricityPriceAdapter(mock_hass, [data], False)
                    
                    # Get the actual hour count for today's data
                    today_hours = len(adapter.today_hourly_prices) if hasattr(adapter, "today_hourly_prices") else 0
                    
                    # Consider data valid only if we have at least 12 hours
                    has_valid_data = data is not None and today_hours >= 12
                    
                    # Store the result
                    results[api_name] = {
                        "area": area,
                        "has_data": has_valid_data,
                        "today_hours": today_hours,
                        "status": "success" if data else "failure",
                        "data_source": "api"
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
                mock_hass = MockHass()
                adapter = ElectricityPriceAdapter(mock_hass, [data], False)
                
                # Get the actual hour count for today's data
                today_hours = len(adapter.today_hourly_prices) if hasattr(adapter, "today_hourly_prices") else 0
                
                # Consider data valid only if we have at least 12 hours
                has_valid_data = data is not None and today_hours >= 12
                
                results[api_name] = {
                    "area": area,
                    "has_data": has_valid_data,
                    "today_hours": today_hours,
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
    """Test TodayDataManager with real API data.
    
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
        
        # Create TodayDataManager
        tdm = TodayDataManager(
            hass=mock_hass,
            area=area,
            currency=Currency.EUR,
            config=config,
            price_cache=None,
            tz_service=None,
            session=None
        )
        
        # Fetch data
        has_data = await tdm.fetch_data("test reason")
        
        # Get data
        data = tdm.get_data()
        
        # Process results
        results["tdm_success"] = has_data is not None
        
        if has_data and data:
            # Create adapter to test data
            adapter = ElectricityPriceAdapter(mock_hass, [data], False)
            
            # Get today hours count
            today_hours = len(adapter.today_hourly_prices) if hasattr(adapter, "today_hourly_prices") else 0
            
            # Consider data valid only if we have enough hours
            has_valid_data = today_hours >= 12
            
            results["has_data"] = has_valid_data
            results["today_hours"] = today_hours
            results["active_source"] = tdm._active_source
            results["attempted_sources"] = tdm._attempted_sources
            results["consecutive_failures"] = tdm._consecutive_failures
            
            # Check if we have current hour price
            results["has_current_hour_price"] = tdm.has_current_hour_price()
        
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
        timeout=args.timeout
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
