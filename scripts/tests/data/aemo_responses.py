"""Sample API response data for AEMO (Australian Energy Market Operator).

This module provides realistic sample responses for the AEMO API,
allowing tests to run without actual network requests.
"""

import json
from datetime import datetime, timedelta, timezone
from ..mocks.api_responses import generate_hourly_prices

# AEMO response structure tends to have a specific format with price data
def create_aemo_response(area="NSW1", hours=24):
    """Generate a realistic AEMO API response.
    
    Args:
        area: Market area code (NSW1, VIC1, etc.)
        hours: Number of hours to include
        
    Returns:
        List of price data points mimicking AEMO response format
    """
    # Start time, typically starting at current day
    start_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # AEMO uses 30-minute intervals in Australia/Sydney timezone
    sydney_offset = timezone(timedelta(hours=10))  # +10:00 for Sydney
    start_time = start_time.astimezone(sydney_offset)
    
    # Generate price data points for intervals
    data_points = []
    
    for interval in range(hours * 2):  # 2 intervals per hour (30 min each)
        interval_time = start_time + timedelta(minutes=30 * interval)
        
        # Create a realistic price (AUD/MWh) for this interval
        # Prices in Australia can be quite volatile
        if area == "NSW1":
            base_price = 85.0  # NSW tends to have higher prices
        elif area == "VIC1":
            base_price = 75.0  # Victoria slightly lower
        else:
            base_price = 80.0  # Default
            
        # Use deterministic price generation based on interval for repeatability
        interval_factor = 1.0 + (((interval % 48) - 24) / 24) * 0.6  # Daily curve
        price = base_price * interval_factor
        
        # Add some variation but keep it deterministic
        variation = ((interval * 13) % 100) / 100.0 * 20.0  # Up to $20 variation
        price += variation - 10.0
        
        # Create interval data point
        data_point = {
            "SETTLEMENTDATE": interval_time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "REGIONID": area,
            "RRP": round(price, 2),  # Regional Reference Price in AUD/MWh
            "PERIODTYPE": "TRADE",
            "INTERVENTION": 0
        }
        
        data_points.append(data_point)
    
    return data_points

# Sample AEMO responses for common areas
SAMPLE_AEMO_NSW1 = create_aemo_response(area="NSW1")
SAMPLE_AEMO_VIC1 = create_aemo_response(area="VIC1")

# Combined samples dict for easy access
SAMPLE_AEMO_RESPONSES = {
    "NSW1": SAMPLE_AEMO_NSW1,
    "VIC1": SAMPLE_AEMO_VIC1
}