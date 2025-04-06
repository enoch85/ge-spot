"""API Client for OMIE (Operador del Mercado Ibérico de Energía) using direct download."""

import asyncio
import csv
import io
import logging
from datetime import datetime, timedelta, time
from typing import Dict, Optional

import aiohttp
import pytz # For timezone handling

# Import from ge-spot's own modules based on user's structure
from ..const import (
    AREA_TIMEZONES,
    CURRENCY_EUR,
    PRICE_PRECISION,
    API_TIMEOUT,
    ENERGY_KILO_WATT_HOUR,
    ENERGY_MEGA_WATT_HOUR,
)
# Attempt to import error classes from likely locations based on complex structure
# Define default dummy classes first
class CannotConnect(Exception): pass
class InvalidAuth(Exception): pass
try:
    from ..exceptions import CannotConnect, InvalidAuth # noqa: F811
    _LOGGER = logging.getLogger(__name__) # Define logger early
    _LOGGER.debug("Importing error classes from exceptions.py for OMIE API")
except ImportError:
    try:
        from ..errors import CannotConnect, InvalidAuth # noqa: F811
        _LOGGER = logging.getLogger(__name__) # Define logger early
        _LOGGER.debug("Importing error classes from errors.py for OMIE API")
    except ImportError:
        _LOGGER = logging.getLogger(__name__) # Define logger early
        _LOGGER.warning("Could not import error classes (CannotConnect, InvalidAuth) from ..exceptions or ..errors for OMIE API")


