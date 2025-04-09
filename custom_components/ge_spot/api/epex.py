"""API handler for EPEX SPOT."""
import logging
import datetime
from bs4 import BeautifulSoup
from .base import BaseEnergyAPI
from ..const import (
    Config,
    Currency,
    EnergyUnit
)

_LOGGER = logging.getLogger(__name__)

class EpexAPI(BaseEnergyAPI):
    """API handler for EPEX SPOT."""

    BASE_URL = "https://www.epexspot.com/en/market-results"

    async def _fetch_data(self):
        """Fetch data from EPEX SPOT."""
        area = self.config.get("area", "SE4")
        now = self._get_now()

        # Format dates for the query
        trading_date = now.strftime("%Y-%m-%d")
        delivery_date = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

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

        try:
            html_content = await self.data_fetcher.fetch_with_retry(self.BASE_URL, params=params)
            if not html_content:
                return None
            return html_content
        except Exception as e:
            _LOGGER.error(f"Error fetching from EPEX SPOT: {e}")
            return None

    async def _process_data(self, data):
        """Process the data from EPEX SPOT."""
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

            # Process rows with price data
            hourly_prices = {}
            all_prices = []
            raw_prices = []
            raw_values = {}

            now = self._get_now()
            current_hour = now.hour

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
                    end_time = start_time + datetime.timedelta(hours=1)

                    # Store raw price data
                    raw_prices.append({
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat(),
                        "price": price
                    })

                    # EPEX prices are in EUR/MWh
                    api_currency = Currency.EUR
                    from_unit = EnergyUnit.MWH

                    # Convert price using centralized method
                    converted_price = await self._convert_price(
                        price=price,
                        from_currency=api_currency,
                        from_unit=from_unit
                    )

                    # Format hour string and store price
                    hour_str = f"{hour:02d}:00"
                    hourly_prices[hour_str] = converted_price
                    all_prices.append(converted_price)

                    # Check if this is current hour
                    if hour == current_hour:
                        current_price = converted_price
                        raw_values["current_price"] = {
                            "raw": price,
                            "unit": f"{api_currency}/{from_unit}",
                            "final": converted_price,
                            "currency": self._currency,
                            "vat_rate": self.vat
                        }

                    # Check if this is next hour
                    next_hour = (current_hour + 1) % 24
                    if hour == next_hour:
                        next_hour_price = converted_price
                        raw_values["next_hour_price"] = {
                            "raw": price,
                            "unit": f"{api_currency}/{from_unit}",
                            "final": converted_price,
                            "currency": self._currency,
                            "vat_rate": self.vat
                        }

                except Exception as e:
                    _LOGGER.warning(f"Error processing row {i}: {e}")

            if not all_prices:
                _LOGGER.error("No prices found in EPEX data")
                return None

            # Calculate statistics
            day_average_price = sum(all_prices) / len(all_prices) if all_prices else None
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

            current_hour_str = f"{current_hour:02d}:00"
            next_hour_str = f"{(current_hour + 1) % 24:02d}:00"

            return {
                "current_price": hourly_prices.get(current_hour_str),
                "next_hour_price": hourly_prices.get(next_hour_str),
                "day_average_price": day_average_price,
                "peak_price": peak_price,
                "off_peak_price": off_peak_price,
                "hourly_prices": hourly_prices,
                "raw_prices": raw_prices,
                "raw_values": raw_values,
                "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "data_source": "EPEX SPOT",
                "currency": self._currency
            }

        except Exception as e:
            _LOGGER.error(f"Error processing EPEX data: {e}", exc_info=True)
            return None
