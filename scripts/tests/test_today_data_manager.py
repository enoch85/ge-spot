#!/usr/bin/env python3
"""Tests for the TodayDataManager."""
import sys
import os
import asyncio
import unittest
import logging
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the parent directory to Python path so we can import the custom_components
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from custom_components.ge_spot.coordinator.today_data_manager import TodayDataManager
from custom_components.ge_spot.price import ElectricityPriceAdapter

class TestTodayDataManager(unittest.TestCase):
    """Test the TodayDataManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        self.price_cache = MagicMock()
        self.tz_service = MagicMock()
        
        self.config = {
            "display_unit": "decimal"
        }
        
        self.manager = TodayDataManager(
            hass=self.hass,
            area="SE1",
            currency="SEK",
            config=self.config,
            price_cache=self.price_cache,
            tz_service=self.tz_service,
            session=None
        )

    def test_init(self):
        """Test initialization."""
        self.assertEqual(self.manager.area, "SE1")
        self.assertEqual(self.manager.currency, "SEK")
        self.assertEqual(self.manager._active_source, None)
        self.assertEqual(self.manager._attempted_sources, [])
        self.assertEqual(self.manager._fallback_data, {})
        self.assertEqual(self.manager._last_api_fetch, None)

    def test_fetch_data_success(self):
        """Test fetch_data with successful result."""
        # This is a wrapper to run the async test
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._test_fetch_data_success())
        
    @patch('custom_components.ge_spot.coordinator.today_data_manager.FallbackManager')
    async def _test_fetch_data_success(self, mock_fallback_manager):
        """Test fetch_data with successful result."""
        # Mock the FallbackManager
        mock_instance = MagicMock()
        mock_fallback_manager.return_value = mock_instance
        
        # Set up the mock to return a successful result
        mock_result = {
            "data": {"some": "data"},
            "source": "test_source",
            "attempted": ["source1", "source2"],
            "fallback_sources": ["fallback1"],
            "fallback_data_fallback1": {"fallback": "data"}
        }
        
        # Create a coroutine that returns the mock result
        async def mock_fetch():
            return mock_result
            
        mock_instance.fetch_with_fallbacks.return_value = mock_fetch()
        
        # Call the method
        result = await self.manager.fetch_data("test reason")
        
        # Verify the result
        self.assertIsNotNone(result)
        self.assertEqual(self.manager._active_source, "test_source")
        self.assertEqual(self.manager._attempted_sources, ["source1", "source2"])
        self.assertEqual(self.manager._consecutive_failures, 0)
        self.assertEqual(self.manager._fallback_data, {"fallback1": {"fallback": "data"}})
        
        # Verify the cache was updated
        self.price_cache.store.assert_called_once()
        call_args = self.price_cache.store.call_args[0]
        self.assertEqual(call_args[0], {"some": "data"})
        self.assertEqual(call_args[1], "SE1")
        self.assertEqual(call_args[2], "test_source")

    def test_fetch_data_failure(self):
        """Test fetch_data with failure result."""
        # This is a wrapper to run the async test
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._test_fetch_data_failure())
        
    @patch('custom_components.ge_spot.coordinator.today_data_manager.FallbackManager')
    async def _test_fetch_data_failure(self, mock_fallback_manager):
        """Test fetch_data with failure result."""
        # Mock the FallbackManager
        mock_instance = MagicMock()
        mock_fallback_manager.return_value = mock_instance
        
        # Set up the mock to return a failure result
        mock_result = {
            "data": None,
            "source": None,
            "attempted": ["source1", "source2"],
            "skipped_sources": ["source3"]
        }
        
        # Create a coroutine that returns the mock result
        async def mock_fetch():
            return mock_result
            
        mock_instance.fetch_with_fallbacks.return_value = mock_fetch()
        
        # Call the method
        result = await self.manager.fetch_data("test reason")
        
        # Verify the result
        self.assertIsNone(result)  # The method returns None when all sources fail
        self.assertEqual(self.manager._consecutive_failures, 1)
        self.assertIsNotNone(self.manager._last_failure_time)
        
        # Verify the cache was not updated
        self.price_cache.store.assert_not_called()

    def test_get_adapters(self):
        """Test get_adapters method."""
        # Set up test data
        data = {"some": "data"}
        self.manager._fallback_data = {
            "fallback1": {"fallback1": "data"},
            "fallback2": {"fallback2": "data"}
        }
        
        # Mock ElectricityPriceAdapter
        with patch('custom_components.ge_spot.coordinator.today_data_manager.ElectricityPriceAdapter') as mock_adapter:
            # Set up the mock to return different instances
            primary_adapter = MagicMock()
            fallback_adapter1 = MagicMock()
            fallback_adapter2 = MagicMock()
            
            mock_adapter.side_effect = [primary_adapter, fallback_adapter1, fallback_adapter2]
            
            # Call the method
            result_primary, result_fallbacks = self.manager.get_adapters(data)
            
            # Verify the results
            self.assertEqual(result_primary, primary_adapter)
            self.assertEqual(len(result_fallbacks), 2)
            self.assertIn("fallback1", result_fallbacks)
            self.assertIn("fallback2", result_fallbacks)
            self.assertEqual(result_fallbacks["fallback1"], fallback_adapter1)
            self.assertEqual(result_fallbacks["fallback2"], fallback_adapter2)
            
            # Verify the adapter was created with the right parameters
            mock_adapter.assert_any_call(self.hass, [data], False)
            mock_adapter.assert_any_call(self.hass, [{"fallback1": "data"}], False)
            mock_adapter.assert_any_call(self.hass, [{"fallback2": "data"}], False)

    def test_has_current_hour_price(self):
        """Test has_current_hour_price method."""
        # Set up the mock
        self.price_cache.has_current_hour_price.return_value = True
        
        # Call the method
        result = self.manager.has_current_hour_price()
        
        # Verify the result
        self.assertTrue(result)
        self.price_cache.has_current_hour_price.assert_called_once_with("SE1")

    def test_get_current_hour_price(self):
        """Test get_current_hour_price method."""
        # Set up the mock
        expected = {"hour": "data"}
        self.price_cache.get_current_hour_price.return_value = expected
        
        # Call the method
        result = self.manager.get_current_hour_price()
        
        # Verify the result
        self.assertEqual(result, expected)
        self.price_cache.get_current_hour_price.assert_called_once_with("SE1")

    def test_get_cached_data(self):
        """Test get_cached_data method."""
        # Set up the mock
        expected = {"cached": "data"}
        self.price_cache.get_data.return_value = expected
        
        # Call the method
        result = self.manager.get_cached_data()
        
        # Verify the result
        self.assertEqual(result, expected)
        self.price_cache.get_data.assert_called_once_with("SE1")

    def test_get_status(self):
        """Test get_status method."""
        # Set up test data
        self.manager._active_source = "test_source"
        self.manager._attempted_sources = ["source1", "source2"]
        self.manager._fallback_data = {"fallback1": {}}
        self.manager._last_api_fetch = datetime(2023, 1, 1, 12, 0)
        self.manager._next_scheduled_api_fetch = datetime(2023, 1, 1, 13, 0)
        self.manager._consecutive_failures = 2
        self.manager._last_failure_time = datetime(2023, 1, 1, 11, 0)
        
        # Call the method
        status = self.manager.get_status()
        
        # Verify the result
        self.assertEqual(status["active_source"], "test_source")
        self.assertEqual(status["attempted_sources"], ["source1", "source2"])
        self.assertEqual(status["fallback_sources"], ["fallback1"])
        self.assertEqual(status["last_api_fetch"], "2023-01-01T12:00:00")
        self.assertEqual(status["next_scheduled_api_fetch"], "2023-01-01T13:00:00")
        self.assertEqual(status["consecutive_failures"], 2)
        self.assertEqual(status["last_failure_time"], "2023-01-01T11:00:00")

if __name__ == "__main__":
    unittest.main()
