"""API handler for OMIE (Operador del Mercado Ibérico de Energía)."""
import logging
import datetime
import csv
import io
from typing import Optional, Dict, Any

from .base import BaseEnergyAPI
from ..timezone import localize_datetime, parse_datetime
from ..price.conversion import async_convert_energy_price
from ..const import (
    Timezone,
    Config,
    DisplayUnit,
    Currency,
    EnergyUnit
)

_LOGGER = logging.getLogger(__name__)

class OmieConstants:
    """Constants for OMIE API."""
    DEFAULT_AREA = "ES"
    BASE_URL_TEMPLATE = "https://www.omie.es/sites/default/files/dados/AGNO_{year}/MES_{month}/TXT/INT_PBC_EV_H_1_{day}_{month}_{year}_{day}_{month}_{year}.TXT"
    PRICE_FIELD_ES = "Precio marginal en el sistema español (EUR/MWh)"
    PRICE_FIELD_PT = "Precio marginal en el sistema portugués (EUR/MWh)"
    DEFAULT_TIMEOUT = 30

class OmieAPI(BaseEnergyAPI):
    """API handler for OMIE."""

    async def _fetch_data(self):
        """Fetch data from OMIE."""
        try:
            # Get proper date in the local timezone of the area (ES/PT)
            now = self._get_now()
            area = self.config.get("area", OmieConstants.DEFAULT_AREA)

            # Format dates for OMIE files
            target_date = now.date()
            year = str(target_date.year)
            month = str.zfill(str(target_date.month), 2)
            day = str.zfill(str(target_date.day), 2)
            date_format = f"{day}_{month}_{year}"

            # Build OMIE URL using template
            url = OmieConstants.BASE_URL_TEMPLATE.format(
                year=year, month=month, day=day
            )

            _LOGGER.debug(f"Fetching OMIE data from URL: {url}")

            # Fetch data with built-in retry mechanism
            response = await self.data_fetcher.fetch_with_retry(
                url, 
                timeout=OmieConstants.DEFAULT_TIMEOUT
            )

            # OMIE returns HTML for non-existent files rather than 404
            if not response:
                _LOGGER.warning(f"No response from OMIE for {date_format}")
                return None

            if isinstance(response, str) and ("<html" in response.lower() or "<!doctype" in response.lower()):
                _LOGGER.warning(f"HTML response from OMIE for {date_format}, likely data not available yet")
                return None

            return {
                "raw_data": response,
                "date_str": date_format,
                "target_date": target_date,
                "url": url
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
            target_date = data["target_date"]

            # Process CSV-like data (OMIE uses ; as delimiter)
            file_like_data = io.StringIO(raw_data)
            lines = file_like_data.readlines()

            # Check if we have valid data
            if len(lines) < 3:
                _LOGGER.warning(f"Not enough data lines in OMIE response")
                return None

            # OMIE format: Skip first 2 lines (header), then read CSV
            csv_data = lines[2:]
            reader = csv.reader(csv_data, delimiter=';', skipinitialspace=True)

            hourly_prices = {}
            all_prices = []
            raw_prices = []
            current_price = None
            next_hour_price = None
            raw_values = {}

            now = self._get_now()
            current_hour = now.hour
            next_hour = (current_hour + 1) % 24

            # Determine if we should convert to subunit
            use_subunit = None
            if Config.DISPLAY_UNIT in self.config:
                use_subunit = self.config[Config.DISPLAY_UNIT] == DisplayUnit.CENTS
            else:
                use_subunit = self.config.get("price_in_cents", False)

            # Process each row looking for Spanish/Portuguese price data based on area
            area = self.config.get("area", OmieConstants.DEFAULT_AREA)
            price_field_name = OmieConstants.PRICE_FIELD_ES
            if area == "PT":
                price_field_name = OmieConstants.PRICE_FIELD_PT

            for row in reader:
                if len(row) < 6:
                    continue

                # Look for the specified price data row
                row_name = row[0] if row else ""
                if price_field_name in row_name:
                    try:
                        # Process hourly prices (values start from position 1)
                        prices = []
                        for val in row[1:]:
                            if not val.strip():
                                continue
                            try:
                                # Handle comma decimal separator
                                prices.append(float(val.replace(',', '.')))
                            except (ValueError, TypeError):
                                prices.append(None)

                        # Store prices for each hour
                        for hour, price in enumerate(prices):
                            if price is None:
                                continue

                            # Create timestamp for this hour
                            dt_local = datetime.datetime.combine(target_date, datetime.time(hour, 0))

                            # Store raw price data
                            raw_prices.append({
                                "start": dt_local.isoformat(),
                                "end": (dt_local + datetime.timedelta(hours=1)).isoformat(),
                                "price": price
                            })

                            # Convert price using core conversion function directly
                            converted_price = await async_convert_energy_price(
                                price=price,
                                from_unit=EnergyUnit.MWH,
                                to_unit="kWh",
                                from_currency=Currency.EUR,
                                to_currency=self._currency,
                                vat=self.vat,
                                to_subunit=use_subunit,
                                session=self.session,
                                exchange_rate=None
                            )

                            hour_str = f"{hour:02d}:00"
                            hourly_prices[hour_str] = converted_price
                            all_prices.append(converted_price)

                            # Check if this is current hour
                            if hour == current_hour:
                                current_price = converted_price
                                raw_values["current_price"] = {
                                    "raw": price,
                                    "unit": f"{Currency.EUR}/MWh",
                                    "final": converted_price,
                                    "currency": self._currency,
                                    "vat_rate": self.vat
                                }

                            # Check if this is next hour
                            if hour == next_hour:
                                next_hour_price = converted_price
                                raw_values["next_hour_price"] = {
                                    "raw": price,
                                    "unit": f"{Currency.EUR}/MWh",
                                    "final": converted_price,
                                    "currency": self._currency,
                                    "vat_rate": self.vat
                                }

                        # We found the row we needed, can break now
                        break
                    except Exception as e:
                        _LOGGER.warning(f"Error processing OMIE price row: {e}")
                        continue

            if not all_prices:
                _LOGGER.warning(f"No valid prices extracted from OMIE data")
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
                "data_source": "OMIE",
                "currency": self._currency
            }

        except Exception as e:
            _LOGGER.error(f"Error processing OMIE data: {e}", exc_info=True)
            return None