# URL Template for OMIE's daily marginal price file
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
        """Initialize the OMIE API client."""
        self._session = session
        self._hass = hass
        # Get the pytz timezone object by looking up the ES timezone string
        try:
            # Lookup the timezone string for Spain ("ES") from the imported dictionary
            # Provide a fallback in case "ES" is somehow missing (shouldn't happen if areas.py is correct)
            tz_identifier = AREA_TIMEZONES.get("ES", "Europe/Madrid")
            if not tz_identifier:
                 _LOGGER.error("Timezone identifier for 'ES' is missing in AREA_TIMEZONES. Falling back to Europe/Madrid.")
                 tz_identifier = "Europe/Madrid"

            self._iberian_tz = pytz.timezone(tz_identifier)
            _LOGGER.debug("OMIE API using timezone: %s", tz_identifier)

        except pytz.UnknownTimeZoneError:
            _LOGGER.error("Unknown timezone identifier '%s' found for Iberian market. Falling back to UTC.", tz_identifier)
            self._iberian_tz = pytz.utc
        except NameError:
             # This shouldn't happen if AREA_TIMEZONES imported correctly
             _LOGGER.error("AREA_TIMEZONES dictionary not found after import. Falling back to UTC.")
             self._iberian_tz = pytz.utc

        # Ensure error classes are available
        self._cannot_connect_error = CannotConnect
        self._invalid_auth_error = InvalidAuth


    async def async_get_spot_prices(self): # Removed Dict type hint from return value
        """
        Fetch spot prices for the next day from OMIE by downloading and parsing the file.

        Returns:
            A dictionary mapping UTC datetime objects to spot prices in EUR/kWh,
            or an empty dictionary if data is not available or an error occurs.

        Raises:
            CannotConnect: If connection or data retrieval/processing fails critically.
        """
        _LOGGER.debug("Attempting to fetch spot prices for tomorrow (OMIE - Direct Download)")
        prices = {} # Removed Dict type hint
        url = "" # Define url outside try for logging in exception

        try:
            # 1. Determine tomorrow's date using the looked-up timezone
            now_local = datetime.now(self._iberian_tz)
            tomorrow = now_local + timedelta(days=1)
            date_str = tomorrow.strftime("%Y%m%d")
            url = OMIE_URL_TEMPLATE.format(date_str=date_str)
            _LOGGER.debug("Fetching OMIE data from URL: %s", url)

            # 2. Fetch data using aiohttp session
            headers = {"User-Agent": "Home Assistant Custom Component"}
            # Ensure API_TIMEOUT is imported or defined, use a default if not
            try:
                timeout_seconds = API_TIMEOUT
            except NameError:
                timeout_seconds = 20
                _LOGGER.warning("API_TIMEOUT constant not found, using default %d s.", timeout_seconds)
            timeout = aiohttp.ClientTimeout(total=timeout_seconds)

            async with self._session.get(url, timeout=timeout, headers=headers) as resp:
                if resp.status != 200:
                    _LOGGER.error("Failed fetch OMIE data for %s. Status: %d %s", date_str, resp.status, resp.reason)
                    if resp.status == 404:
                        _LOGGER.warning("OMIE file for %s not found.", date_str)
                        return {}
                    else:
                        raise self._cannot_connect_error(f"HTTP Error {resp.status} fetching OMIE data.")

                try:
                    raw_data = await resp.text(encoding='latin-1')
                except UnicodeDecodeError:
                    _LOGGER.warning("Failed latin-1 decode for OMIE, trying default.")
                    raw_data = await resp.text()

                if not raw_data or "<!DOCTYPE html" in raw_data.lower() or "<html" in raw_data.lower():
                    _LOGGER.warning("Empty or HTML response from OMIE for %s.", date_str)
                    return {}

                # 3. Parse the CSV-like data
                file_like_data = io.StringIO(raw_data)
                valid_lines = [line for line in file_like_data if line.strip().startswith("marginalpdbc") and len(line.split(';')) >= 6]
                if not valid_lines:
                     _LOGGER.warning("No valid data lines in OMIE response for %s.", date_str)
                     return {}

                reader = csv.reader(valid_lines, delimiter=';', skipinitialspace=True)
                # Ensure PRICE_PRECISION is available, use default if not
                try:
                    price_precision = PRICE_PRECISION
                except NameError:
                    price_precision = 5
                    _LOGGER.warning("PRICE_PRECISION constant not found, using default %d.", price_precision)

                for row in reader:
                    if len(row) < 6: continue
                    try:
                        year, month, day, hour_1_based = map(int, row[1:5])
                        price_str = row[5]

                        if not (2000 < year < 2100 and 1 <= month <= 12 and 1 <= day <= 31 and 1 <= hour_1_based <= 24):
                            _LOGGER.warning("Invalid date/hour in OMIE row: %s", row)
                            continue

                        hour_0_based = hour_1_based - 1
                        dt_local = self._iberian_tz.localize(datetime(year, month, day, hour_0_based))
                        price_mwh = float(price_str.replace(',', '.'))
                        price_kwh = round(price_mwh / MWH_TO_KWH_FACTOR, price_precision)
                        dt_utc = dt_local.astimezone(pytz.utc)
                        prices[dt_utc] = price_kwh
                    except (ValueError, IndexError, TypeError) as parse_err:
                        _LOGGER.warning("Parsing error on OMIE row: %s. Row: %s", parse_err, row)
                        continue

                if not prices:
                     _LOGGER.warning("No valid prices extracted from OMIE file for %s.", date_str)
                     return {}

                _LOGGER.info("Processed %d OMIE prices for %s.", len(prices), date_str)

        except aiohttp.ClientError as http_err:
            _LOGGER.error("Network error fetching OMIE data from URL %s: %s", url, http_err)
            raise self._cannot_connect_error(f"Network error fetching OMIE data: {http_err}") from http_err
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout fetching OMIE data from URL: %s", url)
            raise self._cannot_connect_error("Timeout fetching OMIE data") from None
        except csv.Error as csv_err:
             _LOGGER.error("CSV Error parsing OMIE data from URL %s: %s", url, csv_err)
             raise self._cannot_connect_error(f"Could not parse OMIE data: {csv_err}") from csv_err
        except Exception as e:
            _LOGGER.exception("Unexpected error processing OMIE data from URL %s: %s", url, e)
            raise self._cannot_connect_error(f"Unexpected error processing OMIE data: {e!s}") from e

        return prices
