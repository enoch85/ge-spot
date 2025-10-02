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
    "next_interval_price": 130.00,
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
    """Test that sensor platform can be set up without errors."""
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
    }
    options_data = {
        Config.INCLUDE_VAT: False,
        Config.VAT: 25,
        Config.DISPLAY_UNIT: "decimal",
        Config.PRECISION: 2,
    }
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        data=config_data,
        options=options_data,
        entry_id="test_entry_123"
    )
    mock_entry.add_to_hass(hass)

    # --- Setup Mock Coordinator ---
    # Mock the coordinator completely to avoid background tasks
    mock_coordinator = MagicMock(spec=UnifiedPriceCoordinator)
    mock_coordinator.data = MOCK_COORDINATOR_DATA
    mock_coordinator.async_config_entry_first_refresh = AsyncMock()
    mock_coordinator.async_add_listener = MagicMock()
    mock_coordinator.async_remove_listener = MagicMock()
    
    # Store coordinator in hass.data as the integration __init__ would
    hass.data.setdefault(DOMAIN, {})[mock_entry.entry_id] = mock_coordinator

    # Mock the integration's async_setup_entry to avoid full setup
    with patch("custom_components.ge_spot.async_setup_entry", return_value=True):
        setup_result = await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

    # --- Assertions ---
    assert setup_result is True, "Config entry setup should return True"
    assert mock_entry.state == pytest.importorskip("homeassistant.config_entries").ConfigEntryState.LOADED

    # --- Cleanup ---
    with patch("custom_components.ge_spot.async_unload_entry", return_value=True):
        unload_result = await hass.config_entries.async_unload(mock_entry.entry_id)
        await hass.async_block_till_done()
    
    assert unload_result is True, "Config entry unload should return True"
