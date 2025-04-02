"""Utility functions for Nordpool API."""
import logging
import datetime
from ..utils.currency_utils import convert_to_subunit, convert_energy_price
from ..utils.timezone_utils import convert_to_local_time

_LOGGER = logging.getLogger(__name__)

def process_day_data(data, area, current_hour=None, use_subunit=False, currency="EUR", apply_vat_func=None):
    """Process price data for a single day."""
    if not data or "multiAreaEntries" not in data:
        _LOGGER.debug("No valid data provided to process_day_data")
        return None
    
    # Process prices
    current_price = None
    next_hour_price = None
    hourly_prices = {}
    all_prices = []
    
    try:
        # Process based on the new API format
        entries = data.get("multiAreaEntries", [])
        if not entries:
            _LOGGER.debug("Empty multiAreaEntries in Nordpool data")
            return None
            
        for entry in entries:
            if not isinstance(entry, dict):
                continue
                
            start_time = entry.get("deliveryStart")
            if not start_time:
                continue
            
            entry_per_area = entry.get("entryPerArea")
            if not entry_per_area or not isinstance(entry_per_area, dict):
                continue
            
            # Check if this area exists in the entryPerArea data
            if area not in entry_per_area:
                continue
            
            # Get the price for this area
            price = entry_per_area.get(area)
            if price is None:
                continue
            
            # Convert to float if needed
            if isinstance(price, str):
                try:
                    price = float(price.replace(",", ".").replace(" ", ""))
                except ValueError:
                    continue
            elif not isinstance(price, (int, float)):
                continue
            
            # Convert from EUR/MWh to the appropriate currency and unit
            price = convert_energy_price(price, from_unit="MWh", to_unit="kWh", vat=0)
            if apply_vat_func:
                price = apply_vat_func(price)
            
            # Convert to subunit (e.g., öre, cents) if enabled
            if use_subunit:
                price = convert_to_subunit(price, currency)
            
            # Parse the hour from the start_time
            try:
                # Parse the datetime with proper timezone handling
                dt = datetime.datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                
                # Convert to local time for this area
                local_dt = convert_to_local_time(dt, area)
                
                hour = local_dt.hour
                
                # Format time in HH:MM format (like website)
                hour_str = f"{hour:02d}:00"
                hourly_prices[hour_str] = price
                all_prices.append(price)
                
                # Check if this is current hour
                if current_hour is not None and hour == current_hour:
                    current_price = price
                    
                # Check if this is next hour
                if current_hour is not None and hour == (current_hour + 1) % 24:
                    next_hour_price = price
                    
            except (ValueError, TypeError) as e:
                _LOGGER.error(f"Error parsing datetime {start_time}: {e}")
                continue
        
        if not hourly_prices:
            _LOGGER.warning("No hourly prices found in Nordpool data")
            return None
            
        # Calculate day average
        day_average_price = sum(all_prices) / len(all_prices) if all_prices else None
        
        # Find peak (highest) and off-peak (lowest) prices
        peak_price = max(all_prices) if all_prices else None
        off_peak_price = min(all_prices) if all_prices else None
        
        return {
            "current_price": current_price,
            "next_hour_price": next_hour_price,
            "day_average_price": day_average_price,
            "peak_price": peak_price,
            "off_peak_price": off_peak_price,
            "hourly_prices": hourly_prices,
        }
    except Exception as e:
        _LOGGER.error(f"Error processing Nordpool data: {e}")
        return None

def generate_simulated_data(now, apply_vat_func, currency, use_subunit=False):
    """Generate simulated data when Nordpool API is unavailable."""
    current_hour = now.hour
    
    # Create simulated hourly prices for today
    today_hourly_prices = {}
    today_all_prices = []
    
    # Create simulated hourly prices for tomorrow
    tomorrow_hourly_prices = {}
    tomorrow_all_prices = []
    
    # Generate prices with realistic patterns for today and tomorrow
    for hour in range(24):
        # Base price with time-based variation
        is_peak = (7 <= hour <= 9) or (18 <= hour <= 21)
        
        # Today's prices
        if is_peak:
            today_price = 0.18 + 0.02 * (hour % 3) + (now.day % 10) * 0.001
        else:
            today_price = 0.12 + 0.01 * (abs(12 - hour) / 12) + (now.day % 10) * 0.001
        
        today_price = apply_vat_func(today_price)
        hour_str = f"{hour:02d}:00"  # Format HH:MM
        today_hourly_prices[hour_str] = today_price
        today_all_prices.append(today_price)
        
        # Tomorrow's prices (slightly different pattern)
        if is_peak:
            tomorrow_price = 0.19 + 0.015 * (hour % 3) + ((now.day + 1) % 10) * 0.001
        else:
            tomorrow_price = 0.13 + 0.008 * (abs(12 - hour) / 12) + ((now.day + 1) % 10) * 0.001
        
        tomorrow_price = apply_vat_func(tomorrow_price)
        tomorrow_hourly_prices[hour_str] = tomorrow_price
        tomorrow_all_prices.append(tomorrow_price)
    
    current_price = today_hourly_prices.get(f"{current_hour:02d}:00")
    next_hour_price = today_hourly_prices.get(f"{(current_hour + 1) % 24:02d}:00")
    
    # Calculate day averages
    today_average_price = sum(today_all_prices) / len(today_all_prices) if today_all_prices else None
    tomorrow_average_price = sum(tomorrow_all_prices) / len(tomorrow_all_prices) if tomorrow_all_prices else None
    
    # Find peak and off-peak prices
    today_peak_price = max(today_all_prices) if today_all_prices else None
    today_off_peak_price = min(today_all_prices) if today_all_prices else None
    
    tomorrow_peak_price = max(tomorrow_all_prices) if tomorrow_all_prices else None
    tomorrow_off_peak_price = min(tomorrow_all_prices) if tomorrow_all_prices else None
    
    return {
        "current_price": current_price,
        "next_hour_price": next_hour_price,
        "day_average_price": today_average_price,
        "peak_price": today_peak_price,
        "off_peak_price": today_off_peak_price,
        "hourly_prices": today_hourly_prices,
        "tomorrow_average_price": tomorrow_average_price,
        "tomorrow_peak_price": tomorrow_peak_price,
        "tomorrow_off_peak_price": tomorrow_off_peak_price,
        "tomorrow_hourly_prices": tomorrow_hourly_prices,
        "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "simulated": True,  # Flag to indicate this is simulated data
    }
