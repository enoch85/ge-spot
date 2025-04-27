"""Sample API response data for EPEX (European Power Exchange).

This module provides realistic sample responses for the EPEX API,
allowing tests to run without actual network requests.
"""

import json
from datetime import datetime, timedelta, timezone
from ..mocks.api_responses import generate_hourly_prices

def create_epex_response(area="FR", hours=24):
    """Generate a realistic EPEX API response.
    
    Args:
        area: Market area code (FR, DE-LU, etc.)
        hours: Number of hours to include
        
    Returns:
        List of price data points mimicking EPEX response format
    """
    # Start time for the pricing data
    start_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # EPEX uses Central European timezone
    cet_offset = timezone(timedelta(hours=1))  # CET is UTC+1 (or UTC+2 in summer)
    start_time = start_time.astimezone(cet_offset)
    
    # Generate price data points
    data_points = []
    
    for hour in range(hours):
        # Time for this price point
        hour_time = start_time + timedelta(hours=hour)
        
        # Base price in EUR/MWh varies by area
        if area == "FR":
            base_price = 75.0  # France
        elif area == "DE-LU":
            base_price = 70.0  # Germany-Luxembourg
        else:
            base_price = 72.0  # Default
            
        # Deterministic price variation based on hour
        hour_factor = 1.0 + (((hour % 24) - 12) / 12) * 0.6  # Daily curve
        price = base_price * hour_factor
        
        # Add some variation but keep it deterministic
        variation = ((hour * 23) % 100) / 100.0 * 30.0  # Up to €30 variation
        price += variation - 15.0
        
        # Format the time as needed by the parser
        time_str = hour_time.strftime("%Y-%m-%dT%H:%M:%S%z")
        
        # Create price data point
        data_point = {
            "datetime": time_str,
            "price": round(price, 2),
            "area": area,  # Store the area code for each data point
            "currency": "EUR",
            "unit": "MWh"
        }
        
        data_points.append(data_point)
    
    return data_points

# Sample EPEX responses for common areas
SAMPLE_EPEX_FR = create_epex_response(area="FR")
SAMPLE_EPEX_DE_LU = create_epex_response(area="DE-LU")

# Combined samples dict for easy access
SAMPLE_EPEX_RESPONSES = {
    "FR": SAMPLE_EPEX_FR,
    "DE-LU": SAMPLE_EPEX_DE_LU
}