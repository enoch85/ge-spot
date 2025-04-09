"""API handler for EPEX SPOT."""
import logging
import datetime
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional

from ..utils.api_client import ApiClient
from ..price.conversion import async_convert_energy_price
from ..timezone.converters import localize_datetime
from ..const import (
    Config, DisplayUnit, Currency, EnergyUnit
)

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.epexspot.com/en/market-results"

async def fetch_day_ahead_prices(config, area, currency, reference_time=None, hass=None, session=None):
    """Fetch day-ahead prices using EPEX SPOT API."""
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
            result["data_source"] = "EPEX SPOT"
            result["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            result["currency"] = currency
        
        return result
    finally:
        if not session and client:
            await client.close()

async def _fetch_data(client, config, area, reference_time):
    """Fetch data from EPEX SPOT."""
    if reference_time is None:
        reference_time = datetime.datetime.now(datetime.timezone.utc)
    
    # Format dates for the query
    trading_date = reference_time.strftime("%Y-%m-%d")
    delivery_date = (reference_time + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    params = {
        "market_area": area,
        "auction": "MRC",
        "trading_date": trading_date,
        "delivery_date": delivery_date,
        "modality": "Auction",
        "sub_modality": "DayAhead",
        "data_mode": "table"
    }

    _LOGGER.debug(f"Fetching EPEX with params: {params}")

    return await client.fetch(BASE_URL, params=params)

async def _process_data(data, area, currency, vat, use_subunit, reference_time, hass, session):
    """Process data from EPEX SPOT."""
    if not data or not isinstance(data, str):
        _LOGGER.error("No valid HTML data received from EPEX")
        return None

    try:
        # Parse HTML
        soup = BeautifulSoup(data, 'html.parser')

        # Extract time slots
        time_slots = []
        fixed_column = soup.find('div', class_='fixed-column')
        if fixed_column:
            for item in fixed_column.find_all('li'):
                slot_text = item.text.strip()
                if ' - ' in slot_text:
                    time_slots.append(slot_text)

        if not time_slots:
            _LOGGER.error("Could not find time slots in EPEX response")
            return None

        # Find the price table
        table_div = soup.find('div', class_='js-table-values')
        if not table_div or not table_div.find('table'):
            _LOGGER.error("Could not find price table in EPEX response")
            return None

        table = table_div.find('table')
        delivery_date_str = table.get('data-head')

        # Get current time
        now = reference_time or datetime.datetime.now(datetime.timezone.utc)
        if hass:
            now = localize_datetime(now, hass)
        current_hour = now.hour

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

        # Parse delivery date
        delivery_date = None
        if delivery_date_str:
            try:
                parts = delivery_date_str.split('.')
                if len(parts) == 3:
                    day, month, year = map(int, parts)
                    if year < 100:  # Handle 2-digit year
                        year += 2000
                    delivery_date = datetime.date(year, month, day)
            except Exception as e:
                _LOGGER.warning(f"Error parsing delivery date: {e}")

        # Process each row in the table body
        all_prices = []
        hourly_prices = {}
        rows = table.find('tbody').find_all('tr')
        
        for i, row in enumerate(rows):
            if i >= len(time_slots):
                continue

            cells = row.find_all('td')
            if len(cells) < 4:  # Need at least 4 columns
                continue

            try:
                # Parse hour from time slot (format: "HH - HH")
                hour_text = time_slots[i].split(' - ')[0]
                hour = int(hour_text)

                # Get price from the 4th column
                price_text = cells[3].text.strip().replace(',', '.')
                price = float(price_text)

                # Create timestamps
                if delivery_date:
                    start_time = datetime.datetime.combine(delivery_date, datetime.time(hour, 0))
                else:
                    start_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                    
                if hass:
                    start_time = localize_datetime(start_time, hass)
                end_time = start_time + datetime.timedelta(hours=1)

                # Store raw price data
                result["raw_prices"].append({
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "price": price
                })

                # EPEX prices are in EUR/MWh
                api_currency = Currency.EUR
                from_unit = EnergyUnit.MWH

                # Convert price
                converted_price = await async_convert_energy_price(
                    price=price,
                    from_unit=from_unit,
                    to_unit="kWh",
                    from_currency=api_currency,
                    to_currency=currency,
                    vat=vat,
                    to_subunit=use_subunit,
                    session=session
                )

                # Format hour string and store price
                hour_str = f"{hour:02d}:00"
                hourly_prices[hour_str] = converted_price
                all_prices.append(converted_price)

                # Check if current hour
                if hour == current_hour:
                    result["current_price"] = converted_price
                    result["raw_values"]["current_price"] = {
                        "raw": price,
                        "unit": f"{api_currency}/{from_unit}",
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
                        "unit": f"{api_currency}/{from_unit}",
                        "final": converted_price,
                        "currency": currency,
                        "vat_rate": vat
                    }

            except Exception as e:
                _LOGGER.warning(f"Error processing row {i}: {e}")

        if not all_prices:
            _LOGGER.error("No prices found in EPEX data")
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
        _LOGGER.error(f"Error processing EPEX data: {e}", exc_info=True)
        return None
