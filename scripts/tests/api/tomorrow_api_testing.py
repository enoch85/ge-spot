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

from ..mocks.hass import MockHass
from ..utils.general import build_api_key_config
from ..core.adapter_testing import ImprovedElectricityPriceAdapter

logger = logging.getLogger(__name__)

async def test_tomorrow_api_data(
    api_name: str,
    area: str,
    timeout: int,
    use_improved_adapter: bool = False
) -> Dict[str, Any]:
    """Test a specific API for tomorrow's data.
    
    Args:
        api_name: Name of the API to test
        area: Area code to test
        timeout: Request timeout in seconds
        use_improved_adapter: Whether to use the improved adapter
        
    Returns:
        Dictionary with test results
    """
    logger.info(f"Testing API: {api_name} for Area: {area}")
    
    # Create mock HASS instance
    mock_hass = MockHass()
    
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
        
        # Check for today's data
        has_today_data = "hourly_prices" in data and data["hourly_prices"]
        result["has_today_data"] = has_today_data
        
        if has_today_data:
            result["today_hours"] = len(data["hourly_prices"])
            logger.info(f"Source {api_name} for area {area} has today's data: {result['today_hours']} hours")
            
            # Log the actual hours available for today
            hours = sorted(data["hourly_prices"].keys())
            logger.debug(f"Today hours available: {hours}")
            result["debug_info"]["today_hours"] = hours
            
            # Check if hourly_prices contains ISO format dates
            has_dates = any("T" in hour for hour in hours)
            result["debug_info"]["hourly_prices_has_dates"] = has_dates
            if has_dates:
                logger.info(f"Hourly prices contain ISO format dates")
                # Log some examples
                date_examples = [hour for hour in hours if "T" in hour][:3]
                logger.info(f"Date examples: {date_examples}")
                result["debug_info"]["date_examples"] = date_examples
        
        # Check for tomorrow's data
        has_tomorrow_data = "tomorrow_hourly_prices" in data and data["tomorrow_hourly_prices"]
        result["has_tomorrow_data"] = has_tomorrow_data
        
        # Create adapter to validate tomorrow's data
        if use_improved_adapter:
            adapter = ImprovedElectricityPriceAdapter(mock_hass, [data], False)
        else:
            adapter = ElectricityPriceAdapter(mock_hass, [data], False)
            
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
                
                # Check if the improved adapter can extract tomorrow's data
                if use_improved_adapter:
                    improved_adapter = ImprovedElectricityPriceAdapter(mock_hass, [data], False)
                    improved_tomorrow_valid = improved_adapter.is_tomorrow_valid()
                    result["improved_tomorrow_valid"] = improved_tomorrow_valid
                    result["improved_tomorrow_hours"] = len(improved_adapter.tomorrow_prices)
                    
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
            
            # Fetch today's data
            today_url = f"{base_url}?currency=EUR&date={today}&market=DayAhead&deliveryArea={delivery_area}"
            logger.info(f"Fetching today's data for {area} from Nordpool API...")
            logger.info(f"URL: {today_url}")
            
            today_result = subprocess.run(
                ["curl", "-s", today_url],
                capture_output=True,
                text=True
            )
            
            # Check if we got a valid response
            if today_result.returncode != 0:
                logger.error(f"Error fetching today's data: {today_result.stderr}")
                result["status"] = "error"
                result["message"] = f"Error fetching today's data: {today_result.stderr}"
                return result
            
            # Try to parse the response as JSON
            try:
                today_data = json.loads(today_result.stdout)
                logger.info(f"Successfully fetched today's data for {area} from Nordpool API")
                result["has_today_data"] = True
                result["debug_info"]["today_data"] = today_data
                
                # Check if we have multiAreaEntries
                if "multiAreaEntries" in today_data:
                    logger.info(f"Found {len(today_data['multiAreaEntries'])} entries in today's data")
                    
                    # Check if we have data for the specified region
                    for entry in today_data["multiAreaEntries"]:
                        if "entryPerArea" in entry and area in entry["entryPerArea"]:
                            logger.info(f"Found data for {area} in today's data")
                            logger.info(f"Example price: {entry['entryPerArea'][area]}")
                            result["debug_info"]["today_example_price"] = entry["entryPerArea"][area]
                            break
                else:
                    logger.warning("No multiAreaEntries found in today's data")
            except json.JSONDecodeError:
                logger.warning("Failed to parse today's data as JSON")
                logger.warning(f"Response: {today_result.stdout[:200]}...")
                result["debug_info"]["today_raw_response"] = today_result.stdout[:1000]
            
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
                result["status"] = "partial"
                result["message"] = f"Successfully fetched today's data but error fetching tomorrow's data: {tomorrow_result.stderr}"
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
                if result["has_today_data"] and result["has_tomorrow_data"]:
                    result["status"] = "success"
                    result["message"] = "Successfully fetched both today's and tomorrow's data"
                elif result["has_today_data"]:
                    result["status"] = "partial"
                    result["message"] = "Successfully fetched today's data but no tomorrow's data"
                else:
                    result["status"] = "failure"
                    result["message"] = "Failed to fetch both today's and tomorrow's data"
            except json.JSONDecodeError:
                logger.warning("Failed to parse tomorrow's data as JSON")
                logger.warning(f"Response: {tomorrow_result.stdout[:200]}...")
                result["debug_info"]["tomorrow_raw_response"] = tomorrow_result.stdout[:1000]
                
                # Set status based on results
                if result["has_today_data"]:
                    result["status"] = "partial"
                    result["message"] = "Successfully fetched today's data but failed to parse tomorrow's data"
                else:
                    result["status"] = "failure"
                    result["message"] = "Failed to parse both today's and tomorrow's data"
        
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
            
            # Fetch today's data
            logger.info(f"Fetching today's data for {area} from ENTSOE API...")
            
            today_success = False
            for doc_type in document_types:
                today_url = (
                    f"{base_url}?securityToken={api_key}&documentType={doc_type}"
                    f"&in_Domain={entsoe_area}&out_Domain={entsoe_area}"
                    f"&periodStart={today_start_str}&periodEnd={today_end_str}"
                )
                logger.info(f"Trying document type {doc_type}...")
                logger.info(f"URL: {today_url.replace(api_key, 'API_KEY_HIDDEN')}")
                
                today_result = subprocess.run(
                    ["curl", "-s", "-H", "User-Agent: Mozilla/5.0", 
                     "-H", "Accept: application/xml", 
                     "-H", "Content-Type: application/xml", 
                     today_url],
                    capture_output=True,
                    text=True
                )
                
                # Check if we got a valid response
                if today_result.returncode != 0:
                    logger.error(f"Error fetching today's data with document type {doc_type}: {today_result.stderr}")
                    continue
                
                # Check if we got a valid XML response
                if "<Publication_MarketDocument" in today_result.stdout:
                    logger.info(f"Successfully fetched today's data for {area} from ENTSOE API with document type {doc_type}")
                    
                    # Check if we have TimeSeries
                    if "<TimeSeries>" in today_result.stdout:
                        logger.info("Found TimeSeries in today's data")
                        
                        # Check if we have price points
                        if "<Point>" in today_result.stdout:
                            logger.info("Found price points in today's data")
                            
                            # Count the number of price points
                            point_count = today_result.stdout.count("<Point>")
                            logger.info(f"Found {point_count} price points in today's data")
                            
                            result["has_today_data"] = True
                            result["debug_info"]["today_point_count"] = point_count
                            result["debug_info"]["today_document_type"] = doc_type
                            result["debug_info"]["today_raw_response"] = today_result.stdout[:1000]
                            
                            today_success = True
                            break
                        else:
                            logger.warning("No price points found in today's data")
                    else:
                        logger.warning("No TimeSeries found in today's data")
                elif "No matching data found" in today_result.stdout:
                    logger.warning(f"No matching data found for today with document type {doc_type}")
                else:
                    logger.warning(f"Unexpected response for today's data with document type {doc_type}")
                    logger.warning(f"Response: {today_result.stdout[:200]}...")
            
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
            if today_success and tomorrow_success:
                result["status"] = "success"
                result["message"] = "Successfully fetched both today's and tomorrow's data"
            elif today_success:
                result["status"] = "partial"
                result["message"] = "Successfully fetched today's data but not tomorrow's data"
            elif tomorrow_success:
                result["status"] = "partial"
                result["message"] = "Successfully fetched tomorrow's data but not today's data"
            else:
                result["status"] = "failure"
                result["message"] = "Failed to fetch both today's and tomorrow's data"
        
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
