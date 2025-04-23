"""API testing functionality for date range utility."""
import logging
import argparse
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

import aiohttp
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.api import get_sources_for_region, fetch_day_ahead_prices
from custom_components.ge_spot.api.base.data_fetch import is_skipped_response
from custom_components.ge_spot.utils.date_range import generate_date_ranges

from ..mocks.hass import MockHass
from ..utils.general import build_api_key_config, get_all_areas, get_all_apis

logger = logging.getLogger(__name__)

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Test date range utility with all APIs")
    parser.add_argument("--apis", nargs="+", help="Specific APIs to test")
    parser.add_argument("--regions", nargs="+", help="Specific regions to test")
    parser.add_argument("--log-level", default="INFO", help="Set logging level")
    parser.add_argument("--timeout", type=int, default=30, help="Set request timeout in seconds")
    parser.add_argument("--reference-time", help="Set reference time for testing (ISO format)")
    parser.add_argument("--test-tomorrow", action="store_true", help="Test tomorrow's data specifically")
    return parser.parse_args()

async def test_api_with_date_range(
    api_name: str,
    area: str,
    timeout: int,
    reference_time: Optional[datetime] = None,
    test_tomorrow: bool = False
) -> Dict[str, Any]:
    """Test a specific API with the date range utility.
    
    Args:
        api_name: Name of the API to test
        area: Area code to test
        timeout: Request timeout in seconds
        reference_time: Optional reference time for testing
        test_tomorrow: Whether to test tomorrow's data specifically
        
    Returns:
        Dictionary with test results
    """
    logger.info(f"Testing API: {api_name} for Area: {area}")
    
    # Create a new session for this test
    session = aiohttp.ClientSession()
    mock_hass = MockHass()
    
    result = {
        "api": api_name,
        "area": area,
        "status": "unknown",
        "message": "",
        "debug_info": {},
        "has_tomorrow_data": False
    }
    
    try:
        # Build config with API keys
        config = build_api_key_config(api_name, area)
        config["request_timeout"] = timeout
        
        # Set reference time if provided
        if reference_time:
            logger.debug(f"Using reference time: {reference_time.isoformat()}")
        
        # Generate date ranges for debugging
        reference = reference_time or datetime.now(timezone.utc)
        date_ranges = generate_date_ranges(
            reference,
            api_name
        )
        
        # Log date ranges for debugging
        logger.info(f"API: {api_name}, Area: {area}, Reference time: {reference.isoformat()}")
        logger.info(f"Generated {len(date_ranges)} date ranges for {api_name}:")
        for i, (start, end) in enumerate(date_ranges):
            logger.info(f"  Range {i+1}: {start.isoformat()} to {end.isoformat()}")
        
        # Fetch data from the API
        logger.debug(f"Fetching data from {api_name} for {area} with config: {config}")
        try:
            api_result = await fetch_day_ahead_prices(
                source_type=api_name,
                config=config,
                area=area,
                currency=Currency.EUR,
                reference_time=reference_time,
                hass=mock_hass,
                session=session
            )
        except TypeError as e:
            if "got an unexpected keyword argument" in str(e):
                # If the function doesn't accept some parameter, retry without it
                logger.debug(f"API doesn't accept all parameters: {str(e)}, retrying with basic params")
                api_result = await fetch_day_ahead_prices(
                    source_type=api_name,
                    config=config,
                    area=area,
                    currency=Currency.EUR,
                    reference_time=reference_time
                )
            else:
                raise
        
        # Process the result
        if is_skipped_response(api_result):
            reason = api_result.get('reason', 'unknown') if isinstance(api_result, dict) else 'unknown'
            logger.warning(f"  ⚠️ Skipped: {reason}")
            result["status"] = "skipped"
            result["message"] = f"API was skipped: {reason}"
            result["debug_info"]["skip_response"] = api_result
        elif api_result and isinstance(api_result, dict):
            # Assert required keys for standardized API format
            required_keys = ["hourly_prices", "currency", "timezone"]
            missing_keys = [k for k in required_keys if k not in api_result]
            if missing_keys:
                error_msg = f"API result missing required keys: {missing_keys}"
                logger.error(f"  ❌ Failed: {error_msg}")
                result["status"] = "failure"
                result["message"] = error_msg
                result["debug_info"]["response"] = api_result
            elif api_result["hourly_prices"]:
                # We have hourly prices data
                current_price = "N/A"
                if "current_price" in api_result and api_result["current_price"] is not None:
                    current_price = f"{api_result['current_price']:.3f} {api_result.get('currency', 'EUR')}"
                
                # Check if we have tomorrow's data
                has_tomorrow_data = False
                if "tomorrow_hourly_prices" in api_result and api_result["tomorrow_hourly_prices"]:
                    has_tomorrow_data = True
                    result["has_tomorrow_data"] = True
                    logger.info(f"  ✅ Success: price={current_price}, has tomorrow's data: {len(api_result['tomorrow_hourly_prices'])} hours")
                else:
                    # Check if we have data for tomorrow in the hourly_prices
                    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date()
                    tomorrow_hours = 0
                    
                    for hour_key, price in api_result["hourly_prices"].items():
                        # Try to parse the hour key to check if it's for tomorrow
                        if "T" in hour_key:  # ISO format with date
                            try:
                                hour_dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                                if hour_dt.date() == tomorrow:
                                    tomorrow_hours += 1
                            except (ValueError, TypeError):
                                pass
                    
                    if tomorrow_hours > 0:
                        has_tomorrow_data = True
                        result["has_tomorrow_data"] = True
                        logger.info(f"  ✅ Success: price={current_price}, has tomorrow's data: {tomorrow_hours} hours")
                    else:
                        logger.info(f"  ✅ Success: price={current_price}, no tomorrow's data")
                
                result["status"] = "success"
                result["message"] = f"Successfully fetched price data: {current_price}"
                result["debug_info"]["price"] = current_price
                result["debug_info"]["hour_count"] = len(api_result["hourly_prices"])
                result["debug_info"]["has_tomorrow_data"] = has_tomorrow_data
                
                # If we're specifically testing tomorrow's data and don't have it, mark as failure
                if test_tomorrow and not has_tomorrow_data:
                    result["status"] = "failure"
                    result["message"] = "No tomorrow's data found when specifically testing for it"
            else:
                # API returned a valid response but no hourly prices - count as "data not available"
                logger.warning(f"  ℹ️ Not Available: API returned valid response but no hourly prices")
                logger.debug(f"  API response structure: {api_result.keys()}")
                result["status"] = "not_available"
                result["message"] = "API returned valid response but no hourly prices"
                result["debug_info"]["response"] = api_result
        elif api_result and isinstance(api_result, str) and "No matching data found" in api_result:
            logger.warning(f"  ℹ️ Not Available: No matching data found")
            result["status"] = "not_available"
            result["message"] = "API returned: No matching data found"
            result["debug_info"]["response"] = api_result
        else:
            error_msg = f"No valid data returned or unexpected response: {api_result}"
            logger.error(f"  ❌ Failed: {error_msg}")
            result["status"] = "failure"
            result["message"] = error_msg
            result["debug_info"]["response"] = api_result
    
    except Exception as e:
        import traceback
        trace = traceback.format_exc()
        error_msg = f"Error during test: {str(e)}"
        logger.error(f"  ❌ {error_msg}")
        logger.debug(trace)
        result["status"] = "failure"
        result["message"] = error_msg
        result["debug_info"]["error"] = str(e)
        result["debug_info"]["traceback"] = trace
    
    finally:
        # Clean up the session
        if session and not session.closed:
            await session.close()
    
    # TODO: Add further assertions for value types and edge cases in future test improvements.
    
    return result

