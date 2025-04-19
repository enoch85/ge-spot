#!/usr/bin/env python3
"""Test script for verifying the ElectricityPriceAdapter's handling of ENTSO-E data.

This script tests the ElectricityPriceAdapter's ability to correctly extract tomorrow's data
from the ENTSO-E API response, which contains ISO format dates.
"""
import sys
import os
import logging
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path so we can import the custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Import components from the integration
try:
    from custom_components.ge_spot.price.adapter import ElectricityPriceAdapter
    from custom_components.ge_spot.api.parsers.entsoe_parser import EntsoeParser
    from scripts.tests.mocks.hass import MockHass
    IMPORTS_SUCCESSFUL = True
except ImportError as e:
    logger.error(f"Failed to import from custom_components: {e}")
    IMPORTS_SUCCESSFUL = False
    sys.exit(1)

class ImprovedElectricityPriceAdapter(ElectricityPriceAdapter):
    """Improved adapter for electricity price data that can handle ISO format dates."""

    def _extract_hourly_prices(self) -> Dict[str, float]:
        """Extract hourly prices from raw data."""
        hourly_prices = {}
        
        # Track tomorrow's data found in hourly_prices
        tomorrow_in_hourly = {}
        from datetime import datetime, timedelta
        from homeassistant.util import dt as dt_util
        today = dt_util.now().date()
        tomorrow = today + timedelta(days=1)

        for item in self.raw_data:
            if not isinstance(item, dict):
                continue

            if "hourly_prices" in item and isinstance(item["hourly_prices"], dict):
                # Store formatted hour -> price mapping
                logger.debug(f"Found hourly_prices in raw data: {len(item['hourly_prices'])} entries")
                for hour_str, price in item["hourly_prices"].items():
                    # Check if this is an ISO format date
                    if "T" in hour_str:
                        try:
                            dt = datetime.fromisoformat(hour_str.replace('Z', '+00:00'))
                            hour = dt.hour
                            hour_key = f"{hour:02d}:00"
                            
                            # Check if this is tomorrow's data
                            if dt.date() == tomorrow:
                                # This is tomorrow's data, store it separately
                                logger.info(f"Found tomorrow's data in hourly_prices: {hour_str} -> {hour_key}")
                                tomorrow_in_hourly[hour_key] = price
                                continue  # Skip adding to hourly_prices
                            elif dt.date() == today:
                                # This is today's data, add it to hourly_prices
                                hourly_prices[hour_key] = price
                            else:
                                # This is data for another day, skip it
                                logger.debug(f"Skipping data for another day: {hour_str}")
                                continue
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Failed to parse ISO date: {hour_str} - {e}")
                            # Try simple format as fallback
                            hour = self._parse_hour_from_string(hour_str)
                            if hour is not None:
                                hour_key = f"{hour:02d}:00"
                                hourly_prices[hour_key] = price
                    else:
                        # Simple format (HH:00)
                        hour = self._parse_hour_from_string(hour_str)
                        if hour is not None:
                            hour_key = f"{hour:02d}:00"
                            hourly_prices[hour_key] = price

        # If we found tomorrow's data in hourly_prices, add it to tomorrow_hourly_prices
        if tomorrow_in_hourly:
            logger.info(f"Found {len(tomorrow_in_hourly)} hours of tomorrow's data in hourly_prices")
            for item in self.raw_data:
                if isinstance(item, dict):
                    if "tomorrow_hourly_prices" not in item:
                        item["tomorrow_hourly_prices"] = {}
                    # Add tomorrow's data to tomorrow_hourly_prices
                    item["tomorrow_hourly_prices"].update(tomorrow_in_hourly)
                    break

        logger.debug(f"Extracted {len(hourly_prices)} hourly prices: {sorted(hourly_prices.keys())}")
        return hourly_prices

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

def test_original_adapter(xml_data: str, area: str = "SE4"):
    """Test the original ElectricityPriceAdapter with ENTSO-E data.
    
    Args:
        xml_data: ENTSO-E XML response
        area: Area code
        
    Returns:
        Test results
    """
    # Create mock HASS instance
    hass = MockHass()
    
    # Parse the XML data using EntsoeParser
    parser = EntsoeParser()
    hourly_prices = parser.parse_hourly_prices(xml_data, area)
    
    # Print some of the hourly prices to see the format
    logger.info(f"Sample hourly prices from parser: {list(hourly_prices.items())[:5]}")
    
    # Create raw data structure
    raw_data = {
        "hourly_prices": hourly_prices,
        "source": "entsoe",
        "currency": "EUR",
        "area": area
    }
    
    # Create adapter
    adapter = ElectricityPriceAdapter(hass, [raw_data], False)
    
    # Check if adapter correctly extracts tomorrow's data
    tomorrow_prices = adapter.tomorrow_prices
    
    # Log the keys to see what format they are in
    logger.info(f"Hourly price keys: {list(adapter.hourly_prices.keys())[:5]}")
    logger.info(f"Tomorrow price keys: {list(tomorrow_prices.keys())[:5] if tomorrow_prices else 'None'}")
    
    # Check if tomorrow's data is correctly identified
    is_tomorrow_valid = adapter.is_tomorrow_valid()
    
    # Log the results
    logger.info(f"Tomorrow data validation: {is_tomorrow_valid}")
    logger.info(f"Today hours: {len(adapter.hourly_prices)}, Tomorrow hours: {len(tomorrow_prices)}")
    
    return {
        "is_tomorrow_valid": is_tomorrow_valid,
        "today_hours": len(adapter.hourly_prices),
        "tomorrow_hours": len(tomorrow_prices),
        "hourly_prices": adapter.hourly_prices,
        "tomorrow_prices": tomorrow_prices
    }

