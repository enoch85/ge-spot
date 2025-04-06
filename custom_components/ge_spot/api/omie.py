"""API Client for OMIE (Operador del Mercado Ibérico de Energía) using direct download."""

import asyncio
import csv
import io
import logging
from datetime import datetime, timedelta, time
from typing import Dict, Optional

import aiohttp
import pytz # For timezone handling

# Import from ge-spot's own modules
from ..const import (
    OMIE_AREAS,
    CURRENCY_EUR,
    PRICE_PRECISION,
    API_TIMEOUT,
    ENERGY_KILO_WATT_HOUR,
    ENERGY_MEGA_WATT_HOUR,
)
from ..errors import CannotConnect, InvalidAuth # Use existing error classes

_LOGGER = logging.getLogger(__name__)

# URL Template for OMIE's daily marginal price file (Intraday Auction 1 - often used for day-ahead)
# Example: https://www.omie.es/sites/default/files/dados/SP/marginalpdbc_20250407.1
OMIE_URL_TEMPLATE = "https://www.omie.es/sites/default/files/dados/SP/marginalpdbc_{date_str}.1"

# Factor for converting from MWh to kWh
MWH_TO_KWH_FACTOR = 1000.0

class OMIEApiClient:
    """API Client for fetching spot prices from OMIE by downloading the file directly."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        hass, # Keep hass even if not used directly, as GEApiClient passes it
    ) -> None:
        """
        Initialize the OMIE API client.

        Args:
            session: aiohttp client session provided by Home Assistant.
            hass: Home Assistant instance (passed by GEApiClient).
        """
        self._session = session
        self._hass = hass # Store hass for potential future use or consistency
        # Get the pytz timezone object from the constant
        try:
            self._iberian_tz = pytz.timezone(TIMEZONE_IBERIAN)
        except pytz.UnknownTimeZoneError:
            _LOGGER.error("Unknown timezone specified for Iberian market: %s. Falling back to UTC.", TIMEZONE_IBERIAN)
            self._iberian_tz = pytz.utc

    async def async_get_spot_prices(self) -> Dict[datetime, float]:
        """
        Fetch spot prices for the next day from OMIE by downloading and parsing the file.

        Returns:
            A dictionary mapping UTC datetime objects to spot prices in EUR/kWh.
            Returns an empty dictionary if data is not available or an error occurs.

        Raises:
            CannotConnect: If connection or data retrieval/processing fails critically.
        """
        _LOGGER.debug("Attempting to fetch spot prices for tomorrow (OMIE - Direct Download)")
        prices: Dict[datetime, float] = {}

        try:
            # 1. Determine tomorrow's date
            # Use local Iberian time to determine the correct date OMIE uses
            # Ensure datetime.now() gets the correct timezone context if running elsewhere.
            # Using the timezone object directly is robust.
            now_local = datetime.now(self._iberian_tz)
            tomorrow = now_local + timedelta(days=1)
            date_str = tomorrow.strftime("%Y%m%d")
            url = OMIE_URL_TEMPLATE.format(date_str=date_str)
            _LOGGER.debug("Fetching OMIE data from URL: %s", url)

            # 2. Fetch data using aiohttp session
            # Use headers to mimic a browser slightly, might help avoid blocking
            headers = {"User-Agent": "Home Assistant Custom Component"}
            async with self._session.get(url, timeout=API_TIMEOUT, headers=headers) as resp:
                # Check for HTTP errors
                if resp.status != 200:
                    _LOGGER.error(
                        "Failed to fetch OMIE data for %s. Status code: %d %s",
                        date_str, resp.status, resp.reason
                    )
                    # Raise CannotConnect for specific errors if needed, otherwise return empty
                    # Common issue: 404 Not Found if file isn't published yet.
                    if resp.status == 404:
                        _LOGGER.warning("OMIE file for %s not found (likely not published yet).", date_str)
                        return {} # Return empty dict, not an error
                    else:
                        # Log content for unexpected errors if useful
                        # content_sample = await resp.text(encoding='latin-1', errors='ignore')[:200]
                        # _LOGGER.error("Unexpected HTTP response content sample: %s", content_sample)
                        raise CannotConnect(f"HTTP Error {resp.status} fetching OMIE data.")

                # Read response text, try latin-1 encoding often used in Spanish sources
                try:
                    raw_data = await resp.text(encoding='latin-1')
                except UnicodeDecodeError:
                    _LOGGER.warning("Failed to decode OMIE data as latin-1, trying default encoding.")
                    raw_data = await resp.text()


                # Check for empty or unexpected content (sometimes OMIE returns error pages)
                if not raw_data or "<!DOCTYPE html" in raw_data.lower() or "<html" in raw_data.lower():
                    _LOGGER.warning("Received empty or non-data (HTML?) response from OMIE URL for %s.", date_str)
                    return {}

                # 3. Parse the CSV-like data
                # OMIE files often use ';' as delimiter and might have header/footer lines.
                # Example format slice:
                # ...
                # marginalpdbc;2025;04;07;1;100.00;100.00;;;
                # marginalpdbc;2025;04;07;2;105.50;105.50;;;
                # ...
                # Use StringIO to treat the string data like a file
                file_like_data = io.StringIO(raw_data)
                # Skip potential header lines if they don't start with the expected prefix
                valid_lines = [line for line in file_like_data if line.strip().startswith("marginalpdbc")]
                if not valid_lines:
                     _LOGGER.warning("No valid data lines found in OMIE response for %s.", date_str)
                     return {}

                # Process valid lines using csv reader
                reader = csv.reader(valid_lines, delimiter=';', skipinitialspace=True)

                for row in reader:
                    # Basic validation for expected number of columns (adjust if needed)
                    if len(row) < 6:
                        _LOGGER.warning("Skipping row with unexpected number of columns: %s", row)
                        continue

                    try:
                        # Extract relevant fields (indices based on example format)
                        year = int(row[1])
                        month = int(row[2])
                        day = int(row[3])
                        hour_1_based = int(row[4]) # OMIE uses 1-24 for hours
                        price_str = row[5] # Price in EUR/MWh, potentially with ',' as decimal

                        # Validate extracted data slightly
                        if not (2000 < year < 2100 and 1 <= month <= 12 and 1 <= day <= 31 and 1 <= hour_1_based <= 24):
                            _LOGGER.warning("Skipping row with invalid date/hour values: %s", row)
                            continue

                        # Adjust hour to be 0-23 for datetime object
                        hour_0_based = hour_1_based - 1

                        # Construct local datetime (aware of Iberian timezone)
                        # This assumes the date/time in the file *is* Iberian time
                        dt_local = self._iberian_tz.localize(
                            datetime(year, month, day, hour_0_based)
                        )

                        # Convert price string (e.g., "105,50" or "105.50") to float
                        # Handle both comma and dot as decimal separators
                        price_mwh = float(price_str.replace(',', '.'))

                        # Convert price to EUR/kWh
                        price_kwh = round(price_mwh / MWH_TO_KWH_FACTOR, PRICE_PRECISION)

                        # Convert timestamp to UTC
                        dt_utc = dt_local.astimezone(pytz.utc)

                        # Store the price
                        prices[dt_utc] = price_kwh

                    except (ValueError, IndexError, TypeError) as parse_err:
                        _LOGGER.warning(
                            "Skipping row due to parsing error: %s. Row: %s",
                            parse_err, row, exc_info=False # Set exc_info=True for more detail if needed
                        )
                        continue # Skip to next row on error

                if not prices:
                     _LOGGER.warning("Processed OMIE file for %s but extracted no valid prices.", date_str)
                     return {} # Return empty if parsing succeeded but found nothing valid

                _LOGGER.info(
                    "Successfully processed %d OMIE prices for %s via direct download.",
                    len(prices),
                    date_str,
                )

        except aiohttp.ClientError as http_err:
            _LOGGER.error("Network error fetching OMIE data: %s", http_err)
            raise CannotConnect(f"Network error fetching OMIE data: {http_err}") from http_err
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout fetching OMIE data from URL: %s", url)
            raise CannotConnect("Timeout fetching OMIE data") from None
        except csv.Error as csv_err:
             _LOGGER.error("Error parsing OMIE CSV data: %s", csv_err)
             raise CannotConnect(f"Could not parse OMIE data: {csv_err}") from csv_err
        except Exception as e:
            # Catch any other unexpected error during the process
            _LOGGER.exception("Unexpected error fetching or processing OMIE data: %s", e)
            raise CannotConnect(f"Unexpected error processing OMIE data: {e!s}") from e

        return prices
