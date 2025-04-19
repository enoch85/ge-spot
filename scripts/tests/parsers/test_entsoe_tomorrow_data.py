#!/usr/bin/env python3
"""Test script for debugging ENTSO-E tomorrow data issues.

This script mimics the ENTSO-E API requests made by the integration and
analyzes the responses to determine if tomorrow's data is available.
"""
import sys
import os
import logging
import argparse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import requests
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path so we can import the custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# Import constants from the integration
try:
    from custom_components.ge_spot.const.time import TimeFormat
    from custom_components.ge_spot.const.network import Network
    from custom_components.ge_spot.const.areas import AreaMapping
    from custom_components.ge_spot.const.sources import Source
    from custom_components.ge_spot.utils.date_range import generate_date_ranges
    IMPORTS_SUCCESSFUL = True
except ImportError as e:
    logger.error(f"Failed to import from custom_components: {e}")
    IMPORTS_SUCCESSFUL = False

# ENTSO-E API constants
BASE_URL = "https://web-api.tp.entsoe.eu/api"
DOCUMENT_TYPES = ["A44", "A62", "A65"]

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Test ENTSO-E API for tomorrow's data")
    parser.add_argument("--api-key", help="ENTSO-E API key")
    parser.add_argument("--area", default="SE4", help="Area code (default: SE4)")
    parser.add_argument("--output-dir", default="./entsoe_responses", help="Directory to save responses")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()

def setup_logging(debug):
    """Set up logging with the specified level."""
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

def get_entsoe_area_code(area):
    """Get ENTSO-E area code from area name."""
    if IMPORTS_SUCCESSFUL:
        return AreaMapping.ENTSOE_MAPPING.get(area, area)
    else:
        # Hardcoded mapping for common areas
        mapping = {
            "SE1": "10Y1001A1001A44P",
            "SE2": "10Y1001A1001A45N",
            "SE3": "10Y1001A1001A46L",
            "SE4": "10Y1001A1001A47J",
            "DK1": "10YDK-1--------W",
            "DK2": "10YDK-2--------M",
            "NO1": "10YNO-1--------2",
            "NO2": "10YNO-2--------T",
            "NO3": "10YNO-3--------J",
            "NO4": "10YNO-4--------9",
            "NO5": "10Y1001A1001A48H",
            "FI": "10YFI-1--------U",
            "EE": "10Y1001A1001A39I",
            "LV": "10YLV-1001A00074",
            "LT": "10YLT-1001A0008Q",
            "DE-LU": "10Y1001A1001A82H",
            "FR": "10YFR-RTE------C",
            "NL": "10YNL----------L",
            "BE": "10YBE----------2",
            "AT": "10YAT-APG------L",
            "CH": "10YCH-SWISSGRIDZ",
            "IT": "10YIT-GRTN-----B",
        }
        return mapping.get(area, area)

def generate_custom_date_ranges(reference_time):
    """Generate date ranges for ENTSO-E API requests."""
    if IMPORTS_SUCCESSFUL:
        return generate_date_ranges(reference_time, Source.ENTSOE)
    else:
        # Simplified date range generation
        date_ranges = [
            # Today to tomorrow
            (reference_time, reference_time + timedelta(days=1)),
            # Yesterday to today
            (reference_time - timedelta(days=1), reference_time),
            # Today to day after tomorrow
            (reference_time, reference_time + timedelta(days=2)),
            # Today to day after tomorrow (same as above, but kept for consistency with the integration)
            (reference_time, reference_time + timedelta(days=2)),
            # Two days ago to day after tomorrow
            (reference_time - timedelta(days=2), reference_time + timedelta(days=2))
        ]
        return date_ranges

def format_date_for_entsoe(dt):
    """Format datetime for ENTSO-E API (YYYYMMDDHHMM format)."""
    if IMPORTS_SUCCESSFUL:
        return dt.strftime(TimeFormat.ENTSOE_DATE_HOUR)
    else:
        return dt.strftime("%Y%m%d%H%M")

