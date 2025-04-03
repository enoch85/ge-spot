"""Utility functions for Nordpool API."""
import logging
import datetime
from ..utils.currency_utils import convert_to_subunit, mwh_to_kwh
from ..utils.timezone_utils import convert_to_local_time
from ..utils.exchange_service import convert_currency, get_exchange_service
from ..const import CURRENCY_SUBUNIT_NAMES, REGION_TO_CURRENCY

_LOGGER = logging.getLogger(__name__)

async def process_day_data(data, area, current_hour=None, use_subunit=False, currency="EUR", apply_vat_func=None):
    """Process price data for a single day with improved currency handling."""
    if not data or "multiAreaEntries" not in data:
        _LOGGER.debug("No valid data provided to process_day_data")
        return None
    
    # Process prices
    current_price = None
    next_hour_price = None
    hourly_prices = {}
    all_prices = []
    raw_values = {}  # Store raw values before conversion
    
    try:
        # Process based on the API format
        entries = data.get("multiAreaEntries", [])
        if not entries:
            _LOGGER.debug("Empty multiAreaEntries in Nordpool data")
            return None
        
        _LOGGER.info(f"Processing {len(entries)} entries for area: {area}")
        
        # Check if the area exists in any entry and collect all available areas
        area_exists = False
        available_areas = set()
        
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            
            entry_per_area = entry.get("entryPerArea")
            if not entry_per_area or not isinstance(entry_per_area, dict):
                continue
            
            # Add all areas from this entry to the available_areas set
            available_areas.update(entry_per_area.keys())
            
            if area in entry_per_area:
                area_exists = True
        
        if not area_exists:
            _LOGGER.error(f"Area '{area}' not found in any entry. Available areas: {sorted(available_areas)}")
            return None
            
        # Get target currency based on area
        target_currency = REGION_TO_CURRENCY.get(area, currency)
        _LOGGER.info(f"Using target currency {target_currency} for area {area}")
        
        # Get exchange rate service
        exchange_service = await get_exchange_service()
        
        for entry in entries:
            if not isinstance(entry, dict):
                continue
                
            start_time = entry.get("deliveryStart")
            if not start_time:
                _LOGGER.warning(f"Missing deliveryStart in entry: {entry.keys() if isinstance(entry, dict) else 'not a dict'}")
                continue
            
            entry_per_area = entry.get("entryPerArea")
            if not entry_per_area or not isinstance(entry_per_area, dict):
                _LOGGER.warning(f"Missing or invalid entryPerArea in entry: {entry.keys() if isinstance(entry, dict) else 'not a dict'}")
                continue
            
            # Check if this area exists in the entryPerArea data
            if area not in entry_per_area:
                continue
            
            # Get the price for this area
            price = entry_per_area.get(area)
            if price is None:
                _LOGGER.debug(f"No price found for area '{area}' in this entry")
                continue
            
            # Convert to float if needed
            if isinstance(price, str):
                try:
                    price = float(price.replace(",", ".").replace(" ", ""))
                except ValueError:
                    _LOGGER.warning(f"Could not convert price '{price}' to float")
                    continue
            elif not isinstance(price, (int, float)):
                _LOGGER.warning(f"Price is not a number: {price} (type: {type(price)})")
                continue
            
            # Store the raw price value before any conversions
            raw_price = price
            
            _LOGGER.info(f"Raw price value from API: {raw_price} EUR/MWh for entry {start_time}")
            
            # Step 1: Convert from MWh to kWh (divide by 1000)
            price_per_kwh = mwh_to_kwh(price)
            _LOGGER.info(f"Converted from MWh to kWh: {raw_price} EUR/MWh → {price_per_kwh} EUR/kWh")
            
            # Step 2: Convert currency from EUR to target currency if needed
            # Use exchange rate service for dynamic rates
            if "EUR" != target_currency:
                price_in_target_currency = await exchange_service.convert(price_per_kwh, "EUR", target_currency)
                _LOGGER.info(f"Currency conversion: {price_per_kwh} EUR/kWh → {price_in_target_currency} {target_currency}/kWh")
            else:
                price_in_target_currency = price_per_kwh
            
            # Step 3: Apply VAT
            vat_rate = 0.0
            if apply_vat_func:
                # Extract vat rate from the function for logging
                if hasattr(apply_vat_func, "__self__") and hasattr(apply_vat_func.__self__, "vat"):
                    vat_rate = apply_vat_func.__self__.vat
                price_with_vat = apply_vat_func(price_in_target_currency)
                _LOGGER.info(f"Applied VAT {vat_rate:.2%}: {price_in_target_currency} → {price_with_vat}")
            else:
                price_with_vat = price_in_target_currency
            
            # Step 4: Convert to subunit if requested
            final_price = price_with_vat
            if use_subunit:
                final_price = convert_to_subunit(price_with_vat, target_currency)
                _LOGGER.info(f"Converted to subunit: {price_with_vat} {target_currency}/kWh → {final_price} {CURRENCY_SUBUNIT_NAMES.get(target_currency, 'cents')}/kWh")
            
            # Parse the hour from the start_time
            try:
                # Parse the datetime with proper timezone handling
                dt = datetime.datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                
                # Convert to local time for this area
                local_dt = convert_to_local_time(dt, area)
                
                hour = local_dt.hour
                
                # Format time in HH:MM format (like website)
                hour_str = f"{hour:02d}:00"
                hourly_prices[hour_str] = final_price
                all_prices.append(final_price)
                
                # Check if this is current hour
                if current_hour is not None and hour == current_hour:
                    current_price = final_price
                    _LOGGER.info(f"Found current hour ({hour}) price: {final_price} {CURRENCY_SUBUNIT_NAMES.get(target_currency, 'cents') if use_subunit else target_currency}/kWh")
                    # Store detailed conversion steps for current price
                    raw_values["current_price"] = {
                        "raw": raw_price,
                        "unit": "EUR/MWh",
                        "per_kwh": price_per_kwh,
                        "target_currency": price_in_target_currency,
                        "with_vat": price_with_vat,
                        "final": final_price,
                        "currency": target_currency if not use_subunit else CURRENCY_SUBUNIT_NAMES.get(target_currency, "cents"),
                        "vat_rate": vat_rate
                    }
                    
                # Check if this is next hour
                if current_hour is not None and hour == (current_hour + 1) % 24:
                    next_hour_price = final_price
                    _LOGGER.info(f"Found next hour ({(current_hour + 1) % 24}) price: {final_price}")
                    # Store detailed conversion steps for next hour price
                    raw_values["next_hour_price"] = {
                        "raw": raw_price,
                        "unit": "EUR/MWh",
                        "per_kwh": price_per_kwh,
                        "target_currency": price_in_target_currency,
                        "with_vat": price_with_vat,
                        "final": final_price,
                        "currency": target_currency if not use_subunit else CURRENCY_SUBUNIT_NAMES.get(target_currency, "cents"),
                        "vat_rate": vat_rate
                    }
                    
            except (ValueError, TypeError) as e:
                _LOGGER.error(f"Error parsing datetime {start_time}: {e}")
                continue
        
        if not hourly_prices:
            _LOGGER.warning(f"No hourly prices found in data for area {area}")
            return None
            
        # Check if we have all 24 hours
        if len(hourly_prices) < 24:
            _LOGGER.warning(f"Incomplete hourly prices for area {area}: found {len(hourly_prices)}/24 hours")
            
        # Calculate day average
        day_average_price = sum(all_prices) / len(all_prices) if all_prices else None
        
        # Find peak (highest) and off-peak (lowest) prices
        peak_price = max(all_prices) if all_prices else None
        off_peak_price = min(all_prices) if all_prices else None
        
        # Store raw values for statistics
        raw_values["day_average_price"] = {
            "value": day_average_price,
            "calculation": "average of all hourly prices"
        }
        
        raw_values["peak_price"] = {
            "value": peak_price,
            "calculation": "maximum of all hourly prices"
        }
        
        raw_values["off_peak_price"] = {
            "value": off_peak_price,
            "calculation": "minimum of all hourly prices"
        }
        
        return {
            "current_price": current_price,
            "next_hour_price": next_hour_price,
            "day_average_price": day_average_price,
            "peak_price": peak_price,
            "off_peak_price": off_peak_price,
            "hourly_prices": hourly_prices,
            "raw_values": raw_values
        }
    except Exception as e:
        _LOGGER.error(f"Error processing data: {e}", exc_info=True)
        return None

