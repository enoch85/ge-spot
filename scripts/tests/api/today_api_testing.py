"""Today API testing functionality for GE-Spot integration."""
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

logger = logging.getLogger(__name__)

async def test_today_api_data(
    api_name: str,
    area: str,
    timeout: int
) -> Dict[str, Any]:
    """Test a specific API for today's data with cache testing.
    
    Args:
        api_name: Name of the API to test
        area: Area code to test
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary with test results
    """
    logger.info(f"Testing API: {api_name} for Area: {area}")
    
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
        "today_hours": 0,
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
            
            # Test cache functionality
            logger.info("Testing cache functionality")
            
            # Store data in cache
            logger.info("Storing data in cache")
            now = datetime.now(timezone.utc)
            price_cache.store(data, area, api_name, now)
            
            # Get current hour key
            current_hour_key = tz_service.get_current_hour_key()
            logger.info(f"Current hour key from TimezoneService: {current_hour_key}")
            
            # Check if current hour is in cache
            has_current_hour = price_cache.has_current_hour_price(area)
            logger.info(f"Cache has current hour price: {has_current_hour}")
            
            # Get current hour price from cache
            current_hour_price = price_cache.get_current_hour_price(area)
            if current_hour_price:
                logger.info(f"Current hour price from cache: {current_hour_price}")
                logger.info(f"Cache hour key: {current_hour_price.get('hour_str')}")
            else:
                logger.warning(f"Failed to retrieve current hour price from cache")
            
            # Inspect cache structure
            cache_structure = {}
            if hasattr(price_cache, "_cache"):
                today_str = now.strftime("%Y-%m-%d")
                if area in price_cache._cache:
                    cache_structure["area_in_cache"] = True
                    if today_str in price_cache._cache[area]:
                        cache_structure["today_in_cache"] = True
                        sources = list(price_cache._cache[area][today_str].keys())
                        cache_structure["sources"] = sources
                        
                        if api_name in price_cache._cache[area][today_str]:
                            source_data = price_cache._cache[area][today_str][api_name]
                            cache_structure["source_data_keys"] = list(source_data.keys())
                            
                            if "hourly_prices" in source_data:
                                hour_keys = list(source_data["hourly_prices"].keys())
                                cache_structure["hourly_price_keys"] = hour_keys
                                
                                # Check if current hour key is in hourly_prices
                                cache_structure["current_hour_in_hourly_prices"] = current_hour_key in source_data["hourly_prices"]
                                
                                # Get timezone info from cache
                                cache_structure["api_timezone"] = source_data.get("api_timezone")
                                cache_structure["ha_timezone"] = source_data.get("ha_timezone")
                                cache_structure["area_timezone"] = source_data.get("area_timezone")
                                cache_structure["stored_in_timezone"] = source_data.get("stored_in_timezone")
            
            # Add cache results to the output
            result["cache_test"] = {
                "has_current_hour": has_current_hour,
                "current_hour_key": current_hour_key,
                "retrieved_hour_price": current_hour_price is not None,
                "cache_structure": cache_structure
            }
            
            # Add timezone information
            result["timezone_info"] = {
                "current_hour_key": current_hour_key,
                "area_timezone": str(tz_service.area_timezone) if tz_service.area_timezone else None,
                "ha_timezone": str(mock_hass.config.time_zone) if hasattr(mock_hass, "config") and hasattr(mock_hass.config, "time_zone") else None,
                "is_dst_transition": tz_service.is_dst_transition_day(now)
            }
            
            # Set status based on cache test
            if has_current_hour and current_hour_price:
                result["status"] = "success"
                result["message"] = f"Successfully fetched today's data and verified cache: {result['today_hours']} hours"
            else:
                result["status"] = "partial"
                result["message"] = f"Successfully fetched today's data but cache verification failed: {result['today_hours']} hours"
        else:
            logger.warning(f"Source {api_name} for area {area} does not have today's data")
            result["status"] = "not_available"
            result["message"] = "No today's data available"
    
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
