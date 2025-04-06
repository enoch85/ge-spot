"""API handler for EPEX SPOT."""
import logging
import datetime
import asyncio
from bs4 import BeautifulSoup
from .base import BaseEnergyAPI
from ..const import (
    CONF_DISPLAY_UNIT,
    DISPLAY_UNIT_CENTS
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
            # Get display unit setting from config
            display_unit = self.config.get(CONF_DISPLAY_UNIT)
            use_subunit = display_unit == DISPLAY_UNIT_CENTS

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

                    # Add to raw prices
                    raw_prices.append({
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat(),
                        "price": price
                    })

                    # Convert price using centralized method
                    converted_price = await self._convert_price(
                        price=price,
                        from_currency="EUR",
                        from_unit="MWh",
                        to_subunit=use_subunit  # Use the display unit setting
                    )

                    # Format hour string and store price
                    hour_str = f"{hour:02d}:00"
                    hourly_prices[hour_str] = converted_price
                    all_prices.append(converted_price)

                except Exception as e:
                    _LOGGER.warning(f"Error processing row {i}: {e}")

            if not all_prices:
                _LOGGER.error("No prices found in EPEX data")
                return None

            # Calculate statistics and prepare result
            return {
                "current_price": hourly_prices.get(f"{current_hour:02d}:00"),
                "next_hour_price": hourly_prices.get(f"{(current_hour + 1) % 24:02d}:00"),
                "day_average_price": sum(all_prices) / len(all_prices),
                "peak_price": max(all_prices),
                "off_peak_price": min(all_prices),
                "hourly_prices": hourly_prices,
                "raw_prices": raw_prices,
                "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "data_source": "EPEX SPOT",
                "currency": "EUR"
            }

        except Exception as e:
            _LOGGER.error(f"Error processing EPEX data: {e}", exc_info=True)
            return None