def test_improved_adapter(xml_data: str, area: str = "SE4"):
    """Test the improved ElectricityPriceAdapter with ENTSO-E data.
    
    Args:
        xml_data: ENTSO-E XML response
        area: Area code
        
    Returns:
        Test results
    """
    # Create mock HASS instance
    hass = MockHass()
    
    # Parse the XML data using EntsoeParser
    parser = EntsoeParser()
    hourly_prices = parser.parse_hourly_prices(xml_data, area)
    
    # Print some of the hourly prices to see the format
    logger.info(f"Sample hourly prices from parser: {list(hourly_prices.items())[:5]}")
    
    # Create raw data structure
    raw_data = {
        "hourly_prices": hourly_prices,
        "source": "entsoe",
        "currency": "EUR",
        "area": area
    }
    
    # Create improved adapter
    adapter = ImprovedElectricityPriceAdapter(hass, [raw_data], False)
    
    # Check if adapter correctly extracts tomorrow's data
    tomorrow_prices = adapter.tomorrow_prices
    
    # Log the keys to see what format they are in
    logger.info(f"Hourly price keys: {list(adapter.hourly_prices.keys())[:5]}")
    logger.info(f"Tomorrow price keys: {list(tomorrow_prices.keys())[:5] if tomorrow_prices else 'None'}")
    
    # Check if tomorrow's data is correctly identified
    is_tomorrow_valid = adapter.is_tomorrow_valid()
    
    # Log the results
    logger.info(f"Tomorrow data validation: {is_tomorrow_valid}")
    logger.info(f"Today hours: {len(adapter.hourly_prices)}, Tomorrow hours: {len(tomorrow_prices)}")
    
    return {
        "is_tomorrow_valid": is_tomorrow_valid,
        "today_hours": len(adapter.hourly_prices),
        "tomorrow_hours": len(tomorrow_prices),
        "hourly_prices": adapter.hourly_prices,
        "tomorrow_prices": tomorrow_prices
    }

def main():
    """Run the test."""
    # Path to the ENTSO-E API response files
    entsoe_response_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "entsoe_responses")
    
    # Find all ENTSO-E response files
    if not os.path.exists(entsoe_response_dir):
        logger.error(f"ENTSO-E response directory not found: {entsoe_response_dir}")
        logger.error("Run test_entsoe_tomorrow_data.py first to generate response files.")
        return 1
        
    response_files = [f for f in os.listdir(entsoe_response_dir) if f.startswith("entsoe_") and f.endswith(".xml")]
    if not response_files:
        logger.error("No ENTSO-E response files found. Run test_entsoe_tomorrow_data.py first.")
        return 1
    
    # Test with each response file
    for filename in response_files:
        logger.info(f"\n\n=== Testing with ENTSO-E response file: {filename} ===\n")
        
        # Load ENTSO-E API response
        file_path = os.path.join(entsoe_response_dir, filename)
        xml_data = load_entsoe_response(file_path)
        if not xml_data:
            logger.warning(f"Could not load ENTSO-E response file: {filename}")
            continue
        
        # Test with original adapter
        logger.info("\n--- Testing with original adapter ---\n")
        original_result = test_original_adapter(xml_data)
        
        # Test with improved adapter
        logger.info("\n--- Testing with improved adapter ---\n")
        improved_result = test_improved_adapter(xml_data)
        
        # Compare results
        logger.info("\n--- Comparison ---\n")
        logger.info(f"Original adapter: Tomorrow valid: {original_result['is_tomorrow_valid']}, Tomorrow hours: {original_result['tomorrow_hours']}")
        logger.info(f"Improved adapter: Tomorrow valid: {improved_result['is_tomorrow_valid']}, Tomorrow hours: {improved_result['tomorrow_hours']}")
        
        if improved_result['is_tomorrow_valid'] and not original_result['is_tomorrow_valid']:
            logger.info("RESULT: Improved adapter successfully extracted tomorrow's data, but original adapter did not.")
        elif original_result['is_tomorrow_valid'] and improved_result['is_tomorrow_valid']:
            logger.info("RESULT: Both adapters successfully extracted tomorrow's data.")
        elif not original_result['is_tomorrow_valid'] and not improved_result['is_tomorrow_valid']:
            logger.info("RESULT: Neither adapter could extract tomorrow's data.")
        else:
            logger.info("RESULT: Original adapter extracted tomorrow's data, but improved adapter did not.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