async def generate_simulated_data(now, apply_vat_func, currency, use_subunit=False):
    """Generate simulated data when Nordpool API is unavailable."""
    current_hour = now.hour
    
    # Create simulated hourly prices for today
    today_hourly_prices = {}
    today_all_prices = []
    raw_values = {}  # Store raw values
    
    # Create simulated hourly prices for tomorrow
    tomorrow_hourly_prices = {}
    tomorrow_all_prices = []
    
    # Get actual VAT rate for logging
    vat_rate = 0.0
    if hasattr(apply_vat_func, "__self__") and hasattr(apply_vat_func.__self__, "vat"):
        vat_rate = apply_vat_func.__self__.vat
    
    # Target currency based on currency parameter
    target_currency = currency
    _LOGGER.info(f"Using currency {target_currency} for simulated data")
    
    # Get exchange service
    exchange_service = await get_exchange_service()
    
    # Generate prices with realistic patterns for today and tomorrow
    for hour in range(24):
        # Base price with time-based variation
        is_peak = (7 <= hour <= 9) or (18 <= hour <= 21)
        
        # Today's prices - DIRECT IN MWh FOR REALISM
        if is_peak:
            raw_price = 180 + 20 * (hour % 3) + (now.day % 10) * 1
        else:
            raw_price = 120 + 10 * (abs(12 - hour) / 13) + (now.day % 10) * 1
        
        # Store raw value before any conversion
        _LOGGER.info(f"Simulated raw price: {raw_price} EUR/MWh for hour {hour}")
        
        # Convert from MWh to kWh
        price_per_kwh = mwh_to_kwh(raw_price)
        _LOGGER.info(f"Converted to kWh: {raw_price} EUR/MWh → {price_per_kwh} EUR/kWh")
        
        # Convert currency if needed
        if "EUR" != target_currency:
            price_in_target = await exchange_service.convert(price_per_kwh, "EUR", target_currency)
            _LOGGER.info(f"Currency conversion: {price_per_kwh} EUR/kWh → {price_in_target} {target_currency}/kWh")
        else:
            price_in_target = price_per_kwh
        
        # Apply VAT
        price_with_vat = apply_vat_func(price_in_target)
        _LOGGER.info(f"Applied VAT {vat_rate:.2%}: {price_in_target} → {price_with_vat}")
        
        # Convert to subunit if requested
        today_price = price_with_vat
        if use_subunit:
            today_price = convert_to_subunit(price_with_vat, target_currency)
            _LOGGER.info(f"Converted to subunit: {price_with_vat} {target_currency}/kWh → {today_price} {CURRENCY_SUBUNIT_NAMES.get(target_currency, 'cents')}/kWh")
            
        hour_str = f"{hour:02d}:00"  # Format HH:MM
        today_hourly_prices[hour_str] = today_price
        today_all_prices.append(today_price)
        
        # Store raw values for current and next hour
        if hour == current_hour:
            raw_values["current_price"] = {
                "raw": raw_price,
                "unit": "EUR/MWh",
                "per_kwh": price_per_kwh,
                "target_currency": price_in_target,
                "with_vat": price_with_vat,
                "final": today_price,
                "currency": target_currency if not use_subunit else CURRENCY_SUBUNIT_NAMES.get(target_currency, "cents"),
                "vat_rate": vat_rate,
                "simulated": True
            }
        elif hour == (current_hour + 1) % 24:
            raw_values["next_hour_price"] = {
                "raw": raw_price,
                "unit": "EUR/MWh",
                "per_kwh": price_per_kwh,
                "target_currency": price_in_target,
                "with_vat": price_with_vat,
                "final": today_price,
                "currency": target_currency if not use_subunit else CURRENCY_SUBUNIT_NAMES.get(target_currency, "cents"),
                "vat_rate": vat_rate,
                "simulated": True
            }
        
        # Tomorrow's prices (slightly different pattern) - DIRECT IN MWh FOR REALISM
        if is_peak:
            tomorrow_raw_price = 190 + 15 * (hour % 3) + ((now.day + 1) % 10) * 1
        else:
            tomorrow_raw_price = 130 + 8 * (abs(12 - hour) / 12) + ((now.day + 1) % 10) * 1
        
        # Convert to kWh
        tomorrow_price_per_kwh = mwh_to_kwh(tomorrow_raw_price)
        
        # Convert currency if needed
        if "EUR" != target_currency:
            tomorrow_price_in_target = await exchange_service.convert(tomorrow_price_per_kwh, "EUR", target_currency)
        else:
            tomorrow_price_in_target = tomorrow_price_per_kwh
        
        # Apply VAT
        tomorrow_price_with_vat = apply_vat_func(tomorrow_price_in_target)
        
        # Convert to subunit if requested
        tomorrow_price = tomorrow_price_with_vat
        if use_subunit:
            tomorrow_price = convert_to_subunit(tomorrow_price_with_vat, target_currency)
            
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
    
    # Store raw values for statistics
    raw_values["day_average_price"] = {
        "value": today_average_price,
        "calculation": "average of all hourly prices",
        "simulated": True
    }
    
    raw_values["peak_price"] = {
        "value": today_peak_price,
        "calculation": "maximum of all hourly prices",
        "simulated": True
    }
    
    raw_values["off_peak_price"] = {
        "value": today_off_peak_price,
        "calculation": "minimum of all hourly prices",
        "simulated": True
    }
    
    _LOGGER.info(f"Generated simulated data with current price: {current_price}, next hour: {next_hour_price}")
    
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
        "raw_values": raw_values,
        "simulated": True,  # Flag to indicate this is simulated data
    }