async def run_tests(
    apis_to_test: List[str],
    areas_to_test: List[str],
    timeout: int,
    reference_time: Optional[datetime] = None,
    test_tomorrow: bool = False
) -> Dict[str, Any]:
    """Run tests for specified APIs and areas.
    
    Args:
        apis_to_test: List of API names to test
        areas_to_test: List of area codes to test
        timeout: Request timeout in seconds
        reference_time: Optional reference time for testing
        test_tomorrow: Whether to test tomorrow's data specifically
        
    Returns:
        Dictionary with test results
    """
    # Build list of tests to run
    tests_to_run = []
    
    # Special handling for ComEd which uses endpoint names as areas
    comed_areas = []
    if "comed" in apis_to_test:
        from custom_components.ge_spot.const.api import ComEd
        comed_areas = ComEd.AREAS
        logger.info(f"Using ComEd areas: {comed_areas}")
    
    for area in areas_to_test:
        # Special handling for ComEd areas
        if area in comed_areas and "comed" in apis_to_test:
            tests_to_run.append(("comed", area))
            continue
            
        try:
            # Get the sources supporting this area
            area_sources = get_sources_for_region(area)
            
            # Filter by requested APIs
            area_sources = [s for s in area_sources if s in apis_to_test]
            
            if not area_sources:
                logger.warning(f"No APIs support area {area} in the requested API list")
                continue
            
            # Add tests for this area
            for api in area_sources:
                tests_to_run.append((api, area))
        except Exception as e:
            logger.error(f"Error processing area {area}: {e}")
            continue
    
    logger.info(f"Identified {len(tests_to_run)} API-region combinations to test")
    
    # Run the tests with limited concurrency to avoid overwhelming APIs
    concurrency_limit = min(5, len(tests_to_run))
    
    # Group tests by API to avoid hitting rate limits
    tests_by_api = {}
    for api, area in tests_to_run:
        if api not in tests_by_api:
            tests_by_api[api] = []
        tests_by_api[api].append(area)
    
    # Run all tests
    all_results = []
    
    for api, areas in tests_by_api.items():
        logger.info(f"Testing API: {api} for {len(areas)} areas")
        
        # Run tests for this API with limited concurrency
        tasks = [
            test_api_with_date_range(
                api, area, timeout, reference_time, test_tomorrow
            ) for area in areas
        ]
        
        for batch in [tasks[i:i+concurrency_limit] for i in range(0, len(tasks), concurrency_limit)]:
            batch_results = await asyncio.gather(*batch)
            all_results.extend(batch_results)
            
            # Add a small delay between batches to avoid rate limiting
            if len(batch) >= concurrency_limit:
                await asyncio.sleep(1)
    
    # Aggregate results
    results_by_status = {
        "success": [],
        "skipped": [],
        "not_available": [],
        "failure": []
    }
    
    api_results = {}
    area_results = {}
    tomorrow_results = {
        "has_tomorrow_data": [],
        "no_tomorrow_data": []
    }
    
    for result in all_results:
        api = result["api"]
        area = result["area"]
        status = result["status"]
        has_tomorrow_data = result.get("has_tomorrow_data", False)
        
        # Add to status group
        results_by_status[status].append((api, area))
        
        # Add to tomorrow data group
        if has_tomorrow_data:
            tomorrow_results["has_tomorrow_data"].append((api, area))
        else:
            tomorrow_results["no_tomorrow_data"].append((api, area))
        
        # Initialize API results if needed
        if api not in api_results:
            api_results[api] = {
                "success": 0,
                "skipped": 0,
                "not_available": 0,
                "failure": 0,
                "total": 0,
                "has_tomorrow_data": 0
            }
        
        # Initialize area results if needed
        if area not in area_results:
            area_results[area] = {
                "success": 0,
                "skipped": 0,
                "not_available": 0,
                "failure": 0,
                "total": 0,
                "has_tomorrow_data": 0
            }
        
        # Update counters
        api_results[api][status] += 1
        api_results[api]["total"] += 1
        if has_tomorrow_data:
            api_results[api]["has_tomorrow_data"] += 1
            
        area_results[area][status] += 1
        area_results[area]["total"] += 1
        if has_tomorrow_data:
            area_results[area]["has_tomorrow_data"] += 1
    
    # Return aggregated results
    return {
        "tests_run": len(all_results),
        "by_status": results_by_status,
        "by_api": api_results,
        "by_area": area_results,
        "tomorrow_results": tomorrow_results,
        "all_results": all_results
    }

