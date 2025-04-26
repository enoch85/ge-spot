"""API testing functionality for GE-Spot integration."""
import logging
import traceback
import asyncio
from typing import Dict, Any, List, Tuple

import aiohttp
from custom_components.ge_spot.const.config import Config
from custom_components.ge_spot.const.currencies import Currency
# Import create_api instead of fetch_day_ahead_prices
from custom_components.ge_spot.api import get_sources_for_region, create_api
from custom_components.ge_spot.api.base.data_fetch import is_skipped_response

from ..mocks.hass import MockHass
from ..utils.general import build_api_key_config, _ASKED_KEYS

logger = logging.getLogger(__name__)

# Map of APIs to the regions they support (will be filled dynamically)
api_region_map = {}


async def test_api_area(api_name: str, area: str, timeout: int) -> Dict[str, Any]:
    """Test a specific API for a specific area.
    
    Args:
        api_name: Name of the API to test
        area: Area code to test
        timeout: Request timeout in seconds
        
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
        "debug_info": {}
    }
    
    try:
        # Build config with API keys
        config = build_api_key_config(api_name, area)
        config["request_timeout"] = timeout
        
        # Check if we should skip this test due to missing keys
        should_skip = False
        skip_reason = ""
        
        if api_name == "entsoe" and not config.get(Config.API_KEY) and "API_KEY" in globals().get("_ASKED_KEYS", set()):
            should_skip = True
            skip_reason = "ENTSO-E API key not provided"
        elif api_name == "epex" and area == "FR":
            if not config.get("rte_client_id") and "RTE_CLIENT_ID" in globals().get("_ASKED_KEYS", set()):
                should_skip = True
                skip_reason = "RTE Client ID not provided for France"
            elif not config.get("rte_client_secret") and "RTE_CLIENT_SECRET" in globals().get("_ASKED_KEYS", set()):
                should_skip = True
                skip_reason = "RTE Client Secret not provided for France"
        
        if should_skip:
            logger.warning(f"  ⚠️ Skipped: {skip_reason}")
            result["status"] = "skipped"
            result["message"] = skip_reason
            return result
        
        # Fetch data from the API
        logger.debug(f"  Fetching data from {api_name} for {area} with config: {config}")
        try:
            # Instantiate the correct API using create_api
            api_instance = create_api(source_type=api_name, config=config, session=session)

            # Call the fetch_day_ahead_prices method on the instance
            api_result = await api_instance.fetch_day_ahead_prices(
                area=area,
                currency=Currency.EUR, # Assuming EUR, adjust if needed based on context
                hass=mock_hass # Pass hass if required by the method
                # session is likely handled by the instance now, so removed from call
            )
        except TypeError as e:
            # Handle potential TypeError if method signature changed significantly
            # This retry logic might need adjustment based on the actual API method signatures
            if "got an unexpected keyword argument" in str(e):
                logger.debug(f"API method doesn't accept all parameters: {str(e)}, retrying with basic params")
                # Retry with potentially fewer arguments if the first attempt failed
                # Re-instantiate or use existing instance
                api_instance_retry = create_api(source_type=api_name, config=config, session=session)
                try:
                    # Try calling with minimal arguments known to be required
                    api_result = await api_instance_retry.fetch_day_ahead_prices(
                        area=area
                        # Add other essential kwargs if known
                    )
                except Exception as retry_e:
                     logger.error(f"Retry failed: {retry_e}")
                     raise retry_e # Re-raise the exception from the retry attempt
            else:
                raise # Re-raise original TypeError if it's not about unexpected kwargs
        except Exception as fetch_exc:
             logger.error(f"Error fetching data: {fetch_exc}")
             raise fetch_exc # Re-raise any other fetching error

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
                logger.info(f"  ✅ Success: price={current_price}")
                result["status"] = "success"
                result["message"] = f"Successfully fetched price data: {current_price}"
                result["debug_info"]["price"] = current_price
                result["debug_info"]["hour_count"] = len(api_result["hourly_prices"])
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
    
    return result

# TODO: Add further assertions for value types and edge cases in future test improvements.


async def run_tests(apis_to_test: List[str], areas_to_test: List[str], timeout: int) -> Dict[str, Any]:
    """Run tests for specified APIs and areas.
    
    Args:
        apis_to_test: List of API names to test
        areas_to_test: List of area codes to test
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary with test results
    """
    global api_region_map
    
    # Build list of tests to run
    tests_to_run = []
    
    # Initialize api_region_map
    api_region_map = {}
    
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
            # Store in the mapping for later reference
            if "comed" not in api_region_map:
                api_region_map["comed"] = []
            api_region_map["comed"].append(area)
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
                # Store in the mapping for later reference
                if api not in api_region_map:
                    api_region_map[api] = []
                api_region_map[api].append(area)
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
        tasks = [test_api_area(api, area, timeout) for area in areas]
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
    
    for result in all_results:
        api = result["api"]
        area = result["area"]
        status = result["status"]
        
        # Add to status group
        results_by_status[status].append((api, area))
        
        # Initialize API results if needed
        if api not in api_results:
            api_results[api] = {
                "success": 0,
                "skipped": 0,
                "not_available": 0,
                "failure": 0,
                "total": 0
            }
        
        # Initialize area results if needed
        if area not in area_results:
            area_results[area] = {
                "success": 0,
                "skipped": 0,
                "not_available": 0,
                "failure": 0,
                "total": 0
            }
        
        # Update counters
        api_results[api][status] += 1
        api_results[api]["total"] += 1
        area_results[area][status] += 1
        area_results[area]["total"] += 1
    
    # Return aggregated results
    return {
        "tests_run": len(all_results),
        "by_status": results_by_status,
        "by_api": api_results,
        "by_area": area_results,
        "api_region_map": api_region_map,
        "all_results": all_results
    }
