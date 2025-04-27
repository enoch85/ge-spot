"""Sample API response data for Energi Data Service (Denmark).

This module provides realistic sample responses for the Energi Data Service API,
allowing tests to run without actual network requests.
"""

import json
from datetime import datetime, timedelta, timezone
from ..mocks.api_responses import generate_hourly_prices

def create_energi_data_response(area="DK1", hours=24):
    """Generate a realistic Energi Data Service API response.
    
    Args:
        area: Market area code (DK1, DK2)
        hours: Number of hours to include
        
    Returns:
        Dict mimicking Energi Data Service response format
    """
    # Start time, typically starting at current day
    start_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Energi Data records
    records = []
    
    for hour in range(hours):
        hour_time = start_time + timedelta(hours=hour)
        
        # Base price in DKK/MWh - Denmark tends to have volatile prices
        if area == "DK1":
            base_price = 350.0  # West Denmark
        else:  # DK2
            base_price = 380.0  # East Denmark
            
        # Deterministic price variation based on hour
        hour_factor = 1.0 + (((hour % 24) - 12) / 12) * 0.7  # Daily curve
        price = base_price * hour_factor
        
        # Add some variation but keep it deterministic
        variation = ((hour * 17) % 100) / 100.0 * 50.0  # Up to 50 DKK variation
        price += variation - 25.0
        
        # Create hour record
        record = {
            "HourUTC": hour_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "HourDK": (hour_time + timedelta(hours=1 if hour_time.dst().seconds > 0 else 2)).strftime("%Y-%m-%dT%H:%M:%S"),
            "PriceArea": area,
            "SpotPriceDKK": round(price, 2),
            "SpotPriceEUR": round(price / 7.45, 2),  # Approximate DKK/EUR conversion
        }
        
        records.append(record)
    
    # Full response structure
    response = {
        "records": records,
        "total": len(records),
        "dataset": "Elspotprices",
        "timezone": "UTC"
    }
    
    return response

# Sample Energi Data responses for common areas
SAMPLE_ENERGI_DATA_DK1 = create_energi_data_response(area="DK1")
SAMPLE_ENERGI_DATA_DK2 = create_energi_data_response(area="DK2")

# Combined samples dict for easy access
SAMPLE_ENERGI_DATA_RESPONSES = {
    "DK1": SAMPLE_ENERGI_DATA_DK1,
    "DK2": SAMPLE_ENERGI_DATA_DK2
}