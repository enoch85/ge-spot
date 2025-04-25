#!/usr/bin/env python3
"""Tests for the UnifiedPriceManager functionality."""
import sys
import os
import asyncio
import logging
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta, timezone
import pytest

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path so we can import the custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from custom_components.ge_spot.coordinator.unified_price_manager import UnifiedPriceManager
from custom_components.ge_spot.price import ElectricityPriceAdapter
from scripts.tests.mocks.hass import MockHass

class TestUnifiedPriceManager:
    """Test the UnifiedPriceManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MockHass()
        self.config = {
            "display_unit": "decimal",
            # Add your real ENTSO-E API key below for live API tests
            "api_key": "YOUR_ENTSOE_API_KEY",
        }
        with patch('custom_components.ge_spot.api.get_sources_for_region') as mock_get_sources:
            mock_get_sources.return_value = ["nordpool", "entsoe"]
            self.manager = UnifiedPriceManager(
                hass=self.hass,
                area="SE1",
                currency="SEK",
                config=self.config,
            )

    def test_init(self):
        assert self.manager.area == "SE1"
        assert self.manager.currency == "SEK"
        assert self.manager._active_source is None
        assert self.manager._attempted_sources == []
        assert self.manager._fallback_sources == []

    @pytest.mark.asyncio
    async def test_fetch_data_success(self):
        result = await self.manager.fetch_data()
        assert result is not None
        assert self.manager._active_source is not None
        assert isinstance(self.manager._attempted_sources, list)
        # Optionally, check for expected keys in result
        assert "hourly_prices" in result

    @pytest.mark.asyncio
    async def test_fetch_data_failure(self):
        # Simulate a failure by using an invalid area or removing API key
        original_area = self.manager.area
        self.manager.area = "INVALID_AREA"
        result = await self.manager.fetch_data()
        assert result is not None  # Should return an empty result dict
        assert self.manager._consecutive_failures >= 1
        self.manager.area = original_area

    @pytest.mark.asyncio
    async def test_process_result(self):
        result = {
            "source": "test_source",
            "area": "SE1",
            "currency": "SEK",
            "hourly_prices": {"10:00": 1.0, "11:00": 2.0}
        }
        self.manager._data_processor.process = AsyncMock(return_value={"processed": True})
        processed = await self.manager._process_result(result)
        self.manager._data_processor.process.assert_awaited_once_with(result)
        assert processed == {"processed": True}

    @pytest.mark.asyncio
    async def test_fetch_with_tomorrow_data(self):
        result = await self.manager.fetch_data()
        assert result is not None
        # Check for tomorrow data if available
        if "tomorrow_hourly_prices" in result:
            assert isinstance(result["tomorrow_hourly_prices"], dict)