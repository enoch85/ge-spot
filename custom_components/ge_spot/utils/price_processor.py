"""Price data processor for standardizing energy price data."""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from homeassistant.util import dt as dt_util
from ..const import AREA_TIMEZONES, REGION_TO_CURRENCY, CURRENCY_SUBUNIT_NAMES
from .currency_utils import async_convert_energy_price

_LOGGER = logging.getLogger(__name__)

class PriceProcessor:
    """Process price data into standardized format."""

    def __init__(self, area: str, currency: str, vat: float = 0.0, use_subunit: bool = False, session = None):
        """Initialize the price processor.

        Args:
            area: The price area code
            currency: The target currency for prices
            vat: VAT rate to apply (0-1)
            use_subunit: Whether to convert to subunit
            session: Optional aiohttp session for currency conversion
        """
        self.area = area
        self.currency = currency
        self.vat = vat
        self.use_subunit = use_subunit
        self.session = session

    async def process_hourly_data(self, entries: List[Dict], base_currency: str = "EUR", base_unit: str = "MWh") -> Tuple[Dict, List, List]:
        """Process hourly price entries.

        Args:
            entries: List of price entries
            base_currency: Source currency of the price data
            base_unit: Energy unit of the price data

        Returns:
            Tuple of (hourly_prices, raw_prices, all_prices)
        """
        hourly_prices = {}
        raw_prices = []
        all_prices = []

        for entry in entries:
            # Extract timestamp and price
            start_time = entry.get("start")
            end_time = entry.get("end")
            price = entry.get("price")

            if not start_time or not price:
                _LOGGER.warning(f"Skipping entry without required data: {entry}")
                continue

            # Parse datetime if needed
            if isinstance(start_time, str):
                try:
                    timestamp = dt_util.parse_datetime(start_time)
                    if timestamp is None:
                        _LOGGER.warning(f"Could not parse timestamp: {start_time}")
                        continue
                except ValueError:
                    _LOGGER.warning(f"Invalid timestamp format: {start_time}")
                    continue
            else:
                timestamp = start_time

            # Convert price value to float if needed
            if not isinstance(price, (float, int)):
                try:
                    price = float(price)
                except (ValueError, TypeError):
                    _LOGGER.warning(f"Invalid price value: {price}")
                    continue

            # Store raw price
            raw_prices.append({
                "start": timestamp.isoformat() if hasattr(timestamp, "isoformat") else timestamp,
                "end": (timestamp + timedelta(hours=1)).isoformat() if hasattr(timestamp, "isoformat") else end_time,
                "price": price
            })

            # Convert price using comprehensive conversion function
            try:
                converted_price = await async_convert_energy_price(
                    price=price,
                    from_unit=base_unit,
                    to_unit="kWh",
                    from_currency=base_currency,
                    to_currency=self.currency,
                    vat=self.vat,
                    to_subunit=self.use_subunit,
                    session=self.session
                )

                # Format hour string and store
                if hasattr(timestamp, "hour"):
                    hour = timestamp.hour
                    hour_str = f"{hour:02d}:00"
                    hourly_prices[hour_str] = converted_price
                    all_prices.append(converted_price)

            except Exception as e:
                _LOGGER.error(f"Error converting price: {e}")
                continue

        return hourly_prices, raw_prices, all_prices

    def calculate_statistics(self, prices: List[float]) -> Dict:
        """Calculate statistics for a list of prices."""
        if not prices:
            return {
                "average": None,
                "min": None,
                "max": None
            }

        return {
            "average": sum(prices) / len(prices),
            "min": min(prices),
            "max": max(prices)
        }

    def convert_to_local_time(self, dt: datetime) -> datetime:
        """Convert a timestamp to the local timezone for this area."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_util.UTC)

        tz_name = AREA_TIMEZONES.get(self.area, "UTC")
        try:
            local_tz = dt_util.get_time_zone(tz_name)
            return dt.astimezone(local_tz)
        except (ImportError, AttributeError):
            # Fallback if dt_utils is not available
            return dt

# Utility functions for processing specific API data

async def process_nordpool_data(raw_data: Dict, area: str, currency: str, vat: float = 0.0, use_subunit: bool = False, session = None) -> Dict:
    """Process Nordpool data into standardized format."""
    if not raw_data or "today" not in raw_data:
        return None

    today_data = raw_data["today"]
    tomorrow_data = raw_data.get("tomorrow")

    if "multiAreaEntries" not in today_data:
        _LOGGER.error("Missing multiAreaEntries in Nordpool data")
        return None

    now = datetime.now()
    current_hour = now.hour

    # Create processor
    processor = PriceProcessor(area, currency, vat, use_subunit, session)

    # Result container
    result = {
        "current_price": None,
        "next_hour_price": None,
        "day_average_price": None,
        "peak_price": None,
        "off_peak_price": None,
        "hourly_prices": {},
        "last_updated": raw_data.get("timestamp"),
        "raw_today": [],
        "raw_tomorrow": [],
        "raw_values": {}
    }

    # Process today's entries
    today_entries = []
    for entry in today_data.get("multiAreaEntries", []):
        if not isinstance(entry, dict) or "entryPerArea" not in entry:
            continue

        if area not in entry["entryPerArea"]:
            continue

        today_entries.append({
            "start": entry.get("deliveryStart"),
            "end": entry.get("deliveryEnd"),
            "price": entry["entryPerArea"][area]
        })

    # Process hourly data for today
    hourly_prices, raw_prices, all_prices = await processor.process_hourly_data(
        today_entries, base_currency="EUR", base_unit="MWh"
    )

    # Store results
    result["hourly_prices"] = hourly_prices
    result["raw_today"] = raw_prices

    # Extract current and next-hour prices
    current_hour_str = f"{current_hour:02d}:00"
    next_hour_str = f"{(current_hour + 1) % 24:02d}:00"

    result["current_price"] = hourly_prices.get(current_hour_str)
    result["next_hour_price"] = hourly_prices.get(next_hour_str)

    # Store raw value information
    if current_hour_str in hourly_prices:
        result["raw_values"]["current_price"] = {
            "hour": current_hour_str,
            "value": result["current_price"]
        }

    if next_hour_str in hourly_prices:
        result["raw_values"]["next_hour_price"] = {
            "hour": next_hour_str,
            "value": result["next_hour_price"]
        }

    # Calculate statistics
    if all_prices:
        stats = processor.calculate_statistics(all_prices)
        result["day_average_price"] = stats["average"]
        result["peak_price"] = stats["max"]
        result["off_peak_price"] = stats["min"]

        # Store raw values for statistics
        result["raw_values"]["day_average_price"] = {
            "value": stats["average"],
            "calculation": "average of all hourly prices"
        }
        result["raw_values"]["peak_price"] = {
            "value": stats["max"],
            "calculation": "maximum of all hourly prices"
        }
        result["raw_values"]["off_peak_price"] = {
            "value": stats["min"],
            "calculation": "minimum of all hourly prices"
        }

    # Process tomorrow's data if available
    if tomorrow_data and "multiAreaEntries" in tomorrow_data:
        tomorrow_entries = []
        for entry in tomorrow_data.get("multiAreaEntries", []):
            if not isinstance(entry, dict) or "entryPerArea" not in entry:
                continue

            if area not in entry["entryPerArea"]:
                continue

            tomorrow_entries.append({
                "start": entry.get("deliveryStart"),
                "end": entry.get("deliveryEnd"),
                "price": entry["entryPerArea"][area]
            })

        # Process hourly data for tomorrow
        tomorrow_hourly_prices, tomorrow_raw_prices, tomorrow_all_prices = await processor.process_hourly_data(
            tomorrow_entries, base_currency="EUR", base_unit="MWh"
        )

        result["tomorrow_hourly_prices"] = tomorrow_hourly_prices
        result["raw_tomorrow"] = tomorrow_raw_prices

        # Calculate tomorrow statistics
        if tomorrow_all_prices:
            tomorrow_stats = processor.calculate_statistics(tomorrow_all_prices)
            result["tomorrow_average_price"] = tomorrow_stats["average"]
            result["tomorrow_peak_price"] = tomorrow_stats["max"]
            result["tomorrow_off_peak_price"] = tomorrow_stats["min"]
            result["tomorrow_valid"] = len(tomorrow_all_prices) >= 20  # At least 20 hours

            # Store raw values for tomorrow statistics
            result["raw_values"]["tomorrow_average_price"] = {
                "value": tomorrow_stats["average"],
                "calculation": "average of all tomorrow's prices"
            }
            result["raw_values"]["tomorrow_peak_price"] = {
                "value": tomorrow_stats["max"],
                "calculation": "maximum of all tomorrow's prices"
            }
            result["raw_values"]["tomorrow_off_peak_price"] = {
                "value": tomorrow_stats["min"],
                "calculation": "minimum of all tomorrow's prices"
            }

    # Include meta-information
    target_currency = REGION_TO_CURRENCY.get(area, currency)
    result["state_class"] = "total"
    result["currency"] = target_currency if not use_subunit else CURRENCY_SUBUNIT_NAMES.get(target_currency, "cents")
    result["area"] = area
    result["vat"] = vat
    result["data_source"] = "NordpoolAPI"

    return result
