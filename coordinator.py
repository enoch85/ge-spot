import asyncio
import datetime
import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.util import dt

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class GSpotDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching energy price data."""

    def __init__(self, hass: HomeAssistant, api, update_interval):
        """Initialize."""
        self.api = api
        self.platforms = []
        self._cached_data = None
        self._last_successful_update = None
        self._consecutive_errors = 0
        self._max_consecutive_errors = 3  # Number of errors before using cached data
        self._retry_delay = 300  # 5 minutes delay for retry after error
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=datetime.timedelta(minutes=update_interval),
        )

    async def _async_update_data(self):
        """Update data via API."""
        try:
            # Attempt to get fresh data
            data = await self.api.async_get_data()
            
            if data:
                # Update cache with successful data
                self._cached_data = data
                self._last_successful_update = dt.now()
                self._consecutive_errors = 0
                return data
            else:
                # API returned None, count as an error
                self._consecutive_errors += 1
                _LOGGER.warning(
                    "Failed to retrieve data from %s (attempt %s of %s)",
                    self.api.__class__.__name__,
                    self._consecutive_errors,
                    self._max_consecutive_errors,
                )
                
                if self._consecutive_errors < self._max_consecutive_errors:
                    # Throw error to try again soon
                    raise UpdateFailed(f"No data received from {self.api.__class__.__name__}")
                
                # Return cached data if we have it
                if self._cached_data:
                    _LOGGER.warning(
                        "Using cached data from %s for %s since API is unavailable",
                        self._last_successful_update,
                        self.api.__class__.__name__,
                    )
                    return self._cached_data
                
                # No cached data available
                raise UpdateFailed(f"No data available from {self.api.__class__.__name__}")
                
        except asyncio.TimeoutError as error:
            self._consecutive_errors += 1
            _LOGGER.warning(
                "Timeout error fetching data from %s (attempt %s of %s): %s",
                self.api.__class__.__name__,
                self._consecutive_errors,
                self._max_consecutive_errors,
                error,
            )
            
            # Return cached data if too many consecutive errors
            if self._consecutive_errors >= self._max_consecutive_errors and self._cached_data:
                _LOGGER.warning(
                    "Using cached data from %s for %s due to timeout",
                    self._last_successful_update,
                    self.api.__class__.__name__,
                )
                return self._cached_data
            
            # Schedule a retry sooner than regular interval if we hit a timeout
            if self.update_interval > datetime.timedelta(seconds=self._retry_delay):
                self._schedule_refresh()
                
            raise UpdateFailed(f"Timeout error fetching data: {error}")
            
        except ConfigEntryAuthFailed as auth_error:
            # Don't retry auth failures - user needs to fix configuration
            _LOGGER.error(
                "Authentication error with %s: %s",
                self.api.__class__.__name__,
                auth_error,
            )
            raise
            
        except Exception as err:
            self._consecutive_errors += 1
            _LOGGER.error(
                "Error fetching data from %s (attempt %s of %s): %s",
                self.api.__class__.__name__,
                self._consecutive_errors,
                self._max_consecutive_errors,
                err,
                exc_info=True,
            )
            
            # Return cached data if too many consecutive errors
            if self._consecutive_errors >= self._max_consecutive_errors and self._cached_data:
                _LOGGER.warning(
                    "Using cached data from %s for %s due to error",
                    self._last_successful_update,
                    self.api.__class__.__name__,
                )
                return self._cached_data
                
            # Schedule a retry sooner than regular interval if we hit an error
            if self.update_interval > datetime.timedelta(seconds=self._retry_delay):
                self._schedule_refresh()
                
            raise UpdateFailed(f"Error communicating with API: {err}")
    
    def _schedule_refresh(self):
        """Schedule a refresh after delay.
        
        This is a non-async method that schedules an async refresh.
        """
        if self.update_interval > datetime.timedelta(seconds=self._retry_delay):
            # Use a shorter delay for retries
            delay = self._retry_delay
        else:
            # Use the standard update interval
            delay = self.update_interval.total_seconds()
        
        # Schedule the refresh task
        self.hass.loop.call_later(delay, lambda: self.hass.async_create_task(self.async_refresh()))
