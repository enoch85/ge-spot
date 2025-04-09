"""API handler for OMIE (Operador del Mercado Ibérico de Energía)."""
import logging
import datetime
import csv
import io
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..price.conversion import async_convert_energy_price
from ..timezone.converters import localize_datetime
from ..timezone.parsers import parse_datetime
from ..const import (
    Config, DisplayUnit, Currency, EnergyUnit
)

_LOGGER = logging.getLogger(__name__)

# Constants
DEFAULT_AREA = "ES"
BASE_URL_TEMPLATE = "https://www.omie.es/sites/default/files/dados/AGNO_{year}/MES_{month}/TXT/INT_PBC_EV_H_1_{day}_{month}_{year}_{day}_{month}_{year}.TXT"
PRICE_FIELD_ES = "Precio marginal en el sistema español (EUR/MWh)"
PRICE_FIELD_PT = "Precio marginal en el sistema portugués (EUR/MWh)"

async def fetch_day_ahead_prices(config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using OMIE API."""
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
            result["data_source"] = "OMIE"
            result["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            result["currency"] = currency
        
        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from OMIE."""
    try:
        # Get proper date in the local timezone of the area (ES/PT)
        if reference_time is None:
            reference_time = datetime.datetime.now(datetime.timezone.utc)
        
        # Format dates for OMIE files
        target_date = reference_time.date()
        year = str(target_date.year)
        month = str.zfill(str(target_date.month), 2)
        day = str.zfill(str(target_date.day), 2)
        
        # Build OMIE URL using template
        url = BASE_URL_TEMPLATE.format(
            year=year, month=month, day=day
        )

        _LOGGER.debug(f"Fetching OMIE data from URL: {url}")

        # Fetch data with built-in retry mechanism
        response = await client.fetch(url, timeout=30)

        # OMIE returns HTML for non-existent files rather than 404
        if not response:
            _LOGGER.warning(f"No response from OMIE for {day}_{month}_{year}")
            return None

        if isinstance(response, str) and ("<html" in response.lower() or "<!doctype" in response.lower()):
            _LOGGER.warning(f"HTML response from OMIE for {day}_{month}_{year}, likely data not available yet")
            return None

        return {
            "raw_data": response,
            "date_str": f"{day}_{month}_{year}",
            "target_date": target_date,
            "url": url
        }

    except Exception as e:
        _LOGGER.error(f"Failed to fetch data from OMIE: {e}")
        return None

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session):
    """Process data from OMIE."""
    if not data or "raw_data" not in data:
        return None

    try:
        raw_data = data["raw_data"]
        target_date = data["target_date"]

        # Process CSV-like data (OMIE uses ; as delimiter)
        file_like_data = io.StringIO(raw_data)
        lines = file_like_data.readlines()

        # Check if we have valid data
        if len(lines) < 3:
            _LOGGER.warning(f"Not enough data lines in OMIE response")
            return None

        # Get current time
        now = reference_time or datetime.datetime.now(datetime.timezone.utc)
        if hass:
            now = localize_datetime(now, hass)
        current_hour = now.hour
        next_hour = (current_hour + 1) % 24

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

        # OMIE format: Skip first 2 lines (header), then read CSV
        csv_data = lines[2:]
        reader = csv.reader(csv_data, delimiter=';', skipinitialspace=True)

        # Process each row looking for Spanish/Portuguese price data based on area
        price_field_name = PRICE_FIELD_ES
        if area == "PT":
            price_field_name = PRICE_FIELD_PT

        all_prices = []
        hourly_prices = {}
        
        for row in reader:
            if len(row) < 6:
                continue

            # Look for the specified price data row
            row_name = row[0] if row else ""
            if price_field_name in row_name:
                try:
                    # Process hourly prices (values start from position 1)
                    for hour, val in enumerate(row[1:]):
                        if not val.strip():
                            continue
                            
                        try:
                            # Handle comma decimal separator
                            price = float(val.replace(',', '.'))
                            
                            # Create timestamp for this hour
                            dt_local = datetime.datetime.combine(target_date, datetime.time(hour, 0))
                            if hass:
                                dt_local = localize_datetime(dt_local, hass)
                            
                            # Store raw price data
                            result["raw_prices"].append({
                                "start": dt_local.isoformat(),
                                "end": (dt_local + datetime.timedelta(hours=1)).isoformat(),
                                "price": price
                            })
                            
                            # Convert price
                            converted_price = await async_convert_energy_price(
                                price=price,
                                from_unit=EnergyUnit.MWH,
                                to_unit="kWh",
                                from_currency=Currency.EUR,
                                to_currency=currency,
                                vat=vat,
                                to_subunit=use_subunit,
                                session=session
                            )
                            
                            # Store hourly price
                            hour_str = f"{hour:02d}:00"
                            hourly_prices[hour_str] = converted_price
                            all_prices.append(converted_price)
                            
                            # Check if current hour
                            if hour == current_hour:
                                result["current_price"] = converted_price
                                result["raw_values"]["current_price"] = {
                                    "raw": price,
                                    "unit": f"{Currency.EUR}/MWh",
                                    "final": converted_price,
                                    "currency": currency,
                                    "vat_rate": vat
                                }
                            
                            # Check if next hour
                            if hour == next_hour:
                                result["next_hour_price"] = converted_price
                                result["raw_values"]["next_hour_price"] = {
                                    "raw": price,
                                    "unit": f"{Currency.EUR}/MWh",
                                    "final": converted_price,
                                    "currency": currency,
                                    "vat_rate": vat
                                }
                            
                        except (ValueError, TypeError):
                            continue
                    
                    # We found the row we needed, can break now
                    break
                except Exception as e:
                    _LOGGER.warning(f"Error processing OMIE price row: {e}")
                    continue

        if not all_prices:
            _LOGGER.warning(f"No valid prices extracted from OMIE data")
            return None

        # Check if we have exactly 24 hourly prices
        if len(hourly_prices) != 24 and len(hourly_prices) > 0:
            _LOGGER.warning(f"Expected 24 hourly prices, got {len(hourly_prices)}. Prices may be incomplete.")
        
        # Add hourly prices
        result["hourly_prices"] = hourly_prices

        # Calculate statistics
        result["day_average_price"] = sum(all_prices) / len(all_prices)
        result["peak_price"] = max(all_prices)
        result["off_peak_price"] = min(all_prices)

        # Store raw values for statistics
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

    except Exception as e:
        _LOGGER.error(f"Error processing OMIE data: {e}", exc_info=True)
        return None