def print_summary(results: Dict[str, Any]):
    """Print a summary of the test results.
    
    Args:
        results: Test results from run_tests
    """
    print("\n" + "=" * 80)
    print(f"DATE RANGE UTILITY TEST SUMMARY")
    print("=" * 80)
    
    # Print overall statistics
    print(f"\nRan {results['tests_run']} tests in {results.get('duration', 0):.2f} seconds")
    print(f"Success: {len(results['by_status']['success'])}")
    print(f"Skipped: {len(results['by_status']['skipped'])}")
    print(f"Not Available: {len(results['by_status']['not_available'])}")
    print(f"Failure: {len(results['by_status']['failure'])}")
    
    # Print tomorrow data statistics
    print(f"\nTomorrow's Data:")
    print(f"  Has Tomorrow Data: {len(results['tomorrow_results']['has_tomorrow_data'])}")
    print(f"  No Tomorrow Data: {len(results['tomorrow_results']['no_tomorrow_data'])}")
    
    # Print API statistics
    print("\nResults by API:")
    for api, stats in results["by_api"].items():
        print(f"  {api}:")
        print(f"    Success: {stats['success']}/{stats['total']}")
        print(f"    Has Tomorrow Data: {stats['has_tomorrow_data']}/{stats['total']}")
        if stats['skipped'] > 0:
            print(f"    Skipped: {stats['skipped']}")
        if stats['not_available'] > 0:
            print(f"    Not Available: {stats['not_available']}")
        if stats['failure'] > 0:
            print(f"    Failure: {stats['failure']}")
    
    # Print failures if any
    if results['by_status']['failure']:
        print("\nFailures:")
        for api, area in results['by_status']['failure']:
            # Find the result for this API and area
            for result in results['all_results']:
                if result['api'] == api and result['area'] == area:
                    print(f"  {api} - {area}: {result['message']}")
                    break
    
    print("\n" + "=" * 80)
