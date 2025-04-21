"""Tomorrow API testing functionality for GE-Spot integration."""
import logging
import traceback
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.api import fetch_day_ahead_prices
from custom_components.ge_spot.price.adapter import ElectricityPriceAdapter
from custom_components.ge_spot.price.cache import PriceCache
from custom_components.ge_spot.timezone import TimezoneService

from ..mocks.hass import MockHass
from ..utils.general import build_api_key_config
from ..core.adapter_testing import ImprovedElectricityPriceAdapter

import subprocess

logger = logging.getLogger(__name__)

async def test_direct_api_call(api_name: str, area: str) -> Dict[str, Any]:
    """Make a direct API call using curl and display the results.
    
    Args:
        api_name: Name of the API to test
        area: Area code to test
        
    Returns:
        Dictionary with test results
    """
    logger.info(f"Making direct API call for {api_name} (area: {area})")
    
    result = {
        "api": api_name,
        "area": area,
        "status": "unknown",
        "direct_api_success": False
    }
    
    try:
        if api_name == "nordpool":
            # Get tomorrow's date
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            
            # Construct the curl command
            curl_cmd = f'curl "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices?currency=EUR&date={tomorrow}&market=DayAhead&deliveryArea={area}"'
            logger.info(f"Executing direct API call: {curl_cmd}")
            
            # Execute the curl command
            process = subprocess.run(curl_cmd, shell=True, capture_output=True, text=True)
            
            if process.returncode == 0:
                logger.info("Direct API call successful")
                
                # Try to parse the response as JSON
                try:
                    response_data = json.loads(process.stdout)
                    logger.info(f"Response contains {len(response_data.get('multiAreaEntries', []))} entries")
                    
                    # Log a sample of the data
                    if response_data.get('multiAreaEntries'):
                        sample = response_data['multiAreaEntries'][0]
                        logger.info(f"Sample data: {json.dumps(sample, indent=2)[:500]}...")
                    
                    result["direct_api_success"] = True
                    result["status"] = "success"
                except json.JSONDecodeError:
                    logger.warning("Failed to parse response as JSON")
                    logger.info(f"Raw response: {process.stdout[:500]}...")
                    result["status"] = "error"
            else:
                logger.error(f"Direct API call failed: {process.stderr}")
                result["status"] = "error"
        
        elif api_name == "entsoe":
            logger.info("Direct API call for ENTSOE requires an API key")
            logger.info("Example curl command: curl -X GET 'https://transparency.entsoe.eu/api?securityToken=YOUR_API_KEY&documentType=A44&in_Domain=10Y1001A1001A47J&out_Domain=10Y1001A1001A47J&periodStart=YYYYMMDDHHMM&periodEnd=YYYYMMDDHHMM'")
            result["status"] = "not_implemented"
        
        elif api_name == "epex":
            logger.info("Direct API call for EPEX not implemented")
            result["status"] = "not_implemented"
        
        elif api_name == "omie":
            # Get tomorrow's date
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d_%m_%Y")
            
            # Construct the curl command
            curl_cmd = f'curl "https://www.omie.es/en/file-download?parents%5B0%5D=&filename=marginalpdbc_{tomorrow}.1"'
            logger.info(f"Executing direct API call: {curl_cmd}")
            
            # Execute the curl command
            process = subprocess.run(curl_cmd, shell=True, capture_output=True, text=True)
            
            if process.returncode == 0:
                logger.info("Direct API call successful")
                logger.info(f"Raw response (first 500 chars): {process.stdout[:500]}...")
                result["direct_api_success"] = True
                result["status"] = "success"
            else:
                logger.error(f"Direct API call failed: {process.stderr}")
                result["status"] = "error"
        
        elif api_name == "energi_data_service":
            # Get tomorrow's and day after tomorrow's dates
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            day_after_tomorrow = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
            
            # Construct the curl command
            curl_cmd = f'curl "https://api.energidataservice.dk/dataset/Elspotprices?start={tomorrow}&end={day_after_tomorrow}&filter=%7B%22PriceArea%22:%22{area}%22%7D"'
            logger.info(f"Executing direct API call: {curl_cmd}")
            
            # Execute the curl command
            process = subprocess.run(curl_cmd, shell=True, capture_output=True, text=True)
            
            if process.returncode == 0:
                logger.info("Direct API call successful")
                
                # Try to parse the response as JSON
                try:
                    response_data = json.loads(process.stdout)
                    logger.info(f"Response contains {len(response_data.get('records', []))} records")
                    
                    # Log a sample of the data
                    if response_data.get('records'):
                        sample = response_data['records'][0]
                        logger.info(f"Sample data: {json.dumps(sample, indent=2)}")
                    
                    result["direct_api_success"] = True
                    result["status"] = "success"
                except json.JSONDecodeError:
                    logger.warning("Failed to parse response as JSON")
                    logger.info(f"Raw response: {process.stdout[:500]}...")
                    result["status"] = "error"
            else:
                logger.error(f"Direct API call failed: {process.stderr}")
                result["status"] = "error"
        
        elif api_name == "aemo":
            # Construct the curl command for tomorrow's data
            curl_cmd = f'curl "https://visualisations.aemo.com.au/aemo/apps/api/report/PREDISPATCH/PRICE/{area}"'
            logger.info(f"Executing direct API call: {curl_cmd}")
            
            # Execute the curl command
            process = subprocess.run(curl_cmd, shell=True, capture_output=True, text=True)
            
            if process.returncode == 0:
                logger.info("Direct API call successful")
                
                # Try to parse the response as JSON
                try:
                    response_data = json.loads(process.stdout)
                    logger.info(f"Response data: {json.dumps(response_data, indent=2)[:500]}...")
                    result["direct_api_success"] = True
                    result["status"] = "success"
                except json.JSONDecodeError:
                    logger.warning("Failed to parse response as JSON")
                    logger.info(f"Raw response: {process.stdout[:500]}...")
                    result["status"] = "error"
            else:
                logger.error(f"Direct API call failed: {process.stderr}")
                result["status"] = "error"
        
        elif api_name == "comed":
            # Construct the curl command
            curl_cmd = f'curl "https://hourlypricing.comed.com/api?type=5minutefeed"'
            logger.info(f"Executing direct API call: {curl_cmd}")
            
            # Execute the curl command
            process = subprocess.run(curl_cmd, shell=True, capture_output=True, text=True)
            
            if process.returncode == 0:
                logger.info("Direct API call successful")
                
                # Try to parse the response as JSON
                try:
                    response_data = json.loads(process.stdout)
                    logger.info(f"Response contains {len(response_data)} entries")
                    
                    # Log a sample of the data
                    if response_data:
                        sample = response_data[0]
                        logger.info(f"Sample data: {json.dumps(sample, indent=2)}")
                    
                    result["direct_api_success"] = True
                    result["status"] = "success"
                except json.JSONDecodeError:
                    logger.warning("Failed to parse response as JSON")
                    logger.info(f"Raw response: {process.stdout[:500]}...")
                    result["status"] = "error"
            else:
                logger.error(f"Direct API call failed: {process.stderr}")
                result["status"] = "error"
        
        elif api_name == "stromligning":
            # Construct the curl command
            curl_cmd = f'curl "https://stromligning.no/api/v1/prices?zone={area}"'
            logger.info(f"Executing direct API call: {curl_cmd}")
            
            # Execute the curl command
            process = subprocess.run(curl_cmd, shell=True, capture_output=True, text=True)
            
            if process.returncode == 0:
                logger.info("Direct API call successful")
                
                # Try to parse the response as JSON
                try:
                    response_data = json.loads(process.stdout)
                    logger.info(f"Response data: {json.dumps(response_data, indent=2)[:500]}...")
                    result["direct_api_success"] = True
                    result["status"] = "success"
                except json.JSONDecodeError:
                    logger.warning("Failed to parse response as JSON")
                    logger.info(f"Raw response: {process.stdout[:500]}...")
                    result["status"] = "error"
            else:
                logger.error(f"Direct API call failed: {process.stderr}")
                result["status"] = "error"
        
        else:
            logger.warning(f"Direct API call not implemented for {api_name}")
            result["status"] = "not_implemented"
    
    except Exception as e:
        logger.error(f"Error making direct API call for {api_name}: {e}")
        result["status"] = "error"
        result["error"] = str(e)
    
    return result

