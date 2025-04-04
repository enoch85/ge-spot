import logging
import datetime
import json
import asyncio
from .base import BaseEnergyAPI
from ..utils.currency_utils import async_convert_energy_price
from ..const import REGION_TO_CURRENCY, CURRENCY_SUBUNIT_NAMES

_LOGGER = logging.getLogger(__name__)

class EnergiDataServiceAPI(BaseEnergyAPI):
    """API handler for Energi Data Service."""

    BASE_URL = "https://api.energidataservice.dk/dataset/Elspotprices"

    async def _fetch_data(self):
        """Fetch data from Energi Data Service."""
        now = self._get_now()
        today = now.strftime("%Y-%m-%d")
        tomorrow = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        area = self.config.get("area", "DK1")  # Default to Western Denmark

        params = {
            "start": f"{today}T00:00",
            "end": f"{tomorrow}T00:00",
            "filter": json.dumps({"PriceArea": area}),
            "sort": "HourDK",
            "timezone": "dk",
        }

        _LOGGER.debug(f"Fetching Energi Data Service with params: {params}")

        url = self.BASE_URL

        # Add retry mechanism
        retry_count = 3
        for attempt in range(retry_count):
            try:
                async with self.session.get(url, params=params, timeout=30) as response:
                    if response.status != 200:
                        _LOGGER.error(f"Error fetching from Energi Data Service (attempt {attempt+1}/{retry_count}): {response.status}")
                        if attempt < retry_count - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        return None

                    return await response.json()
            except asyncio.TimeoutError:
                _LOGGER.error(f"Timeout fetching from Energi Data Service (attempt {attempt+1}/{retry_count})")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise
            except Exception as e:
                _LOGGER.error(f"Error fetching from Energi Data Service (attempt {attempt+1}/{retry_count}): {e}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise

        return None

    async def _process_data(self, data):
        """Process the data from Energi Data Service."""
        if not data or "records" not in data or not data["records"]:
            return None

        records = data["records"]
        now = self._get_now()
        current_hour = now.replace(minute=0, second=0, microsecond=0)

        # Find current price
        current_price = None
        next_hour_price = None
        hourly_prices = {}
        all_prices = []
        raw_values = {}
        raw_prices = []

        use_cents = self.config.get("price_in_cents", False)
        area = self.config.get("area", "DK1")
        target_currency = REGION_TO_CURRENCY.get(area, "DKK")  # Default to DKK for Danish data

        # Extract exchange rate if available
        exchange_rate = None
        if "currency" in data and data["currency"] != target_currency:
            api_currency = data.get("currency", "DKK")
            if "exchangeRate" in data:
                try:
                    exchange_rate = float(data["exchangeRate"])
                    _LOGGER.debug(f"Using exchange rate from API: {exchange_rate}")
                except (ValueError, TypeError):
                    _LOGGER.warning(f"Invalid exchange rate in API data: {data.get('exchangeRate')}")
        else:
            api_currency = "DKK"  # Default for this API

        vat_rate = self.vat  # Extract VAT from self

        for record in records:
            hour_dk = datetime.datetime.fromisoformat(record["HourDK"].replace("Z", "+00:00"))

            # Store raw price from API
            raw_price = record.get("SpotPriceDKK", 0)
            if not isinstance(raw_price, (int, float)):
                try:
                    raw_price = float(raw_price)
                except (ValueError, TypeError):
                    _LOGGER.warning(f"Invalid price value: {raw_price}")
                    continue

            # Store the record in raw prices list
            raw_prices.append({
                "start": hour_dk.isoformat(),
                "end": (hour_dk + datetime.timedelta(hours=1)).isoformat(),
                "price": raw_price
            })

            # Use comprehensive conversion function
            price = await async_convert_energy_price(
                price=raw_price,
                from_unit="MWh",
                to_unit="kWh",
                from_currency=api_currency,
                to_currency=target_currency,
                vat=vat_rate,
                to_subunit=use_cents,
                exchange_rate=exchange_rate,
                session=self.session
            )

            all_prices.append(price)

            # Store in hourly prices
            hour_str = hour_dk.strftime("%H:%M")
            hourly_prices[hour_str] = price

            # Check if this is current hour
            if hour_dk.hour == current_hour.hour and hour_dk.day == current_hour.day:
                current_price = price
                raw_values["current_price"] = {
                    "raw": raw_price,
                    "unit": f"{api_currency}/MWh",
                    "final": price,
                    "currency": target_currency if not use_cents else CURRENCY_SUBUNIT_NAMES.get(target_currency, "cents"),
                    "vat_rate": vat_rate
                }

            # Check if this is next hour
            next_hour = current_hour + datetime.timedelta(hours=1)
            if hour_dk.hour == next_hour.hour and hour_dk.day == next_hour.day:
                next_hour_price = price
                raw_values["next_hour_price"] = {
                    "raw": raw_price,
                    "unit": f"{api_currency}/MWh",
                    "final": price,
                    "currency": target_currency if not use_cents else CURRENCY_SUBUNIT_NAMES.get(target_currency, "cents"),
                    "vat_rate": vat_rate
                }

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
            "raw_prices": raw_prices,
            "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "raw_api_response": data  # Store raw API response
        }
