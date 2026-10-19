#!/usr/bin/env python3
"""Tests for Energy-Charts API error handling.

These tests verify that the Energy-Charts API correctly handles errors
and doesn't produce cascading error messages.

Phase 1.2 fix: API client timeout/error responses should be detected
before checking for missing fields.
"""

import sys
import os
import asyncio
import logging
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone
import pytest

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from custom_components.ge_spot.api.energy_charts import EnergyChartsAPI


class TestEnergyChartsErrorHandling:
    """Test Energy-Charts API error handling."""

    @pytest.fixture
    def api(self):
        """Create an EnergyChartsAPI instance for testing."""
        return EnergyChartsAPI(config={})

    @pytest.mark.parametrize(
        "status,message",
        [
            (None, "Request timed out"),
            (None, "Cannot connect to host"),
            (429, "Too Many Requests"),
            (404, "no content available"),
            (503, "Service unavailable"),
        ],
    )
    async def test_handled_request_failure_is_debug_without_cascading_errors(
        self, api, caplog, status, message
    ):
        client = AsyncMock()
        client.fetch.return_value = {
            "error": True,
            "status_code": status,
            "message": message,
        }
        with caplog.at_level(logging.DEBUG):
            result = await api._fetch_data(client, "SE4", datetime.now(timezone.utc))
        assert result is None
        assert any(message in record.message for record in caplog.records)
        assert all(record.levelno < logging.WARNING for record in caplog.records)
        assert not any(
            "missing required fields" in record.message for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_invalid_response_structure_handled(self, api, caplog):
        """Test that invalid response structure (not a dict) is handled."""
        # Arrange
        mock_client = AsyncMock()
        mock_client.fetch = AsyncMock(return_value="not a dict")

        caplog.clear()

        # Act
        result = await api._fetch_data(
            client=mock_client, area="FR", reference_time=datetime.now(timezone.utc)
        )

        # Assert
        assert result is None

        error_messages = [
            record.message for record in caplog.records if record.levelname == "ERROR"
        ]
        assert len(error_messages) == 1
        assert "invalid response" in error_messages[0].lower()

    @pytest.mark.asyncio
    async def test_empty_response_handled(self, api, caplog):
        """Test that empty/None response is handled."""
        # Arrange
        mock_client = AsyncMock()
        mock_client.fetch = AsyncMock(return_value=None)

        caplog.clear()

        # Act
        result = await api._fetch_data(
            client=mock_client, area="BE", reference_time=datetime.now(timezone.utc)
        )

        # Assert
        assert result is None

        error_messages = [
            record.message for record in caplog.records if record.levelname == "ERROR"
        ]
        assert len(error_messages) == 1
        assert "invalid response" in error_messages[0].lower()

    @pytest.mark.asyncio
    async def test_missing_fields_error_only_for_valid_response(self, api, caplog):
        """Test that 'missing fields' error only appears for valid dict responses.

        When we get a valid dict (no error flag) but it's missing required fields,
        THEN we should see the 'missing fields' error.
        """
        # Arrange
        mock_client = AsyncMock()
        mock_client.fetch = AsyncMock(
            return_value={
                "some_field": "value",
                # Missing "unix_seconds" and "price" fields
            }
        )

        caplog.clear()

        # Act
        result = await api._fetch_data(
            client=mock_client, area="NL", reference_time=datetime.now(timezone.utc)
        )

        # Assert
        assert result is None

        error_messages = [
            record.message for record in caplog.records if record.levelname == "ERROR"
        ]
        assert len(error_messages) == 1
        assert (
            "missing required fields" in error_messages[0].lower()
        ), "Should have 'missing fields' error for valid dict missing fields"

    @pytest.mark.asyncio
    async def test_successful_response_no_errors(self, api, caplog):
        """Test that successful response with all fields doesn't log errors."""
        # Arrange
        mock_client = AsyncMock()
        mock_client.fetch = AsyncMock(
            return_value={
                "unix_seconds": [1729414800, 1729414900, 1729415000],
                "price": [100.5, 101.2, 99.8],
                "license_info": "CC BY 4.0",
            }
        )

        caplog.clear()

        # Act
        result = await api._fetch_data(
            client=mock_client, area="NL", reference_time=datetime.now(timezone.utc)
        )

        # Assert
        assert result is not None, "Should return data on success"
        assert "raw_data" in result
        # raw_data now has a "today" key that wraps the API response
        assert "today" in result["raw_data"]
        assert result["raw_data"]["today"]["unix_seconds"] == [
            1729414800,
            1729414900,
            1729415000,
        ]

        # Should have no errors
        error_messages = [
            record.message for record in caplog.records if record.levelname == "ERROR"
        ]
        assert len(error_messages) == 0, "Should have no errors for successful response"
