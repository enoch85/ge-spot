"""API handler for OMIE (Operador del Mercado Ibérico de Energía)."""
import logging
import datetime
import asyncio
import csv
import io
from .base import BaseEnergyAPI
from ..utils.currency_utils import async_convert_energy_price
from ..utils.timezone_utils import localize_datetime

_LOGGER = logging.getLogger(__name__)

# URL Template for OMIE's daily marginal price file
OMIE_URL_TEMPLATE = "https://www.omie.es/sites/default/files/dados/SP/marginalpdbc_{date_str}.1"

class OmieAPI(BaseEnergyAPI):
    """API handler for OMIE."""

    async def _fetch_data(self):
        """Fetch data from OMIE."""
        try:
            # Determine tomorrow's date in Iberian timezone
            now = self._get_now()
            tomorrow = now + datetime.timedelta(days=1)
            date_str = tomorrow.strftime("%Y%m%d")

            url = OMIE_URL_TEMPLATE.format(date_str=date_str)
            _LOGGER.debug(f"Fetching OMIE data from URL: {url}")

            # Fetch data with built-in retry mechanism
            response = await self._fetch_with_retry(url, timeout=30)

            if not response or isinstance(response, str) and ("<!DOCTYPE html" in response.lower() or "<html" in response.lower()):
                _LOGGER.warning(f"Empty or HTML response from OMIE for {date_str}.")
                return None

            return {
                "raw_data": response,
                "date_str": date_str,
                "target_date": tomorrow.date()
            }

        except Exception as e:
            _LOGGER.error(f"Failed to fetch data from OMIE: {e}")
            return None

    async def _process_data(self, data):
        """Process the data from OMIE."""
        if not data or "raw_data" not in data:
            return None

        try:
            raw_data = data["raw_data"]
            date_str = data["date_str"]
            target_date = data["target_date"]

            # Process CSV-like data
            file_like_data = io.StringIO(raw_data)
            valid_lines = []

            for line in file_like_data:
                if line.strip().startswith("marginalpdbc") and len(line.split(';')) >= 6:
                    valid_lines.append(line)

            if not valid_lines:
                _LOGGER.warning(f"No valid data lines in OMIE response for {date_str}.")
                return None

            reader = csv.reader(valid_lines, delimiter=';', skipinitialspace=True)

            hourly_prices = {}
            all_prices = []
            raw_prices = []
            current_price = None
            next_hour_price = None
            raw_values = {}

            now = self._get_now()
            current_hour = now.hour
            next_hour = (current_hour + 1) % 24

            for row in reader:
                if len(row) < 6:
                    continue

                try:
                    year, month, day, hour_1_based = map(int, row[1:5])
                    price_str = row[5]

                    if not (2000 < year < 2100 and 1 <= month <= 12 and 1 <= day <= 31 and 1 <= hour_1_based <= 24):
                        _LOGGER.warning(f"Invalid date/hour in OMIE row: {row}")
                        continue

                    hour_0_based = hour_1_based - 1

                    # Create datetime objects
                    dt_local = datetime.datetime(year, month, day, hour_0_based)
                    if hasattr(self, 'hass') and self.hass:
                        dt_local = localize_datetime(dt_local, self.hass)

                    # Parse price value
                    price_mwh = float(price_str.replace(',', '.'))

                    # Store raw price data
                    raw_prices.append({
                        "start": dt_local.isoformat(),
                        "end": (dt_local + datetime.timedelta(hours=1)).isoformat(),
                        "price": price_mwh
                    })

                    # Convert price
                    converted_price = await self._convert_price(
                        price=price_mwh,
                        from_unit="MWh",
                        from_currency="EUR"
                    )

                    hour_str = f"{hour_0_based:02d}:00"
                    hourly_prices[hour_str] = converted_price
                    all_prices.append(converted_price)

                    # Check if this is current hour
                    if hour_0_based == current_hour and dt_local.date() == now.date():
                        current_price = converted_price
                        raw_values["current_price"] = {
                            "raw": price_mwh,
                            "converted": converted_price,
                            "hour": hour_0_based
                        }

                    # Check if this is next hour
                    if hour_0_based == next_hour and dt_local.date() == now.date():
                        next_hour_price = converted_price
                        raw_values["next_hour_price"] = {
                            "raw": price_mwh,
                            "converted": converted_price,
                            "hour": hour_0_based
                        }

                except (ValueError, IndexError, TypeError) as e:
                    _LOGGER.warning(f"Error processing OMIE row: {e}. Row: {row}")
                    continue

            if not all_prices:
                _LOGGER.warning(f"No valid prices extracted from OMIE data for {date_str}")
                return None

            # Calculate day average
            day_average_price = sum(all_prices) / len(all_prices) if all_prices else None

            # Find peak and off-peak prices
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
                "raw_prices": raw_prices,
                "raw_values": raw_values,
                "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "data_source": "OMIE"
            }

        except Exception as e:
            _LOGGER.error(f"Error processing OMIE data: {e}", exc_info=True)
            return None
