#!/usr/bin/env python3
"""Comprehensive test script for ElectricityPriceAdapter functionality.

This script provides a unified testing approach for testing both the standard and improved
ElectricityPriceAdapter implementations with various data sources. It tests the adapters'
ability to correctly extract and format price data from different API responses.
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
    from scripts.tests.core.adapter_testing import ImprovedElectricityPriceAdapter
    from scripts.tests.core.adapter_testing import create_test_data_with_dates, create_test_data_without_dates, create_test_data_mixed
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

def load_entsoe_response(file_path: str) -> str:
    """Load ENTSO-E XML response from file.
    
    Args:
        file_path: Path to the XML file
        
    Returns:
        XML response as string
    """
    try:
        with open(file_path, "r") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to load ENTSO-E response: {e}")
        return None

def test_with_synthetic_data():
    """Test adapters with synthetically generated data containing dates.
    
    Returns:
        Dictionary with test results
    """
    logger.info("=== Testing adapters with synthetic data ===")
    
    # Create mock HASS instance
    hass = MockHass()
    
    results = {}
    
    # Testing with today's data only (without dates)
    logger.info("Testing with data without dates")
    data_without_dates = create_test_data_without_dates()
    
    # Standard adapter
    standard_adapter = ElectricityPriceAdapter(hass, [data_without_dates], False)
    
    results["standard_without_dates"] = {
        "today_hours": len(standard_adapter.hourly_prices),
        "tomorrow_hours": len(standard_adapter.tomorrow_prices) if standard_adapter.tomorrow_prices else 0,
        "tomorrow_valid": standard_adapter.is_tomorrow_valid(),
        "sample_hours": list(standard_adapter.hourly_prices.keys())[:5]
    }
    
    logger.info(f"Standard adapter with data without dates: "
               f"Today hours: {results['standard_without_dates']['today_hours']}, "
               f"Tomorrow hours: {results['standard_without_dates']['tomorrow_hours']}, "
               f"Tomorrow valid: {results['standard_without_dates']['tomorrow_valid']}")
    
    # Improved adapter
    improved_adapter = ImprovedElectricityPriceAdapter(hass, [data_without_dates], False)
    
    results["improved_without_dates"] = {
        "today_hours": len(improved_adapter.hourly_prices),
        "tomorrow_hours": len(improved_adapter.tomorrow_prices) if improved_adapter.tomorrow_prices else 0,
        "tomorrow_valid": improved_adapter.is_tomorrow_valid(),
        "sample_hours": list(improved_adapter.hourly_prices.keys())[:5]
    }
    
    logger.info(f"Improved adapter with data without dates: "
               f"Today hours: {results['improved_without_dates']['today_hours']}, "
               f"Tomorrow hours: {results['improved_without_dates']['tomorrow_hours']}, "
               f"Tomorrow valid: {results['improved_without_dates']['tomorrow_valid']}")
    
    # Testing with data containing date info
    logger.info("Testing with data containing ISO format dates")
    data_with_dates = create_test_data_with_dates()
    
    # Standard adapter
    standard_adapter = ElectricityPriceAdapter(hass, [data_with_dates], False)
    
    results["standard_with_dates"] = {
        "today_hours": len(standard_adapter.hourly_prices),
        "tomorrow_hours": len(standard_adapter.tomorrow_prices) if standard_adapter.tomorrow_prices else 0,
        "tomorrow_valid": standard_adapter.is_tomorrow_valid(),
        "sample_hours": list(standard_adapter.hourly_prices.keys())[:5]
    }
    
    logger.info(f"Standard adapter with data with dates: "
               f"Today hours: {results['standard_with_dates']['today_hours']}, "
               f"Tomorrow hours: {results['standard_with_dates']['tomorrow_hours']}, "
               f"Tomorrow valid: {results['standard_with_dates']['tomorrow_valid']}")
    
    # Improved adapter
    improved_adapter = ImprovedElectricityPriceAdapter(hass, [data_with_dates], False)
    
    results["improved_with_dates"] = {
        "today_hours": len(improved_adapter.hourly_prices),
        "tomorrow_hours": len(improved_adapter.tomorrow_prices) if improved_adapter.tomorrow_prices else 0,
        "tomorrow_valid": improved_adapter.is_tomorrow_valid(),
        "sample_hours": list(improved_adapter.hourly_prices.keys())[:5]
    }
    
    logger.info(f"Improved adapter with data with dates: "
               f"Today hours: {results['improved_with_dates']['today_hours']}, "
               f"Tomorrow hours: {results['improved_with_dates']['tomorrow_hours']}, "
               f"Tomorrow valid: {results['improved_with_dates']['tomorrow_valid']}")
    
    # Testing with mixed data containing both today's and tomorrow's data in hourly_prices
    logger.info("Testing with mixed data (today + tomorrow in hourly_prices)")
    mixed_data = create_test_data_mixed()
    
    # Standard adapter
    standard_adapter = ElectricityPriceAdapter(hass, [mixed_data], False)
    
    results["standard_mixed"] = {
        "today_hours": len(standard_adapter.hourly_prices),
        "tomorrow_hours": len(standard_adapter.tomorrow_prices) if standard_adapter.tomorrow_prices else 0,
        "tomorrow_valid": standard_adapter.is_tomorrow_valid(),
        "sample_hours": list(standard_adapter.hourly_prices.keys())[:5]
    }
    
    logger.info(f"Standard adapter with mixed data: "
               f"Today hours: {results['standard_mixed']['today_hours']}, "
               f"Tomorrow hours: {results['standard_mixed']['tomorrow_hours']}, "
               f"Tomorrow valid: {results['standard_mixed']['tomorrow_valid']}")
    
    # Improved adapter
    improved_adapter = ImprovedElectricityPriceAdapter(hass, [mixed_data], False)
    
    results["improved_mixed"] = {
        "today_hours": len(improved_adapter.hourly_prices),
        "tomorrow_hours": len(improved_adapter.tomorrow_prices) if improved_adapter.tomorrow_prices else 0,
        "tomorrow_valid": improved_adapter.is_tomorrow_valid(),
        "sample_hours": list(improved_adapter.hourly_prices.keys())[:5]
    }
    
    logger.info(f"Improved adapter with mixed data: "
               f"Today hours: {results['improved_mixed']['today_hours']}, "
               f"Tomorrow hours: {results['improved_mixed']['tomorrow_hours']}, "
               f"Tomorrow valid: {results['improved_mixed']['tomorrow_valid']}")
    
    return results

def test_with_entsoe_data():
    """Test adapters with real ENTSO-E data.
    
    Returns:
        Dictionary with test results
    """
    logger.info("=== Testing adapters with ENTSO-E data ===")
    
    results = {}
    
    # Path to the ENTSO-E API response files
    entsoe_response_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "entsoe_responses")
    
    # Find all ENTSO-E response files
    if not os.path.exists(entsoe_response_dir):
        logger.error(f"ENTSO-E response directory not found: {entsoe_response_dir}")
        return {"error": "ENTSO-E response directory not found"}
        
    response_files = [f for f in os.listdir(entsoe_response_dir) if f.startswith("entsoe_") and f.endswith(".xml")]
    if not response_files:
        logger.error("No ENTSO-E response files found")
        return {"error": "No ENTSO-E response files found"}
    
    # Test with each response file
    for filename in response_files:
        logger.info(f"Testing with ENTSO-E response file: {filename}")
        
        # Load ENTSO-E API response
        file_path = os.path.join(entsoe_response_dir, filename)
        xml_data = load_entsoe_response(file_path)
        if not xml_data:
            logger.warning(f"Could not load ENTSO-E response file: {filename}")
            continue
        
        # Create mock HASS instance
        hass = MockHass()
    
        # Parse the XML data using EntsoeParser
        parser = EntsoeParser()
        hourly_prices = parser.parse_hourly_prices(xml_data, "SE4")
        
        # Show sample hourly prices
        logger.info(f"Sample hourly prices from parser: {list(hourly_prices.items())[:5]}")
        
        # Create raw data structure
        raw_data = {
            "hourly_prices": hourly_prices,
            "source": "entsoe",
            "currency": "EUR",
            "area": "SE4"
        }
        
        # Test with standard adapter
        standard_adapter = ElectricityPriceAdapter(hass, [raw_data], False)
        
        # Check if adapter correctly extracts tomorrow's data
        standard_tomorrow_prices = standard_adapter.tomorrow_prices
        
        # Test with improved adapter
        improved_adapter = ImprovedElectricityPriceAdapter(hass, [raw_data], False)
        
        # Check if adapter correctly extracts tomorrow's data
        improved_tomorrow_prices = improved_adapter.tomorrow_prices
        
        # Store results for this file
        results[filename] = {
            "standard": {
                "today_hours": len(standard_adapter.hourly_prices),
                "tomorrow_hours": len(standard_tomorrow_prices) if standard_tomorrow_prices else 0,
                "tomorrow_valid": standard_adapter.is_tomorrow_valid(),
                "sample_hours": list(standard_adapter.hourly_prices.keys())[:5]
            },
            "improved": {
                "today_hours": len(improved_adapter.hourly_prices),
                "tomorrow_hours": len(improved_tomorrow_prices) if improved_tomorrow_prices else 0,
                "tomorrow_valid": improved_adapter.is_tomorrow_valid(),
                "sample_hours": list(improved_adapter.hourly_prices.keys())[:5]
            }
        }
        
        logger.info(f"Standard adapter: Tomorrow valid: {results[filename]['standard']['tomorrow_valid']}, "
                   f"Today hours: {results[filename]['standard']['today_hours']}, "
                   f"Tomorrow hours: {results[filename]['standard']['tomorrow_hours']}")
        
        logger.info(f"Improved adapter: Tomorrow valid: {results[filename]['improved']['tomorrow_valid']}, "
                   f"Today hours: {results[filename]['improved']['today_hours']}, "
                   f"Tomorrow hours: {results[filename]['improved']['tomorrow_hours']}")
    
    return results

async def test_with_live_api_data(
    parser_name: str,
    area: str,
    timeout: int = 30
) -> Dict[str, Any]:
    """Test adapters with data from live API.
    
    Args:
        parser_name: Name of the parser to test
        area: Area code to test
        timeout: API request timeout in seconds
        
    Returns:
        Dictionary with test results
    """
    logger.info(f"=== Testing adapters with live API data: {parser_name} for {area} ===")
    
    results = {
        "parser": parser_name,
        "area": area,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        # Test using cache first, then API if cache fails
        cache_dir = "./parser_cache"
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, f"{parser_name}_{area}.json")
        
        # Try cache first
        use_cache = False
        if os.path.exists(cache_file):
            file_time = os.path.getmtime(cache_file)
            file_age = datetime.now().timestamp() - file_time
            if file_age < 24 * 60 * 60:  # 24 hours in seconds
                use_cache = True
                
        data = None
        if use_cache:
            logger.info(f"Using cached data for {parser_name} ({area})")
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache for {parser_name} ({area}): {e}")
                use_cache = False
        
        # Fall back to API if cache missing or failed
        if not use_cache or not data:
            logger.info(f"Fetching live data from {parser_name} API for {area}")
            
            # Create mock HASS instance
            mock_hass = MockHass()
            
            # Build config
            config = build_api_key_config(parser_name, area)
            config["request_timeout"] = timeout
            
            # Fetch data
            session = aiohttp.ClientSession()
            try:
                data = await fetch_day_ahead_prices(
                    source_type=parser_name,
                    config=config,
                    area=area,
                    currency=Currency.EUR,
                    hass=mock_hass,
                    session=session
                )
                
                # Cache the result for future use
                with open(cache_file, "w") as f:
                    json.dump(data, f, cls=DateTimeEncoder)
                    
                results["data_source"] = "api"
            finally:
                if session and not session.closed:
                    await session.close()
        else:
            results["data_source"] = "cache"
        
        if not data:
            logger.error(f"No data returned from {parser_name} API")
            results["error"] = "No data returned from API"
            return results
        
        # Test with standard adapter
        standard_adapter = ElectricityPriceAdapter(mock_hass, [data], False)
        
        # Store results for standard adapter
        results["standard"] = {
            "today_hours": len(standard_adapter.hourly_prices),
            "tomorrow_hours": len(standard_adapter.tomorrow_prices) if standard_adapter.tomorrow_prices else 0,
            "tomorrow_valid": standard_adapter.is_tomorrow_valid(),
            "sample_hours": list(standard_adapter.hourly_prices.keys())[:5]
        }
        
        logger.info(f"Standard adapter: Tomorrow valid: {results['standard']['tomorrow_valid']}, "
                   f"Today hours: {results['standard']['today_hours']}, "
                   f"Tomorrow hours: {results['standard']['tomorrow_hours']}")
        
        # Test with improved adapter
        improved_adapter = ImprovedElectricityPriceAdapter(mock_hass, [data], False)
        
        # Store results for improved adapter
        results["improved"] = {
            "today_hours": len(improved_adapter.hourly_prices),
            "tomorrow_hours": len(improved_adapter.tomorrow_prices) if improved_adapter.tomorrow_prices else 0,
            "tomorrow_valid": improved_adapter.is_tomorrow_valid(),
            "sample_hours": list(improved_adapter.hourly_prices.keys())[:5]
        }
        
        logger.info(f"Improved adapter: Tomorrow valid: {results['improved']['tomorrow_valid']}, "
                   f"Today hours: {results['improved']['today_hours']}, "
                   f"Tomorrow hours: {results['improved']['tomorrow_hours']}")
        
        # Record if improved adapter did better than standard
        if results["improved"]["tomorrow_valid"] and not results["standard"]["tomorrow_valid"]:
            results["improved_advantage"] = True
            logger.info("Improved adapter successfully extracted tomorrow's data, but standard adapter did not.")
        else:
            results["improved_advantage"] = False
    
    except Exception as e:
        logger.error(f"Error testing with live API data: {e}")
        results["error"] = str(e)
    
    return results

def parse_args() -> argparse.Namespace:
    """Parse command line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(description="Test ElectricityPriceAdapter implementations")
    
    # Test selection options
    parser.add_argument("--test-all", action="store_true", help="Run all tests")
    parser.add_argument("--test-synthetic", action="store_true", help="Test with synthetic data")
    parser.add_argument("--test-entsoe", action="store_true", help="Test with ENTSO-E data")
    parser.add_argument("--test-live", action="store_true", help="Test with live API data")
    
    # API selection options
    parser.add_argument("--parser", help="Specific parser to test with live API (e.g., entsoe, nordpool)")
    parser.add_argument("--area", help="Specific area to test with live API (e.g., SE4, SE3)")
    
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
    synthetic_results: Dict[str, Any] = None,
    entsoe_results: Dict[str, Any] = None,
    live_results: Dict[str, Any] = None
) -> None:
    """Print a summary of the test results.
    
    Args:
        synthetic_results: Results from testing with synthetic data
        entsoe_results: Results from testing with ENTSO-E data
        live_results: Results from testing with live API data
    """
    print("\n" + "=" * 80)
    print("ADAPTER TEST SUMMARY")
    print("=" * 80)
    
    if synthetic_results:
        print("\n=== Synthetic Data Tests ===")
        # Without dates
        print("Data without dates:")
        print(f"  Standard adapter: Today hours: {synthetic_results['standard_without_dates']['today_hours']}, "
              f"Tomorrow hours: {synthetic_results['standard_without_dates']['tomorrow_hours']}, "
              f"Tomorrow valid: {synthetic_results['standard_without_dates']['tomorrow_valid']}")
        print(f"  Improved adapter: Today hours: {synthetic_results['improved_without_dates']['today_hours']}, "
              f"Tomorrow hours: {synthetic_results['improved_without_dates']['tomorrow_hours']}, "
              f"Tomorrow valid: {synthetic_results['improved_without_dates']['tomorrow_valid']}")
        
        # With dates
        print("Data with ISO dates:")
        print(f"  Standard adapter: Today hours: {synthetic_results['standard_with_dates']['today_hours']}, "
              f"Tomorrow hours: {synthetic_results['standard_with_dates']['tomorrow_hours']}, "
              f"Tomorrow valid: {synthetic_results['standard_with_dates']['tomorrow_valid']}")
        print(f"  Improved adapter: Today hours: {synthetic_results['improved_with_dates']['today_hours']}, "
              f"Tomorrow hours: {synthetic_results['improved_with_dates']['tomorrow_hours']}, "
              f"Tomorrow valid: {synthetic_results['improved_with_dates']['tomorrow_valid']}")
        
        # Mixed data
        print("Mixed data (today + tomorrow in hourly_prices):")
        print(f"  Standard adapter: Today hours: {synthetic_results['standard_mixed']['today_hours']}, "
              f"Tomorrow hours: {synthetic_results['standard_mixed']['tomorrow_hours']}, "
              f"Tomorrow valid: {synthetic_results['standard_mixed']['tomorrow_valid']}")
        print(f"  Improved adapter: Today hours: {synthetic_results['improved_mixed']['today_hours']}, "
              f"Tomorrow hours: {synthetic_results['improved_mixed']['tomorrow_hours']}, "
              f"Tomorrow valid: {synthetic_results['improved_mixed']['tomorrow_valid']}")
    
    if entsoe_results:
        print("\n=== ENTSO-E Data Tests ===")
        if "error" in entsoe_results:
            print(f"Error: {entsoe_results['error']}")
        else:
            for filename, results in entsoe_results.items():
                if filename != "error":
                    print(f"{filename}:")
                    print(f"  Standard adapter: Today hours: {results['standard']['today_hours']}, "
                          f"Tomorrow hours: {results['standard']['tomorrow_hours']}, "
                          f"Tomorrow valid: {results['standard']['tomorrow_valid']}")
                    print(f"  Improved adapter: Today hours: {results['improved']['today_hours']}, "
                          f"Tomorrow hours: {results['improved']['tomorrow_hours']}, "
                          f"Tomorrow valid: {results['improved']['tomorrow_valid']}")
    
    if live_results:
        print("\n=== Live API Data Tests ===")
        if "error" in live_results:
            print(f"Error: {live_results['error']}")
        else:
            print(f"Parser: {live_results.get('parser')}, Area: {live_results.get('area')}, Source: {live_results.get('data_source', 'unknown')}")
            print(f"  Standard adapter: Today hours: {live_results['standard']['today_hours']}, "
                  f"Tomorrow hours: {live_results['standard']['tomorrow_hours']}, "
                  f"Tomorrow valid: {live_results['standard']['tomorrow_valid']}")
            print(f"  Improved adapter: Today hours: {live_results['improved']['today_hours']}, "
                  f"Tomorrow hours: {live_results['improved']['tomorrow_hours']}, "
                  f"Tomorrow valid: {live_results['improved']['tomorrow_valid']}")
            
            if live_results.get("improved_advantage", False):
                print("  RESULT: Improved adapter successfully extracted tomorrow's data, but standard adapter did not.")
    
    print("\nFor detailed results, check the files in the test_results directory.")

