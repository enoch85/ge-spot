# tests/integration/test_sensor_setup.py
"""Tests for the GE Spot sensor platform setup."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.const import Platform

from custom_components.ge_spot.const import DOMAIN, Config
from custom_components.ge_spot.coordinator import UnifiedPriceCoordinator
from datetime import timedelta
from unittest.mock import AsyncMock, patch, MagicMock

# Define mock data that the coordinator would typically provide
MOCK_COORDINATOR_DATA = {
    "area": "SE4",
    "currency": "SEK",
    "current_price": 123.45,
    "next_hour_price": 130.00,
    "today_stats": {
        "average": 110.5,
        "min": 90.0,
        "max": 150.0,
        "min_timestamp": "2025-04-25T03:00:00+00:00",
        "max_timestamp": "2025-04-25T18:00:00+00:00",
        "current": 123.45, # Ensure current is present for difference/percent sensors
        "peak": {"average": 140.0},
        "off_peak": {"average": 100.0},
    },
    "hour_stats": { # For OffPeakPeakSensor attributes
        "peak_avg": 140.0,
        "off_peak_avg": 100.0,
    },
    "tomorrow_valid": False,
    "source": "mock_source",
    "timezone": "Europe/Stockholm",
    "vat_included": False,
    "has_data": True,
    "error": None,
    # Add other keys expected by sensors if necessary
}

@pytest.mark.asyncio
async def test_sensor_platform_setup(hass, monkeypatch):
    # Patch _EXCHANGE_SERVICE.get_rates and get_exchange_service before anything else
    from custom_components.ge_spot.utils import exchange_service as exch_mod
    mock_exchange_service = MagicMock()
    mock_exchange_service.get_rates = AsyncMock(return_value=None)
    mock_exchange_service.close = AsyncMock(return_value=None)
    monkeypatch.setattr(exch_mod, "_EXCHANGE_SERVICE", mock_exchange_service)
    monkeypatch.setattr(exch_mod, "get_exchange_service", AsyncMock(return_value=mock_exchange_service))

    # --- Setup Mock Config Entry ---
    config_data = {
        Config.AREA: "SE4",
        Config.CURRENCY: "SEK",
        # Add other necessary config options if needed by the setup process
    }
    options_data = {
        Config.INCLUDE_VAT: False,
        Config.VAT: 25,
        Config.DISPLAY_UNIT: "decimal",
        Config.PRECISION: 2,
        # Add other options used in sensor/electricity.py
    }
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        data=config_data,
        options=options_data,
        entry_id="test_entry_123"
    )
    mock_entry.add_to_hass(hass)

    # --- Setup Mock Coordinator ---
    # Create a real coordinator instance but prevent it from fetching
    # We will manually set its data
    coordinator = UnifiedPriceCoordinator(
        hass=hass,
        area=mock_entry.data[Config.AREA],
        currency=mock_entry.data[Config.CURRENCY],
        config=mock_entry.options, # Pass options as config
        update_interval=timedelta(minutes=5)
    )
    # Prevent actual fetching during test setup
    coordinator.async_config_entry_first_refresh = lambda: None
    coordinator.async_refresh = lambda: None
    # Set the mock data
    coordinator.data = MOCK_COORDINATOR_DATA
    # Store coordinator in hass.data as the integration __init__ would
    hass.data.setdefault(DOMAIN, {})[mock_entry.entry_id] = coordinator

    # --- Load the Integration (including sensor platform) ---
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done() # Wait for setup to complete

    # --- Assertions ---
    # 1. Check if the sensor platform was set up (no exceptions occurred)
    #    If async_setup raised an error, the test would fail before this point.
    assert mock_entry.state == pytest.importorskip("homeassistant.config_entries").ConfigEntryState.LOADED

    # 2. Check if sensor entities were created
    #    Verify based on the sensors defined in sensor/electricity.py
    #    (Adjust names/count based on actual sensors created)
    expected_sensors = [
        "sensor.gespot_se4_current_price_se4",
        "sensor.gespot_se4_next_hour_price_se4",
        "sensor.gespot_average_price_se4",
        "sensor.gespot_se4_peak_price_se4",
        "sensor.gespot_se4_off_peak_price_se4",
        "sensor.gespot_peak_offpeak_se4",
        "sensor.gespot_price_difference_se4",
        "sensor.gespot_price_percentage_se4",
    ]
    for entity_id in expected_sensors:
        state = hass.states.get(entity_id)
        assert state is not None, f"Sensor entity {entity_id} was not created."

    # --- Cleanup (Optional but good practice) ---
    # Unload the config entry
    await hass.config_entries.async_unload(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.state == pytest.importorskip("homeassistant.config_entries").ConfigEntryState.NOT_LOADED
