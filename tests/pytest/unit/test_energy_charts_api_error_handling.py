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

    @pytest.mark.asyncio
    async def test_timeout_error_handled_correctly(self, api, caplog):
        """Test that timeout errors are detected and don't cascade to 'missing fields' error.

        Phase 1.2 fix: API client returns {"error": True, "message": "..."} on timeout.
        This should be detected BEFORE checking for missing fields.
        """
        # Arrange
        mock_client = AsyncMock()
        mock_client.fetch = AsyncMock(
            return_value={
                "error": True,
                "message": "Request timed out",
                "url": "https://api.energy-charts.info/price",
            }
        )

        caplog.clear()

        # Act
        result = await api._fetch_data(
            client=mock_client, area="NL", reference_time=datetime.now(timezone.utc)
        )

        # Assert
        assert result is None, "Should return None on error"

        # Check that we got the timeout error message, not "missing fields"
        error_messages = [
            record.message for record in caplog.records if record.levelname == "ERROR"
        ]

        # Should have exactly one error message about the timeout
        assert (
            len(error_messages) == 1
        ), f"Should have 1 error message, got {len(error_messages)}"
        assert (
            "request failed" in error_messages[0].lower()
        ), "Error message should indicate request failure"
        assert (
            "timed out" in error_messages[0].lower()
            or "timeout" in error_messages[0].lower()
        ), "Error message should mention timeout"

        # Should NOT have "missing required fields" error
        assert not any(
            "missing required fields" in msg.lower() for msg in error_messages
        ), "Should NOT have cascading 'missing fields' error"

    @pytest.mark.asyncio
    async def test_connection_error_handled_correctly(self, api, caplog):
        """Test that connection errors are detected and don't cascade."""
        # Arrange
        mock_client = AsyncMock()
        mock_client.fetch = AsyncMock(
            return_value={
                "error": True,
                "message": "Cannot connect to host",
                "url": "https://api.energy-charts.info/price",
            }
        )

        caplog.clear()

        # Act
        result = await api._fetch_data(
            client=mock_client, area="DE-LU", reference_time=datetime.now(timezone.utc)
        )

        # Assert
        assert result is None

        error_messages = [
            record.message for record in caplog.records if record.levelname == "ERROR"
        ]
        assert len(error_messages) == 1
        assert "request failed" in error_messages[0].lower()
        assert not any(
            "missing required fields" in msg.lower() for msg in error_messages
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
        assert result["raw_data"]["unix_seconds"] == [
            1729414800,
            1729414900,
            1729415000,
        ]

        # Should have no errors
        error_messages = [
            record.message for record in caplog.records if record.levelname == "ERROR"
        ]
        assert len(error_messages) == 0, "Should have no errors for successful response"

    @pytest.mark.asyncio
    async def test_error_check_order(self, api, caplog):
        """Test that error checking happens in correct order.

        Order should be:
        1. Check for error flag from API client
        2. Check for valid response structure
        3. Check for required fields
        """
        # Test case: Response with error flag AND missing fields
        # Should only log the error flag message, not missing fields
        mock_client = AsyncMock()
        mock_client.fetch = AsyncMock(
            return_value={
                "error": True,
                "message": "API rate limit exceeded",
                # Also missing unix_seconds and price, but error flag should be caught first
            }
        )

        caplog.clear()

        # Act
        result = await api._fetch_data(
            client=mock_client, area="AT", reference_time=datetime.now(timezone.utc)
        )

        # Assert
        assert result is None

        error_messages = [
            record.message for record in caplog.records if record.levelname == "ERROR"
        ]
        assert len(error_messages) == 1, "Should have exactly one error"
        assert "request failed" in error_messages[0].lower()
        assert "rate limit" in error_messages[0].lower()
        # Should NOT reach the "missing fields" check
        assert not any(
            "missing required fields" in msg.lower() for msg in error_messages
        )