async def test_tomorrow_api_data(
    api_name: str,
    area: str,
    timeout: int,
    use_improved_adapter: bool = False,
    debug: bool = False
) -> Dict[str, Any]:
    """Test a specific API for tomorrow's data with cache testing.
    
    Args:
        api_name: Name of the API to test
        area: Area code to test
        timeout: Request timeout in seconds
        use_improved_adapter: Whether to use the improved adapter
        debug: Whether to enable debug mode (show direct API calls)
        
    Returns:
        Dictionary with test results
    """
    logger.info(f"Testing API: {api_name} for Area: {area}")
    
    # If debug mode is enabled, make a direct API call first to show the raw data
    if debug:
        await test_direct_api_call(api_name, area)
    
    # Create mock HASS instance and cache
    mock_hass = MockHass()
    price_cache = PriceCache(mock_hass, {})
    tz_service = TimezoneService(mock_hass, area, {})
    
    result = {
        "api": api_name,
        "area": area,
        "status": "unknown",
        "message": "",
        "has_today_data": False,
        "has_tomorrow_data": False,
        "tomorrow_valid": False,
        "today_hours": 0,
        "tomorrow_hours": 0,
        "cache_test": {},
        "timezone_info": {},
        "debug_info": {}
    }
    
    try:
        # Build config with API keys
        config = build_api_key_config(api_name, area)
        config["request_timeout"] = timeout
        
        # Fetch data from the API
        logger.debug(f"Fetching data from {api_name} for {area} with config: {config}")
        
        data = await fetch_day_ahead_prices(
            source_type=api_name,
            config=config,
            area=area,
            currency=Currency.EUR,
            hass=mock_hass
        )
        
        # Save raw data for analysis
        result["raw_data"] = data
        
        # Process the result
        if not data or not isinstance(data, dict):
            logger.warning(f"No valid data returned from {api_name} for {area}")
            result["status"] = "failure"
            result["message"] = "No valid data returned"
            return result
        
        # Check for tomorrow's data
        has_tomorrow_data = "tomorrow_hourly_prices" in data and data["tomorrow_hourly_prices"]
        result["has_tomorrow_data"] = has_tomorrow_data
        
        # Create adapter to validate tomorrow's data
        if use_improved_adapter:
            adapter = ImprovedElectricityPriceAdapter(mock_hass, [data], api_name, False)
        else:
            adapter = ElectricityPriceAdapter(mock_hass, [data], api_name, False)
            
        is_tomorrow_valid = adapter.is_tomorrow_valid()
        result["tomorrow_valid"] = is_tomorrow_valid
        
        if has_tomorrow_data:
            result["tomorrow_hours"] = len(data["tomorrow_hourly_prices"])
            logger.info(f"Source {api_name} for area {area} has tomorrow's data: {result['tomorrow_hours']} hours")
            logger.info(f"Tomorrow data validation: {is_tomorrow_valid}")
            
            # Log the actual hours available for tomorrow
            hours = sorted(data["tomorrow_hourly_prices"].keys())
            logger.debug(f"Tomorrow hours available: {hours}")
            result["debug_info"]["tomorrow_hours"] = hours
            
            # Check if tomorrow_hourly_prices contains ISO format dates
            has_dates = any("T" in hour for hour in hours)
            result["debug_info"]["tomorrow_hourly_prices_has_dates"] = has_dates
            if has_dates:
                logger.info(f"Tomorrow hourly prices contain ISO format dates")
                # Log some examples
                date_examples = [hour for hour in hours if "T" in hour][:3]
                logger.info(f"Date examples: {date_examples}")
                result["debug_info"]["tomorrow_date_examples"] = date_examples
            
            # Test cache functionality
            logger.info("Testing cache functionality for tomorrow data")
            
            # Store data in cache
            logger.info("Storing data in cache")
            now = datetime.now(timezone.utc)
            price_cache.store(data, area, api_name, now)
            
            # Inspect cache structure
            cache_structure = {}
            if hasattr(price_cache, "_cache"):
                today_str = now.strftime("%Y-%m-%d")
                tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
                
                # Check for today's cache entry
                if area in price_cache._cache and today_str in price_cache._cache[area]:
                    cache_structure["today_in_cache"] = True
                    
                    if api_name in price_cache._cache[area][today_str]:
                        source_data = price_cache._cache[area][today_str][api_name]
                        cache_structure["source_data_keys"] = list(source_data.keys())
                        
                        # Check for tomorrow data in today's cache
                        if "tomorrow_hourly_prices" in source_data:
                            tomorrow_keys = list(source_data["tomorrow_hourly_prices"].keys())
                            cache_structure["tomorrow_in_today_cache"] = True
                            cache_structure["tomorrow_hour_keys"] = tomorrow_keys
                            
                            # Check if tomorrow_hourly_prices contains ISO format dates
                            has_dates = any("T" in hour for hour in tomorrow_keys)
                            cache_structure["tomorrow_has_dates"] = has_dates
                            if has_dates:
                                date_examples = [hour for hour in tomorrow_keys if "T" in hour][:3]
                                cache_structure["tomorrow_date_examples"] = date_examples
                
                # Check for tomorrow's cache entry
                if area in price_cache._cache and tomorrow_str in price_cache._cache[area]:
                    cache_structure["tomorrow_cache_entry"] = True
                    
                    if api_name in price_cache._cache[area][tomorrow_str]:
                        tomorrow_data = price_cache._cache[area][tomorrow_str][api_name]
                        cache_structure["tomorrow_data_keys"] = list(tomorrow_data.keys())
                        
                        if "hourly_prices" in tomorrow_data:
                            hour_keys = list(tomorrow_data["hourly_prices"].keys())
                            cache_structure["tomorrow_hourly_keys"] = hour_keys
            
            # Add cache results to the output
            result["cache_test"] = {
                "cache_structure": cache_structure,
                "tomorrow_valid_from_cache": is_tomorrow_valid
            }
            
            # Add timezone information
            result["timezone_info"] = {
                "area_timezone": str(tz_service.area_timezone) if tz_service.area_timezone else None,
                "ha_timezone": str(mock_hass.config.time_zone) if hasattr(mock_hass, "config") and hasattr(mock_hass.config, "time_zone") else None,
                "is_dst_transition": tz_service.is_dst_transition_day(now)
            }
            
            # Set status based on validation
            if is_tomorrow_valid:
                result["status"] = "success"
                result["message"] = f"Successfully fetched tomorrow's data: {result['tomorrow_hours']} hours"
            else:
                result["status"] = "partial"
                result["message"] = f"Tomorrow's data incomplete: {result['tomorrow_hours']}/24 hours"
        else:
            logger.warning(f"Source {api_name} for area {area} does not have tomorrow's data")
            
            # Check if we have data for tomorrow in the hourly_prices
            tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date()
            tomorrow_hours = 0
            tomorrow_hour_keys = []
            
            for hour_key, price in data.get("hourly_prices", {}).items():
                # Try to parse the hour key to check if it's for tomorrow
                if "T" in hour_key:  # ISO format with date
                    try:
                        hour_dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                        if hour_dt.date() == tomorrow:
                            tomorrow_hours += 1
                            tomorrow_hour_keys.append(hour_key)
                    except (ValueError, TypeError):
                        pass
            
            if tomorrow_hours > 0:
                result["has_tomorrow_data_in_hourly"] = True
                result["tomorrow_hours_in_hourly"] = tomorrow_hours
                logger.info(f"Source {api_name} for area {area} has tomorrow's data in hourly_prices: {tomorrow_hours} hours")
                result["debug_info"]["tomorrow_in_hourly"] = tomorrow_hour_keys
                
                # Test cache functionality for tomorrow data in hourly_prices
                logger.info("Testing cache functionality for tomorrow data in hourly_prices")
                
                # Store data in cache
                logger.info("Storing data in cache")
                now = datetime.now(timezone.utc)
                price_cache.store(data, area, api_name, now)
                
                # Inspect cache structure
                cache_structure = {}
                if hasattr(price_cache, "_cache"):
                    today_str = now.strftime("%Y-%m-%d")
                    tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
                    
                    # Check for today's cache entry
                    if area in price_cache._cache and today_str in price_cache._cache[area]:
                        cache_structure["today_in_cache"] = True
                        
                        if api_name in price_cache._cache[area][today_str]:
                            source_data = price_cache._cache[area][today_str][api_name]
                            cache_structure["source_data_keys"] = list(source_data.keys())
                            
                            # Check for hourly_prices with tomorrow dates
                            if "hourly_prices" in source_data:
                                hour_keys = list(source_data["hourly_prices"].keys())
                                cache_structure["hourly_price_keys"] = hour_keys
                                
                                # Check if any hourly_prices keys contain ISO format dates for tomorrow
                                tomorrow_in_hourly = []
                                for hour_key in hour_keys:
                                    if "T" in hour_key:
                                        try:
                                            hour_dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                                            if hour_dt.date() == tomorrow:
                                                tomorrow_in_hourly.append(hour_key)
                                        except (ValueError, TypeError):
                                            pass
                                
                                if tomorrow_in_hourly:
                                    cache_structure["tomorrow_in_hourly_prices"] = True
                                    cache_structure["tomorrow_in_hourly_keys"] = tomorrow_in_hourly
                
                # Add cache results to the output
                result["cache_test"] = {
                    "cache_structure": cache_structure
                }
                
                # Check if the improved adapter can extract tomorrow's data
                if use_improved_adapter:
                    improved_adapter = ImprovedElectricityPriceAdapter(mock_hass, [data], api_name, False)
                    improved_tomorrow_valid = improved_adapter.is_tomorrow_valid()
                    result["improved_tomorrow_valid"] = improved_tomorrow_valid
                    result["improved_tomorrow_hours"] = len(improved_adapter.tomorrow_prices)
                    
                    # Test adapter with cached data
                    result["cache_test"]["improved_adapter_tomorrow_valid"] = improved_tomorrow_valid
                    
                    if improved_tomorrow_valid:
                        logger.info(f"Improved adapter successfully extracted tomorrow's data: {result['improved_tomorrow_hours']} hours")
                        result["status"] = "success_with_improved_adapter"
                        result["message"] = f"Successfully extracted tomorrow's data with improved adapter: {result['improved_tomorrow_hours']} hours"
                    else:
                        result["status"] = "partial"
                        result["message"] = f"Tomorrow's data in hourly_prices incomplete: {tomorrow_hours}/24 hours"
                else:
                    # Set status based on number of hours
                    if tomorrow_hours >= 20:  # Same validation as in ElectricityPriceAdapter.is_tomorrow_valid()
                        result["status"] = "success_needs_improved_adapter"
                        result["message"] = f"Tomorrow's data available in hourly_prices but needs improved adapter: {tomorrow_hours} hours"
                    else:
                        result["status"] = "partial"
                        result["message"] = f"Tomorrow's data in hourly_prices incomplete: {tomorrow_hours}/24 hours"
            else:
                result["status"] = "not_available"
                result["message"] = "No tomorrow's data available"
    
    except Exception as e:
        trace = traceback.format_exc()
        error_msg = f"Error during test: {str(e)}"
        logger.error(f"Error testing {api_name} for {area}: {error_msg}")
        logger.debug(trace)
        result["status"] = "error"
        result["message"] = error_msg
        result["debug_info"]["error"] = str(e)
        result["debug_info"]["traceback"] = trace
    
    return result


