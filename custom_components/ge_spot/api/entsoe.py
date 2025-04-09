"""API handler for ENTSO-E Transparency Platform."""
import logging
import datetime
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..price.conversion import async_convert_energy_price
from ..timezone.converters import localize_datetime
from ..timezone.parsers import parse_datetime
from ..const import (
    AreaMapping, Config, DisplayUnit, EntsoE, Network,
    TimeFormat, EnergyUnit, ContentType, Currency
)

_LOGGER = logging.getLogger(__name__)

BASE_URL = Network.URLs.ENTSOE

async def fetch_day_ahead_prices(config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using ENTSO-E API."""
    client = ApiClient(session=session)
    try:
        # Settings
        use_subunit = config.get(Config.DISPLAY_UNIT) == DisplayUnit.CENTS
        vat = config.get(Config.VAT, 0)
        
        # Fetch raw data
        raw_data = await _fetch_data(client, config, area, reference_time)
        if not raw_data:
            return None
        
        # Process data
        result = await _process_data(raw_data, area, currency, vat, use_subunit, reference_time, hass, session)
        
        # Add metadata
        if result:
            result["data_source"] = "ENTSO-E"
            result["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            result["currency"] = currency
            result["api_key_valid"] = True
        
        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from ENTSO-E."""
    api_key = config.get(Config.API_KEY) or config.get("api_key")
    if not api_key:
        _LOGGER.debug("No API key provided for ENTSO-E, skipping")
        return None

    if reference_time is None:
        reference_time = datetime.datetime.now(datetime.timezone.utc)
    
    today = reference_time
    tomorrow = today + datetime.timedelta(days=1)

    # Format dates for ENTSO-E API (YYYYMMDDHHMM format)
    period_start = today.strftime(TimeFormat.ENTSOE_DATE_HOUR)
    period_end = tomorrow.strftime(TimeFormat.ENTSOE_DATE_HOUR)

    # Map our area code to ENTSO-E area code
    entsoe_area = AreaMapping.ENTSOE_MAPPING.get(area, area)
    
    _LOGGER.debug(f"Using ENTSO-E area code {entsoe_area} for area {area}")

    # Build query parameters
    params = {
        "securityToken": api_key,
        "documentType": EntsoE.DOCUMENT_TYPE_DAY_AHEAD,
        "in_Domain": entsoe_area,
        "out_Domain": entsoe_area,
        "periodStart": period_start,
        "periodEnd": period_end,
    }

    # Use custom headers for ENTSO-E API
    headers = {
        "User-Agent": Network.Defaults.USER_AGENT,
        "Accept": ContentType.XML,
        "Content-Type": ContentType.XML
    }

    response = await client.fetch(
        BASE_URL,
        params=params,
        headers=headers,
        timeout=Network.Defaults.TIMEOUT
    )

    if not response:
        _LOGGER.error("ENTSO-E API returned empty response")
        return None

    # Check for authentication errors
    if "Not authorized" in response:
        _LOGGER.error("ENTSO-E API authentication failed: Not authorized. Check your API key.")
        return None
    elif "No matching data found" in response:
        _LOGGER.warning("ENTSO-E API returned: No matching data found")
        return None

    return response

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session):
    """Process XML data from ENTSO-E."""
    if not data:
        return None

    try:
        # The XML has a default namespace
        nsmap = {
            EntsoE.XMLNS_NS: EntsoE.NS_URN
        }

        # Parse XML
        root = ET.fromstring(data)

        # Find TimeSeries elements
        time_series_elements = root.findall(f".//{EntsoE.XMLNS_NS}:TimeSeries", nsmap)

        if not time_series_elements:
            _LOGGER.error("No TimeSeries elements found in ENTSO-E response")
            return None

        now = reference_time or datetime.datetime.now(datetime.timezone.utc)
        if hass:
            now = localize_datetime(now, hass)
        current_hour = now.hour

        # Store data from all TimeSeries to compare
        all_hourly_prices = []

        # Process each TimeSeries to find the best one
        for ts_index, ts in enumerate(time_series_elements):
            # Extract metadata
            business_type = _find_element_text(ts, f".//{EntsoE.XMLNS_NS}:businessType", nsmap, "unknown")
            curve_type = _find_element_text(ts, f".//{EntsoE.XMLNS_NS}:curveType", nsmap, "unknown")
            entsoe_currency = _find_element_text(ts, f".//{EntsoE.XMLNS_NS}:currency_Unit.name", nsmap, Currency.EUR)
            unit_name = _find_element_text(ts, f".//{EntsoE.XMLNS_NS}:price_Measure_Unit.name", nsmap, "unknown")

            # Process periods in this time series
            hourly_prices = {}
            metadata = {
                "business_type": business_type,
                "curve_type": curve_type,
                "currency": entsoe_currency,
                "unit": unit_name,
                "index": ts_index
            }

            # Find Period elements
            period_elements = ts.findall(f".//{EntsoE.XMLNS_NS}:Period", nsmap)
            if not period_elements:
                continue

            for period in period_elements:
                # Get timeInterval
                interval = period.find(f"{EntsoE.XMLNS_NS}:timeInterval", nsmap)
                if interval is None:
                    continue

                # Get start and end times
                start_element = interval.find(f"{EntsoE.XMLNS_NS}:start", nsmap)
                end_element = interval.find(f"{EntsoE.XMLNS_NS}:end", nsmap)
                if start_element is None or end_element is None:
                    continue

                # Parse times
                try:
                    start_dt = parse_datetime(start_element.text)
                    end_dt = parse_datetime(end_element.text)
                except ValueError:
                    continue

                # Get resolution
                resolution_element = period.find(f"{EntsoE.XMLNS_NS}:resolution", nsmap)
                resolution_minutes = 60  # Default hourly

                # Process Point elements (price points)
                points = period.findall(f"{EntsoE.XMLNS_NS}:Point", nsmap)
                for point in points:
                    position_element = point.find(f"{EntsoE.XMLNS_NS}:position", nsmap)
                    price_element = point.find(f"{EntsoE.XMLNS_NS}:price.amount", nsmap)

                    if position_element is None or price_element is None:
                        continue

                    try:
                        position = int(position_element.text)
                        price = float(price_element.text)
                        
                        # Calculate the time for this position
                        position_minutes = (position - 1) * resolution_minutes
                        position_time = start_dt + datetime.timedelta(minutes=position_minutes)
                        
                        # Convert to local time
                        local_time = position_time
                        if hass:
                            local_time = localize_datetime(position_time, hass)
                        
                        # Format hour string
                        hour_str = f"{local_time.hour:02d}:00"
                        hourly_prices[hour_str] = price
                    except (ValueError, TypeError):
                        continue

            # Store this TimeSeries prices for comparison
            if hourly_prices:
                all_hourly_prices.append({
                    "metadata": metadata,
                    "prices": hourly_prices
                })

        # Select the best TimeSeries
        selected_series = _select_best_time_series(all_hourly_prices)
        if not selected_series:
            _LOGGER.error("Failed to identify any valid price TimeSeries")
            return None

        # Process the selected series
        hourly_prices = selected_series["prices"]
        entsoe_currency = selected_series["metadata"]["currency"]

        # Initialize result structure
        result = {
            "current_price": None,
            "next_hour_price": None,
            "day_average_price": None,
            "peak_price": None,
            "off_peak_price": None,
            "hourly_prices": {},
            "raw_values": {},
            "raw_prices": []
        }

        # Check if we have exactly 24 prices
        if len(hourly_prices) != 24 and len(hourly_prices) > 0:
            _LOGGER.warning(f"Expected 24 hourly prices, got {len(hourly_prices)}. Prices may be incomplete.")

        # Process each hour in the selected series
        all_converted_prices = []
        for hour_str, price in hourly_prices.items():
            hour = int(hour_str.split(":")[0])

            # Create timestamp for raw prices array
            hour_time = datetime.datetime.combine(
                now.date(),
                datetime.time(hour=hour)
            )
            if hass:
                hour_time = localize_datetime(hour_time, hass)
            end_time = hour_time + datetime.timedelta(hours=1)

            # Store raw price
            result["raw_prices"].append({
                "start": hour_time.isoformat(),
                "end": end_time.isoformat(),
                "price": price
            })

            # Convert price
            converted_price = await async_convert_energy_price(
                price=price,
                from_unit=EnergyUnit.MWH,
                to_unit="kWh",
                from_currency=entsoe_currency,
                to_currency=currency,
                vat=vat,
                to_subunit=use_subunit,
                session=session
            )

            # Store converted price
            result["hourly_prices"][hour_str] = converted_price
            all_converted_prices.append(converted_price)

            # Check if current hour
            if hour == current_hour:
                result["current_price"] = converted_price
                result["raw_values"]["current_price"] = {
                    "raw": price,
                    "unit": f"{entsoe_currency}/MWh",
                    "final": converted_price,
                    "currency": currency,
                    "vat_rate": vat
                }

            # Check if next hour
            next_hour = (current_hour + 1) % 24
            if hour == next_hour:
                result["next_hour_price"] = converted_price
                result["raw_values"]["next_hour_price"] = {
                    "raw": price,
                    "unit": f"{entsoe_currency}/MWh",
                    "final": converted_price,
                    "currency": currency,
                    "vat_rate": vat
                }

        # Calculate statistics
        if all_converted_prices:
            result["day_average_price"] = sum(all_converted_prices) / len(all_converted_prices)
            result["peak_price"] = max(all_converted_prices)
            result["off_peak_price"] = min(all_converted_prices)

            # Raw value details for statistics
            result["raw_values"]["day_average_price"] = {
                "value": result["day_average_price"],
                "calculation": "average of all hourly prices"
            }
            result["raw_values"]["peak_price"] = {
                "value": result["peak_price"],
                "calculation": "maximum of all hourly prices"
            }
            result["raw_values"]["off_peak_price"] = {
                "value": result["off_peak_price"],
                "calculation": "minimum of all hourly prices"
            }

        return result

    except ET.ParseError as e:
        _LOGGER.error(f"Error parsing ENTSO-E XML: {e}")
        return None
    except Exception as e:
        _LOGGER.error(f"Error processing ENTSO-E data: {e}", exc_info=True)
        return None

