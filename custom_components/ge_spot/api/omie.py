"""API Client for OMIE (Operador del Mercado Ibérico de Energía)."""

import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Optional

import aiohttp
import pytz # For timezone handling

# Import external libraries
from omiedata.omie_data import OMIEData
# Import pandas for type checking, required by omiedata
try:
    import pandas as pd
except ImportError:
    # Handle missing pandas - omiedata won't work without it.
    # The error will be properly raised later if needed.
    pd = None


# Import from ge-spot's own modules
from ..const import (
    TIMEZONE_IBERIAN, # Use defined constant for the timezone
    CURRENCY_EUR,     # Use defined constant for the currency
    PRICE_PRECISION,  # Use defined constant for rounding
    API_TIMEOUT,      # Can be used for timeout if executor job supports it (not directly here)
    ENERGY_KILO_WATT_HOUR,
    ENERGY_MEGA_WATT_HOUR, # Used conceptually for conversion
)
from ..errors import CannotConnect, InvalidAuth # Use existing error classes

_LOGGER = logging.getLogger(__name__)

# Factor for converting from MWh to kWh
MWH_TO_KWH_FACTOR = 1000.0

class OMIEApiClient:
    """API Client for fetching spot prices from OMIE using the 'omiedata' library."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        hass, # Home Assistant instance, required for async_add_executor_job
    ) -> None:
        """
        Initialize the OMIE API client.

        Args:
            session: aiohttp client session (may not be used directly for OMIE calls now).
            hass: Home Assistant instance.
        """
        self._session = session # Kept for consistency, but not used directly here
        self._hass = hass
        self._omie = OMIEData() # Instantiate the omiedata client
        # Get the pytz timezone object from the constant
        try:
            self._iberian_tz = pytz.timezone(TIMEZONE_IBERIAN)
        except pytz.UnknownTimeZoneError:
            _LOGGER.error("Unknown timezone specified for Iberian market: %s. Falling back to UTC.", TIMEZONE_IBERIAN)
            self._iberian_tz = pytz.utc # Fallback, but should not happen with "Europe/Madrid"

    def _sync_get_and_process_omie_data(self, target_date: date) -> Optional[Dict[datetime, float]]:
        """
        Synchronous method to fetch and process OMIE data for a given date.
        Intended to be run within hass.async_add_executor_job.

        Args:
            target_date: The date for which to fetch prices.

        Returns:
            A dictionary mapping UTC datetime objects to prices in EUR/kWh,
            or an empty dictionary if no data is available yet,
            or raises CannotConnect if a critical error occurs.

        Raises:
            CannotConnect: If connection or data retrieval/processing fails critically,
                           or if pandas dependency is missing.
        """
        # Check if pandas is available (dependency of omiedata)
        if pd is None:
            _LOGGER.error("Pandas library not found. Please ensure 'omiedata' dependencies are installed via manifest.json.")
            raise CannotConnect("Missing dependency (pandas) for OMIE data processing.")

        _LOGGER.debug("Executing synchronous OMIE data fetch for date: %s", target_date)
        prices_dict: Dict[datetime, float] = {}
        try:
            # Use the omiedata library to fetch prices
            # query_marginal_price returns a pandas DataFrame
            # with timestamps (index) in local time (CET/CEST)
            df_prices = self._omie.query_marginal_price(
                start_date=target_date, end_date=target_date
            )

            if df_prices is None or df_prices.empty:
                _LOGGER.warning("No OMIE marginal price data returned for %s.", target_date)
                # It's normal for data to be missing early in the day before publication.
                # Return an empty dict to signal "no data yet".
                return {}

            # Verify that the index is a DatetimeIndex and handle timezones robustly
            if not isinstance(df_prices.index, pd.DatetimeIndex):
                 _LOGGER.error("OMIE data index is not a DatetimeIndex for %s.", target_date)
                 raise CannotConnect(f"Unexpected data format from OMIE for {target_date}")

            if df_prices.index.tz is None:
                _LOGGER.warning("OMIE data index is timezone naive for %s. Assuming Iberian time.", target_date)
                # Try to localize to Iberian time if timezone is missing
                try:
                    df_prices.index = df_prices.index.tz_localize(self._iberian_tz)
                except Exception as tz_err:
                    _LOGGER.error("Failed to localize OMIE timestamp index for %s: %s", target_date, tz_err)
                    raise CannotConnect(f"Could not handle timezone for OMIE data on {target_date}") from tz_err
            elif str(df_prices.index.tz) != str(self._iberian_tz): # Compare string representations for safety
                 _LOGGER.warning(
                     "OMIE data index has unexpected timezone '%s' for %s. Attempting conversion from %s.",
                     df_prices.index.tz, target_date, self._iberian_tz
                 )
                 # Try to convert to the expected timezone before UTC conversion
                 try:
                     df_prices.index = df_prices.index.tz_convert(self._iberian_tz)
                 except Exception as tz_err:
                     _LOGGER.error("Failed to convert OMIE timestamp index timezone for %s: %s", target_date, tz_err)
                     raise CannotConnect(f"Could not handle timezone conversion for OMIE data on {target_date}") from tz_err

            # Process each hour from the DataFrame
            for timestamp_local, row in df_prices.iterrows():
                price_mwh = row.get("price") # Get the price for the hour

                if price_mwh is not None and isinstance(price_mwh, (int, float)):
                    # Convert the local timestamp (CET/CEST) to UTC
                    # timestamp_local is now guaranteed to be a timezone-aware pandas Timestamp
                    timestamp_utc = timestamp_local.tz_convert(pytz.utc).to_pydatetime() # Convert to standard datetime

                    # Convert price from EUR/MWh to EUR/kWh
                    price_kwh = round(price_mwh / MWH_TO_KWH_FACTOR, PRICE_PRECISION)

                    # Store in dictionary with UTC timestamp as key
                    prices_dict[timestamp_utc] = price_kwh
                else:
                    _LOGGER.warning(
                        "Missing or invalid price value (%s) for timestamp %s on %s.",
                        price_mwh,
                        timestamp_local.strftime("%Y-%m-%d %H:%M:%S %Z%z"), # Include timezone in log
                        target_date,
                    )

            _LOGGER.info(
                "Successfully fetched and processed %d OMIE spot prices for %s.",
                len(prices_dict),
                target_date,
            )
            return prices_dict

        except Exception as e:
            # Catch all other errors from the library or processing
            _LOGGER.error("Failed to fetch or process OMIE data for %s: %s", target_date, e, exc_info=True)
            # Map to CannotConnect or a more specific error if needed
            raise CannotConnect(f"Failed to get OMIE data for {target_date}: {e!s}") from e


    async def async_get_spot_prices(self) -> Dict[datetime, float]:
        """
        Fetch spot prices for the next day from OMIE (asynchronously).

        Uses omiedata library running in executor thread pool.

        Returns:
            A dictionary mapping UTC datetime objects to spot prices in EUR/kWh.
            Returns an empty dictionary if data is not available yet or an error occurs
            that is handled within the sync processing (like no data found).

        Raises:
            CannotConnect: If the background task fails critically (e.g., dependency missing,
                           major processing error, unexpected exception during await).
            TimeoutError: If the background task times out (less likely without explicit timeout).
        """
        _LOGGER.debug("Requesting asynchronous fetch of tomorrow's OMIE spot prices.")
        prices: Dict[datetime, float] = {}
        try:
            # Determine tomorrow's date based on the current time in the Iberian timezone
            # This ensures we query for the correct day according to OMIE's publication time.
            # Use datetime.now(self._iberian_tz) for robustness.
            today_local = datetime.now(self._iberian_tz).date()
            target_date = today_local + timedelta(days=1)
            _LOGGER.debug("Target date for OMIE prices: %s", target_date)

            # Run the synchronous data fetching and processing in Home Assistant's executor thread pool
            # to avoid blocking the async event loop. API_TIMEOUT is not used directly here.
            result = await self._hass.async_add_executor_job(
                self._sync_get_and_process_omie_data, target_date
            )

            # If _sync_get_and_process_omie_data returns None or raises an error,
            # it will be handled by the except blocks below. If it returns
            # a dictionary (even empty), it's assigned to 'prices'.
            if result is not None: # Should always return dict now, but check for safety
                prices = result

        except CannotConnect as e:
             # The error was already logged in the synchronous function or during dependency check. Re-raise.
             _LOGGER.warning("Could not connect or fetch OMIE data: %s", e)
             raise # Let the calling code (e.g., GEApiClient) handle this
        except TimeoutError:
             # If the executor job were to time out (unlikely without specific timeout)
             _LOGGER.error("Timeout occurred while fetching OMIE data for target date %s", target_date)
             raise CannotConnect("Timeout while fetching OMIE data") from None # Re-raise as CannotConnect
        except Exception as e:
            # Catch unexpected errors during the async operation itself
            _LOGGER.exception("Unexpected error during async OMIE price fetching: %s", e)
            raise CannotConnect(f"Unexpected error fetching OMIE prices: {e!s}") from e

        # Return the fetched price list (can be empty if no data was found yet)
        return prices