def make_entsoe_request(api_key, area_code, start_date, end_date, doc_type):
    """Make a request to the ENTSO-E API."""
    # Format dates for ENTSO-E API
    period_start = format_date_for_entsoe(start_date)
    period_end = format_date_for_entsoe(end_date)

    # Build query parameters
    params = {
        "securityToken": api_key,
        "documentType": doc_type,
        "in_Domain": area_code,
        "out_Domain": area_code,
        "periodStart": period_start,
        "periodEnd": period_end,
    }

    # Custom headers for ENTSO-E API
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/xml",
        "Content-Type": "application/xml"
    }

    logger.debug(f"Making ENTSO-E request with document type {doc_type} and date range: {period_start} to {period_end}")
    
    # Sanitize params for logging (hide API key)
    log_params = params.copy()
    if "securityToken" in log_params:
        log_params["securityToken"] = log_params["securityToken"][:4] + "****" + log_params["securityToken"][-4:]
    logger.debug(f"ENTSO-E request params: {log_params}")

    try:
        response = requests.get(
            BASE_URL,
            params=params,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.text
        else:
            logger.error(f"ENTSO-E API request failed with status {response.status_code}: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error making ENTSO-E API request: {e}")
        return None

def extract_hourly_prices(xml_data, reference_date):
    """Extract hourly prices from ENTSO-E XML response."""
    if not xml_data:
        return {}

    try:
        # Parse XML
        root = ET.fromstring(xml_data)

        # ENTSO-E uses a specific namespace
        ns = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}

        # Find time series elements
        time_series = root.findall(".//ns:TimeSeries", ns)
        
        # Store all hourly prices
        all_prices = {}
        
        # Process each TimeSeries
        for ts in time_series:
            # Check if this is a day-ahead price time series
            business_type = ts.find(".//ns:businessType", ns)
            if business_type is None or (business_type.text != "A62" and business_type.text != "A44"):
                # Skip if not a day-ahead price time series
                continue

            # Get period start time
            period = ts.find(".//ns:Period", ns)
            if period is None:
                continue

            start_str = period.find(".//ns:timeInterval/ns:start", ns)
            if start_str is None:
                continue

            try:
                # Parse start time
                start_time = datetime.fromisoformat(start_str.text.replace('Z', '+00:00'))

                # Get price points
                points = period.findall(".//ns:Point", ns)

                # Parse points
                for point in points:
                    position = point.find("ns:position", ns)
                    price = point.find("ns:price.amount", ns)

                    if position is not None and price is not None:
                        try:
                            pos = int(position.text)
                            price_val = float(price.text)

                            # Calculate hour
                            hour_time = start_time + timedelta(hours=pos-1)
                            
                            # Store with ISO format date as key
                            all_prices[hour_time.isoformat()] = price_val
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Failed to parse point: {e}")

            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse start time: {e}")

        return all_prices

    except ET.ParseError as e:
        logger.error(f"Error parsing ENTSO-E XML: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error processing ENTSO-E data: {e}")
        return {}

def analyze_prices(all_prices, reference_date):
    """Analyze prices to determine if tomorrow's data is available."""
    if not all_prices:
        return {
            "today_count": 0,
            "tomorrow_count": 0,
            "today_prices": {},
            "tomorrow_prices": {},
            "has_tomorrow_data": False
        }
    
    # Get today's and tomorrow's date
    today = reference_date.date()
    tomorrow = today + timedelta(days=1)
    
    # Separate today's and tomorrow's prices
    today_prices = {}
    tomorrow_prices = {}
    
    for dt_str, price in all_prices.items():
        try:
            dt = datetime.fromisoformat(dt_str)
            if dt.date() == today:
                hour_key = f"{dt.hour:02d}:00"
                today_prices[hour_key] = price
            elif dt.date() == tomorrow:
                hour_key = f"{dt.hour:02d}:00"
                tomorrow_prices[hour_key] = price
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse datetime: {e}")
    
    return {
        "today_count": len(today_prices),
        "tomorrow_count": len(tomorrow_prices),
        "today_prices": today_prices,
        "tomorrow_prices": tomorrow_prices,
        "has_tomorrow_data": len(tomorrow_prices) >= 20  # Consider valid if we have at least 20 hours
    }