def _find_element_text(element, path, nsmap, default=None):
    """Helper method to safely extract text from an element."""
    child = element.find(path, nsmap)
    if child is not None:
        return child.text
    return default

def _select_best_time_series(all_series):
    """Select the best TimeSeries to use for price data."""
    if not all_series:
        return None

    # If only one series, use it
    if len(all_series) == 1:
        return all_series[0]

    # First try to identify by businessType
    # A62 (Day-ahead allocation) is the correct spot price data
    for series in all_series:
        if series["metadata"]["business_type"] == EntsoE.BUSINESS_TYPE_DAY_AHEAD_ALLOCATION:
            return series

    # Next, try A44 (Day-ahead)
    for series in all_series:
        if series["metadata"]["business_type"] == EntsoE.BUSINESS_TYPE_DAY_AHEAD:
            return series

    # Fallback: try a heuristic approach
    # Use overnight prices as a heuristic (should be lower)
    overnight_averages = []
    for series in all_series:
        overnight_prices = []
        for hour_str, price in series["prices"].items():
            hour = int(hour_str.split(":")[0])
            if 0 <= hour <= 6:  # Overnight hours
                overnight_prices.append(price)

        if overnight_prices:
            avg = sum(overnight_prices) / len(overnight_prices)
            overnight_averages.append({
                "series": series,
                "overnight_avg": avg
            })

    # Choose the series with the lowest overnight average
    if overnight_averages:
        overnight_averages.sort(key=lambda x: x["overnight_avg"])
        return overnight_averages[0]["series"]

    # If all else fails, use the first series
    return all_series[0]

async def validate_api_key(api_key, area, session=None):
    """Validate an API key by making a test request."""
    try:
        # Create a simple configuration for validation
        config = {
            "area": area,
            "api_key": api_key
        }
        
        client = ApiClient(session=session)
        try:
            # Try to fetch data
            result = await _fetch_data(client, config, area, None)
            
            # Check if we got a valid response
            if result and isinstance(result, str) and "<Publication_MarketDocument" in result:
                return True
            elif isinstance(result, str) and "Not authorized" in result:
                return False
            elif isinstance(result, str) and "No matching data found" in result:
                # This is a valid key even if there's no data
                return True
            else:
                return False
        finally:
            if not session and client:
                await client.close()
            
    except Exception as e:
        _LOGGER.error(f"API key validation error: {e}")
        return False