async def main() -> int:
    """Run the adapter tests.
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    args = parse_args()
    setup_logging(args.debug)
    
    # Get current timestamp for file naming
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Determine which tests to run
    run_all = args.test_all or not (args.test_synthetic or args.test_entsoe or args.test_live)
    run_synthetic = run_all or args.test_synthetic
    run_entsoe = run_all or args.test_entsoe
    run_live = run_all or args.test_live
    
    # Store all results
    synthetic_results = None
    entsoe_results = None
    live_results = None
    
    # Run synthetic data tests
    if run_synthetic:
        logger.info("=== Running synthetic data tests ===")
        synthetic_results = test_with_synthetic_data()
        save_results(synthetic_results, f"adapter_synthetic_{timestamp}.json", args.results_dir)
    
    # Run ENTSO-E data tests
    if run_entsoe:
        logger.info("=== Running ENTSO-E data tests ===")
        entsoe_results = test_with_entsoe_data()
        save_results(entsoe_results, f"adapter_entsoe_{timestamp}.json", args.results_dir)
    
    # Run live API tests
    if run_live:
        logger.info("=== Running live API tests ===")
        parser_name = args.parser or "entsoe"
        area = args.area or {"entsoe": "SE4", "nordpool": "SE3", "epex": "DE", 
                            "omie": "ES", "energi_data_service": "DK1", 
                            "aemo": "NSW1", "comed": "US", "stromligning": "NO1"}.get(parser_name, "SE4")
        
        live_results = await test_with_live_api_data(
            parser_name=parser_name,
            area=area,
            timeout=args.timeout
        )
        save_results(live_results, f"adapter_live_{parser_name}_{area}_{timestamp}.json", args.results_dir)
    
    # Print summary
    print_summary(synthetic_results, entsoe_results, live_results)
    
    logger.info("All tests completed successfully")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
