"""Utility functions for Nordpool API."""
import logging
import datetime
from ..utils.timezone_utils import convert_to_local_time
from ..const import CURRENCY_SUBUNIT_NAMES, REGION_TO_CURRENCY

_LOGGER = logging.getLogger(__name__)

# Define the exchange rates directly (can be replaced with dynamic service later)
EXCHANGE_RATES = {
    "SEK": 10.72411,  # 1 EUR = 10.72411 SEK
    "NOK": 11.7,      # 1 EUR = 11.7 NOK
    "DKK": 7.46,      # 1 EUR = 7.46 DKK
    "EUR": 1.0
}

async def process_day_data(data, area, current_hour=None, use_subunit=False, currency="EUR", apply_vat_func=None, session=None):
    """Process price data for a single day with direct currency handling."""
    if not data or "multiAreaEntries" not in data:
        _LOGGER.debug("No valid data provided to process_day_data")
        return None
    
    # Process prices
    current_price = None
    next_hour_price = None
    hourly_prices = {}
    all_prices = []
    raw_values = {}  # Store raw values before conversion
    raw_prices = []  # Store raw price data in the original format
    
    try:
        # Process based on the API format
        entries = data.get("multiAreaEntries", [])
        if not entries:
            _LOGGER.debug("Empty multiAreaEntries in Nordpool data")
            return None
        
        _LOGGER.debug(f"Processing {len(entries)} entries for area: {area}")
        
        # Check if the area exists in any entry and collect all available areas
        area_exists = False
        available_areas = set()
        
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            
            entry_per_area = entry.get("entryPerArea")
            if not entry_per_area or not isinstance(entry_per_area, dict):
                continue
            
            available_areas.update(entry_per_area.keys())
            
            if area in entry_per_area:
                area_exists = True
        
        if not area_exists:
            _LOGGER.error(f"Area '{area}' not found in any entry. Available areas: {sorted(available_areas)}")
            return None
            
        # Get target currency based on area
        target_currency = REGION_TO_CURRENCY.get(area, currency)
        _LOGGER.debug(f"Using target currency {target_currency} for area {area}")
        
        # Get exchange rate from data or use our fixed rates
        exchange_rate = EXCHANGE_RATES.get(target_currency, 1.0)
        if "exchangeRate" in data:
            try:
                api_exchange_rate = float(data["exchangeRate"])
                if api_exchange_rate > 0:
                    exchange_rate = api_exchange_rate
                    _LOGGER.debug(f"Using exchange rate from API: {exchange_rate}")
            except (ValueError, TypeError):
                _LOGGER.warning(f"Invalid exchange rate in API data: {data.get('exchangeRate')}")
        
        # Source currency from API or default to EUR
        api_currency = data.get("currency", "EUR")
        _LOGGER.debug(f"API data currency: {api_currency}")
        
        # Extract VAT rate
        vat_rate = 0.0
        if apply_vat_func and hasattr(apply_vat_func, "__self__") and hasattr(apply_vat_func.__self__, "vat"):
            vat_rate = apply_vat_func.__self__.vat
        
        for entry in entries:
            if not isinstance(entry, dict):
                continue
                
            start_time = entry.get("deliveryStart")
            end_time = entry.get("deliveryEnd")
            if not start_time or not end_time:
                _LOGGER.warning(f"Missing deliveryStart/End in entry")
                continue
            
            entry_per_area = entry.get("entryPerArea")
            if not entry_per_area or not isinstance(entry_per_area, dict):
                _LOGGER.warning(f"Missing or invalid entryPerArea in entry")
                continue
            
            # Check if this area exists in the entryPerArea data
            if area not in entry_per_area:
                continue
            
            # Get the price for this area
            price = entry_per_area.get(area)
            if price is None:
                _LOGGER.debug(f"No price found for area '{area}' in this entry")
                continue
            
            # Store in raw prices list
            raw_prices.append({
                "start": start_time,
                "end": end_time,
                "price": price  
            })
            
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
            _LOGGER.debug(f"Raw price value from API: {raw_price} {api_currency}/MWh for {start_time}")
            
            # DIRECT CONVERSION APPROACH
            # Step 1: Convert currency (EUR to target currency)
            price_in_target_currency = raw_price * exchange_rate
            _LOGGER.debug(f"Step 1 - Currency conversion: {raw_price} {api_currency}/MWh → {price_in_target_currency} {target_currency}/MWh")
            
            # Step 2: Convert from MWh to kWh (divide by 1000)
            price_per_kwh = price_in_target_currency / 1000
            _LOGGER.debug(f"Step 2 - Energy unit conversion: {price_in_target_currency} {target_currency}/MWh → {price_per_kwh} {target_currency}/kWh")
            
            # Step 3: Apply VAT if needed
            if vat_rate > 0:
                price_with_vat = price_per_kwh * (1 + vat_rate)
                _LOGGER.debug(f"Step 3 - VAT application: {price_per_kwh} {target_currency}/kWh → {price_with_vat} {target_currency}/kWh (VAT: {vat_rate:.2%})")
            else:
                price_with_vat = price_per_kwh
            
            # Step 4: Convert to subunit if requested
            if use_subunit:
                final_price = price_with_vat * 100  # e.g., SEK to öre
                subunit_name = CURRENCY_SUBUNIT_NAMES.get(target_currency, "cents")
                _LOGGER.debug(f"Step 4 - Subunit conversion: {price_with_vat} {target_currency}/kWh → {final_price} {subunit_name}/kWh")
            else:
                final_price = price_with_vat
            
            # Parse the hour from the start_time
            try:
                # Parse the datetime with proper timezone handling
                dt = datetime.datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                
                # Convert to local time for this area
                local_dt = convert_to_local_time(dt, area)
                
                hour = local_dt.hour
                
                # Format time in HH:MM format
                hour_str = f"{hour:02d}:00"
                hourly_prices[hour_str] = final_price
                all_prices.append(final_price)
                
                # Check if this is current hour
                if current_hour is not None and hour == current_hour:
                    current_price = final_price
                    _LOGGER.debug(f"Current hour ({hour}) price: {final_price}")
                    # Store raw value for current price
                    raw_values["current_price"] = {
                        "raw": raw_price,
                        "unit": f"{api_currency}/MWh",
                        "final": final_price,
                        "currency": target_currency if not use_subunit else CURRENCY_SUBUNIT_NAMES.get(target_currency, "cents"),
                        "vat_rate": vat_rate
                    }
                    
                # Check if this is next hour
                if current_hour is not None and hour == (current_hour + 1) % 24:
                    next_hour_price = final_price
                    _LOGGER.debug(f"Next hour ({(current_hour + 1) % 24}) price: {final_price}")
                    # Store raw value for next hour price
                    raw_values["next_hour_price"] = {
                        "raw": raw_price,
                        "unit": f"{api_currency}/MWh",
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
            "raw_values": raw_values,
            "raw_prices": raw_prices  # Store raw prices in original format
        }
    except Exception as e:
        _LOGGER.error(f"Error processing data: {e}", exc_info=True)
        return None