async def test_raw_api_data(api_name: str, area: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """Test raw API data using curl commands.
    
    Args:
        api_name: Name of the API to test
        area: Area code to test
        api_key: Optional API key for APIs that require it
        
    Returns:
        Dictionary with test results
    """
    result = {
        "api": api_name,
        "area": area,
        "status": "unknown",
        "message": "",
        "has_today_data": False,
        "has_tomorrow_data": False,
        "debug_info": {}
    }
    
    if api_name == "nordpool":
        # Test Nordpool API
        try:
            import subprocess
            
            # Nordpool API details
            base_url = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
            
            # Get today's and tomorrow's dates
            today = datetime.now().strftime("%Y-%m-%d")
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            
            # Delivery area is the same as region for SE1 and SE4
            delivery_area = area
            
            # We're only focusing on tomorrow's data in this test
            
            # Fetch tomorrow's data
            tomorrow_url = f"{base_url}?currency=EUR&date={tomorrow}&market=DayAhead&deliveryArea={delivery_area}"
            logger.info(f"Fetching tomorrow's data for {area} from Nordpool API...")
            logger.info(f"URL: {tomorrow_url}")
            
            tomorrow_result = subprocess.run(
                ["curl", "-s", tomorrow_url],
                capture_output=True,
                text=True
            )
            
            # Check if we got a valid response
            if tomorrow_result.returncode != 0:
                logger.error(f"Error fetching tomorrow's data: {tomorrow_result.stderr}")
                result["status"] = "error"
                result["message"] = f"Error fetching tomorrow's data: {tomorrow_result.stderr}"
                return result
            
            # Try to parse the response as JSON
            try:
                tomorrow_data = json.loads(tomorrow_result.stdout)
                logger.info(f"Successfully fetched tomorrow's data for {area} from Nordpool API")
                result["has_tomorrow_data"] = True
                result["debug_info"]["tomorrow_data"] = tomorrow_data
                
                # Check if we have multiAreaEntries
                if "multiAreaEntries" in tomorrow_data:
                    logger.info(f"Found {len(tomorrow_data['multiAreaEntries'])} entries in tomorrow's data")
                    
                    # Check if we have data for the specified region
                    for entry in tomorrow_data["multiAreaEntries"]:
                        if "entryPerArea" in entry and area in entry["entryPerArea"]:
                            logger.info(f"Found data for {area} in tomorrow's data")
                            logger.info(f"Example price: {entry['entryPerArea'][area]}")
                            result["debug_info"]["tomorrow_example_price"] = entry["entryPerArea"][area]
                            break
                else:
                    logger.warning("No multiAreaEntries found in tomorrow's data")
                
                # Set status based on results
                if result["has_tomorrow_data"]:
                    result["status"] = "success"
                    result["message"] = "Successfully fetched tomorrow's data"
                else:
                    result["status"] = "failure"
                    result["message"] = "Failed to fetch tomorrow's data"
            except json.JSONDecodeError:
                logger.warning("Failed to parse tomorrow's data as JSON")
                logger.warning(f"Response: {tomorrow_result.stdout[:200]}...")
                result["debug_info"]["tomorrow_raw_response"] = tomorrow_result.stdout[:1000]
                
                # Set status based on results
                result["status"] = "failure"
                result["message"] = "Failed to parse tomorrow's data"
        
        except Exception as e:
            trace = traceback.format_exc()
            error_msg = f"Error during test: {str(e)}"
            logger.error(error_msg)
            logger.debug(trace)
            result["status"] = "error"
            result["message"] = error_msg
            result["debug_info"]["error"] = str(e)
            result["debug_info"]["traceback"] = trace
    
    elif api_name == "entsoe":
        # Test ENTSOE API
        if not api_key:
            result["status"] = "error"
            result["message"] = "ENTSOE API key is required"
            return result
            
        try:
            import subprocess
            
            # ENTSOE API details
            base_url = "https://transparency.entsoe.eu/api"
            
            # Get date ranges for today and tomorrow
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            tomorrow_start = today_end
            tomorrow_end = tomorrow_start + timedelta(days=1)
            
            # Format dates for ENTSOE API (YYYYMMDDHHMM format)
            today_start_str = today_start.strftime("%Y%m%d%H%M")
            today_end_str = today_end.strftime("%Y%m%d%H%M")
            tomorrow_start_str = tomorrow_start.strftime("%Y%m%d%H%M")
            tomorrow_end_str = tomorrow_end.strftime("%Y%m%d%H%M")
            
            # ENTSOE area code is the EIC code, not the region code
            entsoe_area_mapping = {
                "SE1": "10Y1001A1001A44P",
                "SE4": "10Y1001A1001A47J"
            }
            entsoe_area = entsoe_area_mapping.get(area, area)
            logger.info(f"Using ENTSOE area code: {entsoe_area} for region {area}")
            
            # Try different document types
            document_types = ["A44", "A62", "A65"]
            
            # We're only focusing on tomorrow's data in this test
            
            # Fetch tomorrow's data
            logger.info(f"Fetching tomorrow's data for {area} from ENTSOE API...")
            
            tomorrow_success = False
            for doc_type in document_types:
                tomorrow_url = (
                    f"{base_url}?securityToken={api_key}&documentType={doc_type}"
                    f"&in_Domain={entsoe_area}&out_Domain={entsoe_area}"
                    f"&periodStart={tomorrow_start_str}&periodEnd={tomorrow_end_str}"
                )
                logger.info(f"Trying document type {doc_type}...")
                logger.info(f"URL: {tomorrow_url.replace(api_key, 'API_KEY_HIDDEN')}")
                
                tomorrow_result = subprocess.run(
                    ["curl", "-s", "-H", "User-Agent: Mozilla/5.0", 
                     "-H", "Accept: application/xml", 
                     "-H", "Content-Type: application/xml", 
                     tomorrow_url],
                    capture_output=True,
                    text=True
                )
                
                # Check if we got a valid response
                if tomorrow_result.returncode != 0:
                    logger.error(f"Error fetching tomorrow's data with document type {doc_type}: {tomorrow_result.stderr}")
                    continue
                
                # Check if we got a valid XML response
                if "<Publication_MarketDocument" in tomorrow_result.stdout:
                    logger.info(f"Successfully fetched tomorrow's data for {area} from ENTSOE API with document type {doc_type}")
                    
                    # Check if we have TimeSeries
                    if "<TimeSeries>" in tomorrow_result.stdout:
                        logger.info("Found TimeSeries in tomorrow's data")
                        
                        # Check if we have price points
                        if "<Point>" in tomorrow_result.stdout:
                            logger.info("Found price points in tomorrow's data")
                            
                            # Count the number of price points
                            point_count = tomorrow_result.stdout.count("<Point>")
                            logger.info(f"Found {point_count} price points in tomorrow's data")
                            
                            result["has_tomorrow_data"] = True
                            result["debug_info"]["tomorrow_point_count"] = point_count
                            result["debug_info"]["tomorrow_document_type"] = doc_type
                            result["debug_info"]["tomorrow_raw_response"] = tomorrow_result.stdout[:1000]
                            
                            tomorrow_success = True
                            break
                        else:
                            logger.warning("No price points found in tomorrow's data")
                    else:
                        logger.warning("No TimeSeries found in tomorrow's data")
                elif "No matching data found" in tomorrow_result.stdout:
                    logger.warning(f"No matching data found for tomorrow with document type {doc_type}")
                else:
                    logger.warning(f"Unexpected response for tomorrow's data with document type {doc_type}")
                    logger.warning(f"Response: {tomorrow_result.stdout[:200]}...")
            
            # Set status based on results
            if tomorrow_success:
                result["status"] = "success"
                result["message"] = "Successfully fetched tomorrow's data"
            else:
                result["status"] = "failure"
                result["message"] = "Failed to fetch tomorrow's data"
        
        except Exception as e:
            trace = traceback.format_exc()
            error_msg = f"Error during test: {str(e)}"
            logger.error(error_msg)
            logger.debug(trace)
            result["status"] = "error"
            result["message"] = error_msg
            result["debug_info"]["error"] = str(e)
            result["debug_info"]["traceback"] = trace
    
    else:
        result["status"] = "not_implemented"
        result["message"] = f"Raw API testing not implemented for {api_name}"
    
    return result


async def compare_adapters_with_api_data(
    api_name: str,
    area: str,
    timeout: int
) -> Dict[str, Any]:
    """Compare original and improved adapters with real API data.
    
    Args:
        api_name: Name of the API to test
        area: Area code to test
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary with comparison results
    """
    # Test with original adapter
    original_result = await test_tomorrow_api_data(api_name, area, timeout, use_improved_adapter=False)
    
    # Test with improved adapter
    improved_result = await test_tomorrow_api_data(api_name, area, timeout, use_improved_adapter=True)
    
    # Compare results
    comparison = {
        "api": api_name,
        "area": area,
        "original": {
            "status": original_result["status"],
            "has_today_data": original_result["has_today_data"],
            "has_tomorrow_data": original_result["has_tomorrow_data"],
            "tomorrow_valid": original_result["tomorrow_valid"],
            "today_hours": original_result["today_hours"],
            "tomorrow_hours": original_result["tomorrow_hours"]
        },
        "improved": {
            "status": improved_result["status"],
            "has_today_data": improved_result["has_today_data"],
            "has_tomorrow_data": improved_result["has_tomorrow_data"],
            "tomorrow_valid": improved_result["tomorrow_valid"],
            "today_hours": improved_result["today_hours"],
            "tomorrow_hours": improved_result["tomorrow_hours"]
        },
        "comparison": {
            "improved_finds_more_tomorrow_data": (
                improved_result["has_tomorrow_data"] and not original_result["has_tomorrow_data"]
            ) or (
                improved_result["tomorrow_valid"] and not original_result["tomorrow_valid"]
            ),
            "improved_finds_same_tomorrow_data": (
                improved_result["has_tomorrow_data"] == original_result["has_tomorrow_data"]
            ) and (
                improved_result["tomorrow_valid"] == original_result["tomorrow_valid"]
            ),
            "original_tomorrow_hours": original_result["tomorrow_hours"],
            "improved_tomorrow_hours": improved_result["tomorrow_hours"]
        }
    }
    
    return comparison