def save_response(xml_data, output_dir, filename):
    """Save XML response to file."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    file_path = os.path.join(output_dir, filename)
    with open(file_path, "w") as f:
        f.write(xml_data)
    
    logger.info(f"Saved response to {file_path}")

def save_analysis(analysis, output_dir, filename):
    """Save analysis results to file."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    file_path = os.path.join(output_dir, filename)
    with open(file_path, "w") as f:
        json.dump(analysis, f, indent=2)
    
    logger.info(f"Saved analysis to {file_path}")

def main():
    """Run the ENTSO-E API test."""
    args = parse_args()
    setup_logging(args.debug)
    
    # Check if API key is provided
    api_key = args.api_key
    if not api_key:
        # Try to get API key from environment variable
        api_key = os.environ.get("API_KEY")
        if not api_key:
            logger.error("No API key provided. Use --api-key or set API_KEY environment variable.")
            return 1
    
    # Get ENTSO-E area code
    area = args.area
    area_code = get_entsoe_area_code(area)
    logger.info(f"Using ENTSO-E area code {area_code} for area {area}")
    
    # Get reference time (current time in UTC)
    reference_time = datetime.now(timezone.utc)
    logger.info(f"Reference time: {reference_time.isoformat()}")
    
    # Generate date ranges
    date_ranges = generate_custom_date_ranges(reference_time)
    logger.info(f"Generated {len(date_ranges)} date ranges")
    
    # Create output directory
    output_dir = args.output_dir
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Track if we found tomorrow's data
    found_tomorrow_data = False
    best_analysis = None
    
    # Try different date ranges and document types
    for i, (start_date, end_date) in enumerate(date_ranges):
        logger.info(f"Date range {i+1}: {start_date.isoformat()} to {end_date.isoformat()}")
        
        for doc_type in DOCUMENT_TYPES:
            logger.info(f"Trying document type {doc_type}")
            
            # Make request
            response = make_entsoe_request(api_key, area_code, start_date, end_date, doc_type)
            
            if response:
                # Save response
                filename = f"entsoe_{doc_type}_range{i+1}.xml"
                save_response(response, output_dir, filename)
                
                # Extract hourly prices
                all_prices = extract_hourly_prices(response, reference_time)
                
                # Analyze prices
                analysis = analyze_prices(all_prices, reference_time)
                
                # Save analysis
                analysis_filename = f"analysis_{doc_type}_range{i+1}.json"
                save_analysis(analysis, output_dir, analysis_filename)
                
                # Log results
                logger.info(f"Found {analysis['today_count']} hours for today and {analysis['tomorrow_count']} hours for tomorrow")
                
                if analysis['has_tomorrow_data']:
                    logger.info(f"Found tomorrow's data with document type {doc_type} and date range {i+1}")
                    found_tomorrow_data = True
                    
                    # Keep track of the best analysis (most hours for tomorrow)
                    if best_analysis is None or analysis['tomorrow_count'] > best_analysis['tomorrow_count']:
                        best_analysis = analysis
                        best_analysis['doc_type'] = doc_type
                        best_analysis['date_range'] = i+1
            else:
                logger.warning(f"No response for document type {doc_type} and date range {i+1}")
    
    # Print summary
    print("\n" + "=" * 80)
    print("ENTSO-E API TEST SUMMARY")
    print("=" * 80)
    
    if found_tomorrow_data:
        print(f"\nFound tomorrow's data!")
        print(f"Best result: {best_analysis['tomorrow_count']} hours with document type {best_analysis['doc_type']} and date range {best_analysis['date_range']}")
        
        # Print tomorrow's prices
        print("\nTomorrow's prices:")
        for hour, price in sorted(best_analysis['tomorrow_prices'].items()):
            print(f"  {hour}: {price}")
    else:
        print("\nNo tomorrow's data found in any response.")
        print("Check the saved responses and analysis files for more details.")
    
    print("\nAll responses and analysis have been saved to the output directory:")
    print(f"  {os.path.abspath(output_dir)}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
