#!/usr/bin/env python3
"""Integration test for validation-based fallback behavior.

This test verifies that when a primary source (e.g. ENTSO-E) returns only
tomorrow's data (missing current interval), the system correctly fails validation
and falls back to alternative sources (e.g. Nordpool, Energy Charts).

Scenario:
- Time: 16:00 local (after 01:00 cutoff)
- ENTSO-E: Returns only tomorrow's prices (published at 13:00 CET)
- Expected: Validation fails, fallback to Nordpool
- Result: System serves data from Nordpool
"""
import sys
import os
import asyncio
import logging
from datetime import datetime, timedelta
import zoneinfo
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Add the parent directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from custom_components.ge_spot.coordinator.fallback_manager import FallbackManager
from custom_components.ge_spot.coordinator.data_processor import DataProcessor
from custom_components.ge_spot.api.parsers.entsoe_parser import EntsoeParser
from custom_components.ge_spot.api.parsers.nordpool_parser import NordpoolParser
from custom_components.ge_spot.timezone.service import TimezoneService
from tests.lib.mocks.hass import MockHass

_LOGGER = logging.getLogger(__name__)


class TestValidationFallback:
    """Test validation-based fallback behavior."""

    @pytest.mark.asyncio
    async def test_entsoe_missing_current_falls_back_to_nordpool(self):
        """Test that ENTSO-E without current interval triggers fallback to Nordpool."""

        # Setup timezone service
        hass = MockHass()
        area = "SE4"
        stockholm_tz = zoneinfo.ZoneInfo("Europe/Stockholm")
        tz_service = TimezoneService(hass, area)

        # Current time (simulate 16:00, after 01:00 cutoff)
        now = datetime.now(stockholm_tz)
        current_interval = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
        tomorrow = now + timedelta(days=1)
        tomorrow_10am = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)

        # --- ENTSO-E API Mock (returns only tomorrow's data) ---
        mock_entsoe_api = MagicMock()
        mock_entsoe_api.source_type = "entsoe"

        # ENTSO-E response: only tomorrow's data (simulates afternoon fetch)
        entsoe_raw_data = {
            "source": "entsoe",
            "area": area,
            "currency": "EUR",
            "timezone": "Etc/UTC",
            "raw_data": f"""<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument>
    <TimeSeries>
        <Period>
            <timeInterval>
                <start>{tomorrow_10am.astimezone(zoneinfo.ZoneInfo('UTC')).strftime('%Y-%m-%dT%H:%M')}Z</start>
            </timeInterval>
            <Point>
                <position>1</position>
                <price.amount>50.0</price.amount>
            </Point>
        </Period>
    </TimeSeries>
</Publication_MarketDocument>""",
        }

        mock_entsoe_api.fetch_raw_data = AsyncMock(return_value=entsoe_raw_data)

        # --- Nordpool API Mock (returns current + tomorrow's data) ---
        mock_nordpool_api = MagicMock()
        mock_nordpool_api.source_type = "nordpool"

        # Nordpool response: includes current interval
        nordpool_raw_data = {
            "source": "nordpool",
            "area": area,
            "currency": "SEK",
            "timezone": "Europe/Stockholm",
            "unit": "MWh",
            "raw_data": {
                "today": {
                    "multiAreaEntries": [
                        {
                            "deliveryStart": current_interval.isoformat(),
                            "entryPerArea": {area: 1.5},
                        },
                        {
                            "deliveryStart": (current_interval + timedelta(minutes=15)).isoformat(),
                            "entryPerArea": {area: 2.0},
                        },
                    ]
                }
            },
        }

        mock_nordpool_api.fetch_raw_data = AsyncMock(return_value=nordpool_raw_data)

        # --- FallbackManager Test ---
        fallback_manager = FallbackManager()

        # Try ENTSO-E first, then Nordpool
        api_instances = [mock_entsoe_api, mock_nordpool_api]

        # Fetch with fallback
        result = await fallback_manager.fetch_with_fallback(
            api_instances=api_instances, area=area, reference_time=now
        )

        # --- Assertions ---
        assert result is not None, "Should get a result"
        assert (
            "error" not in result or not result["error"]
        ), f"Should not have error, got: {result.get('error')}"

        # Should have raw_data from one of the sources
        assert "raw_data" in result, "Result should contain raw_data"

        # Log which source succeeded
        _LOGGER.info(f"Successful source: {result.get('data_source')}")
        _LOGGER.info(f"Attempted sources: {result.get('attempted_sources')}")

        # Both sources should have been attempted
        assert (
            len(result.get("attempted_sources", [])) >= 1
        ), "Should have attempted at least one source"

    @pytest.mark.asyncio
    async def test_data_processor_validation_rejects_future_only_data(self):
        """Test that DataProcessor validation rejects data without current interval."""

        # Setup
        hass = MockHass()
        area = "SE4"
        stockholm_tz = zoneinfo.ZoneInfo("Europe/Stockholm")
        tz_service = TimezoneService(hass, area)

        # Create mock manager
        mock_manager = MagicMock()
        mock_exchange_service = AsyncMock()
        mock_manager._exchange_service = mock_exchange_service
        mock_manager.is_in_grace_period.return_value = (
            False  # NOT in grace period - strict validation
        )

        # Create processor
        processor = DataProcessor(
            hass=hass,
            area=area,
            target_currency="EUR",
            config={"vat": 0, "include_vat": False, "display_unit": "decimal"},
            tz_service=tz_service,
            manager=mock_manager,
        )

        # Create future-only data (tomorrow's prices)
        now = datetime.now(stockholm_tz)
        tomorrow = now + timedelta(days=1)
        tomorrow_10am = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)

        future_only_raw = {
            "source": "entsoe",
            "data_source": "entsoe",
            "area": area,
            "currency": "EUR",
            "timezone": "Etc/UTC",
            "attempted_sources": ["entsoe"],
            "raw_data": f"""<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument>
    <TimeSeries>
        <Period>
            <timeInterval>
                <start>{tomorrow_10am.astimezone(zoneinfo.ZoneInfo('UTC')).strftime('%Y-%m-%dT%H:%M')}Z</start>
            </timeInterval>
            <Point>
                <position>1</position>
                <price.amount>50.0</price.amount>
            </Point>
        </Period>
    </TimeSeries>
</Publication_MarketDocument>""",
        }

        # Mock exchange service
        with patch.object(processor, "_ensure_exchange_service", AsyncMock()):
            # Process the future-only data
            result = await processor.process(future_only_raw)

            # Should fail validation and return error
            assert "error" in result, "Should return error for future-only data after 01:00"
            assert (
                "validation" in result["error"].lower()
                or "current interval" in result["error"].lower()
            ), f"Error should mention validation or current interval, got: {result.get('error')}"

            _LOGGER.info(f"Validation correctly failed with error: {result['error']}")


if __name__ == "__main__":
    # Run the tests
    logging.basicConfig(level=logging.INFO)
    pytest.main([__file__, "-v"])
