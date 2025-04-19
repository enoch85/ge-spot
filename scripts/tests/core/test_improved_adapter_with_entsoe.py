#!/usr/bin/env python3
"""Test script for verifying the ElectricityPriceAdapter's handling of ENTSOE data.

This script tests the ElectricityPriceAdapter's ability to correctly extract tomorrow's data
from the ENTSOE API response, which contains ISO format dates.
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

def test_enhanced_adapter(xml_data: str, area: str = "SE4"):
    """Test the enhanced ElectricityPriceAdapter with ENTSO-E data.
    
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
    
    # Create adapter with enhanced functionality
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
        
        # Test with enhanced adapter
        logger.info("\n--- Testing with enhanced adapter ---\n")
        enhanced_result = test_enhanced_adapter(xml_data)
        
        # Compare results
        logger.info("\n--- Comparison ---\n")
        logger.info(f"Original adapter: Tomorrow valid: {original_result['is_tomorrow_valid']}, Tomorrow hours: {original_result['tomorrow_hours']}")
        logger.info(f"Enhanced adapter: Tomorrow valid: {enhanced_result['is_tomorrow_valid']}, Tomorrow hours: {enhanced_result['tomorrow_hours']}")
        
        if enhanced_result['is_tomorrow_valid'] and not original_result['is_tomorrow_valid']:
            logger.info("RESULT: Enhanced adapter successfully extracted tomorrow's data, but original adapter did not.")
        elif original_result['is_tomorrow_valid'] and enhanced_result['is_tomorrow_valid']:
            logger.info("RESULT: Both adapters successfully extracted tomorrow's data.")
        elif not original_result['is_tomorrow_valid'] and not enhanced_result['is_tomorrow_valid']:
            logger.info("RESULT: Neither adapter could extract tomorrow's data.")
        else:
            logger.info("RESULT: Original adapter extracted tomorrow's data, but enhanced adapter did not.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
