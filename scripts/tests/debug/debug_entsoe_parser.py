#!/usr/bin/env python3
"""Debug script for ENTSOE parser issues."""
import sys
import os
import logging
from datetime import datetime, timedelta, timezone

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path so we can import the custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# Import components from the integration
try:
    from custom_components.ge_spot.api.parsers.entsoe_parser import EntsoeParser
    from custom_components.ge_spot.timezone.timezone_utils import normalize_hour_value, format_hour_key
    IMPORTS_SUCCESSFUL = True
except ImportError as e:
    logger.error(f"Failed to import from custom_components: {e}")
    IMPORTS_SUCCESSFUL = False
    sys.exit(1)

def test_normalize_hour_value():
    """Test the normalize_hour_value function."""
    # Test with valid hour values
    test_cases = [
        (0, "2025-04-19"),  # Midnight
        (12, "2025-04-19"),  # Noon
        (23, "2025-04-19"),  # 11 PM
        (24, "2025-04-19"),  # Midnight next day
        (25, "2025-04-19"),  # 1 AM next day
    ]
    
    for hour, date_str in test_cases:
        try:
            # Parse date
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            # Call normalize_hour_value
            normalized_hour, adjusted_date = normalize_hour_value(hour, date_obj)
            
            # Log result
            logger.info(f"Hour {hour} on {date_str} -> {normalized_hour} on {adjusted_date}")
        except Exception as e:
            logger.error(f"Error normalizing hour {hour} on {date_str}: {e}")

def test_format_hour_key():
    """Test the format_hour_key function."""
    # Test with various datetime objects
    test_cases = [
        datetime(2025, 4, 19, 0, 0, 0),  # Midnight
        datetime(2025, 4, 19, 12, 0, 0),  # Noon
        datetime(2025, 4, 19, 23, 0, 0),  # 11 PM
    ]
    
    for dt in test_cases:
        try:
            # Call format_hour_key
            hour_key = format_hour_key(dt)
            
            # Log result
            logger.info(f"Datetime {dt} -> hour key {hour_key}")
        except Exception as e:
            logger.error(f"Error formatting hour key for {dt}: {e}")

def test_parse_xml():
    """Test parsing XML with the ENTSOE parser."""
    # Path to the ENTSOE API response files
    entsoe_response_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "entsoe_responses")
    
    # Find all ENTSOE response files
    if not os.path.exists(entsoe_response_dir):
        logger.error(f"ENTSOE response directory not found: {entsoe_response_dir}")
        return
    
    response_files = [f for f in os.listdir(entsoe_response_dir) if f.startswith("entsoe_") and f.endswith(".xml")]
    if not response_files:
        logger.error("No ENTSOE response files found.")
        return
    
    # Test with the first response file
    filename = response_files[0]
    file_path = os.path.join(entsoe_response_dir, filename)
    
    try:
        # Load XML data
        with open(file_path, "r") as f:
            xml_data = f.read()
        
        # Create parser
        parser = EntsoeParser()
        
        # Parse XML
        result = parser._parse_xml(xml_data)
        
        # Log result
        logger.info(f"Successfully parsed XML: {filename}")
        logger.info(f"Found {len(result['hourly_prices'])} hourly prices")
        logger.info(f"Sample hourly prices: {list(result['hourly_prices'].items())[:5]}")
    except Exception as e:
        logger.error(f"Error parsing XML {filename}: {e}")

def test_parse_hourly_prices():
    """Test parsing hourly prices with the ENTSOE parser."""
    # Path to the ENTSOE API response files
    entsoe_response_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "entsoe_responses")
    
    # Find all ENTSOE response files
    if not os.path.exists(entsoe_response_dir):
        logger.error(f"ENTSOE response directory not found: {entsoe_response_dir}")
        return
    
    response_files = [f for f in os.listdir(entsoe_response_dir) if f.startswith("entsoe_") and f.endswith(".xml")]
    if not response_files:
        logger.error("No ENTSOE response files found.")
        return
    
    # Test with the first response file
    filename = response_files[0]
    file_path = os.path.join(entsoe_response_dir, filename)
    
    try:
        # Load XML data
        with open(file_path, "r") as f:
            xml_data = f.read()
        
        # Create parser
        parser = EntsoeParser()
        
        # Parse hourly prices
        hourly_prices = parser.parse_hourly_prices(xml_data, "SE4")
        
        # Log result
        logger.info(f"Successfully parsed hourly prices from {filename}")
        logger.info(f"Found {len(hourly_prices)} hourly prices")
        logger.info(f"Sample hourly prices: {list(hourly_prices.items())[:5]}")
    except Exception as e:
        logger.error(f"Error parsing hourly prices from {filename}: {e}")

def main():
    """Run the debug tests."""
    logger.info("=== Testing normalize_hour_value ===")
    test_normalize_hour_value()
    
    logger.info("\n=== Testing format_hour_key ===")
    test_format_hour_key()
    
    logger.info("\n=== Testing parse_xml ===")
    test_parse_xml()
    
    logger.info("\n=== Testing parse_hourly_prices ===")
    test_parse_hourly_prices()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
