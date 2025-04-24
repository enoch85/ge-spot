#!/usr/bin/env python3
"""Tests for the UnifiedPriceManager functionality."""
import sys
import os
import asyncio
import unittest
import logging
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone

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

class TestUnifiedPriceManager(unittest.TestCase):
    """Test the UnifiedPriceManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.hass = MockHass()
        
        self.config = {
            "display_unit": "decimal"
        }
        
        # Mock the get_sources_for_region function to return a list of sources
        with patch('custom_components.ge_spot.api.get_sources_for_region') as mock_get_sources:
            mock_get_sources.return_value = ["nordpool", "entsoe"]
            
            # Initialize the manager with our mocks
            self.manager = UnifiedPriceManager(
                hass=self.hass,
                area="SE1",
                currency="SEK",
                config=self.config,
            )

    def test_init(self):
        """Test initialization."""
        self.assertEqual(self.manager.area, "SE1")
        self.assertEqual(self.manager.currency, "SEK")
        self.assertEqual(self.manager._active_source, None)
        self.assertEqual(self.manager._attempted_sources, [])
        self.assertEqual(self.manager._fallback_sources, [])
        
    @patch('custom_components.ge_spot.coordinator.unified_price_manager.PriceDataFetcher')
    async def test_fetch_data_success(self, mock_fetcher):
        """Test fetch_data with successful result."""
        # Set up the mock to return a successful result
        mock_instance = MagicMock()
        mock_fetcher.return_value = mock_instance
        
        mock_result = {
            "source": "test_source",
            "attempted_sources": ["source1", "source2"],
            "fallback_sources": ["fallback1"],
            "hourly_prices": {"10:00": 1.0, "11:00": 2.0}
        }
        
        # Create a coroutine that returns the mock result
        async def mock_fetch(*args, **kwargs):
            return mock_result
            
        mock_instance.fetch_with_fallback.return_value = mock_fetch()
        
        # Call the method
        result = await self.manager.fetch_data()
        
        # Verify the result
        self.assertIsNotNone(result)
        self.assertEqual(self.manager._active_source, "test_source")
        self.assertEqual(self.manager._attempted_sources, ["source1", "source2"])
        self.assertEqual(self.manager._consecutive_failures, 0)
        
    @patch('custom_components.ge_spot.coordinator.unified_price_manager.PriceDataFetcher')
    async def test_fetch_data_failure(self, mock_fetcher):
        """Test fetch_data with failure result."""
        # Set up the mock to return None
        mock_instance = MagicMock()
        mock_fetcher.return_value = mock_instance
        
        # Create a coroutine that returns None
        async def mock_fetch(*args, **kwargs):
            return None
            
        mock_instance.fetch_with_fallback.return_value = mock_fetch()
        
        # Call the method
        result = await self.manager.fetch_data()
        
        # Verify the result
        self.assertIsNotNone(result)  # Should return an empty result dict
        self.assertEqual(self.manager._consecutive_failures, 1)
        
    def test_process_result(self):
        """Test _process_result method."""
        # Test with a valid result
        result = {
            "source": "test_source",
            "area": "SE1",
            "currency": "SEK",
            "hourly_prices": {"10:00": 1.0, "11:00": 2.0}
        }
        
        # Mock data processor
        self.manager._data_processor = MagicMock()
        expected_processed = {"processed": True}
        self.manager._data_processor.process.return_value = expected_processed
        
        processed = self.manager._process_result(result)
        
        # Verify the processor was called
        self.manager._data_processor.process.assert_called_once_with(result)
        self.assertEqual(processed, expected_processed)
        
    @patch('custom_components.ge_spot.coordinator.unified_price_manager.PriceDataFetcher')
    async def test_fetch_with_tomorrow_data(self, mock_fetcher):
        """Test fetch_data with tomorrow data."""
        # Set up the mock to return a result with tomorrow data
        mock_instance = MagicMock()
        mock_fetcher.return_value = mock_instance
        
        # Create mock data with tomorrow prices
        today = datetime.now(timezone.utc).date()
        tomorrow = today + timedelta(days=1)
        
        # Create hourly prices for today and tomorrow
        hourly_prices = {}
        tomorrow_hourly_prices = {}
        
        # Add today's prices (using simple HH:00 format)
        for hour in range(24):
            hourly_prices[f"{hour:02d}:00"] = 10.0 + hour
            
        # Add tomorrow's prices
        for hour in range(24):
            tomorrow_hourly_prices[f"{hour:02d}:00"] = 50.0 + hour
        
        mock_result = {
            "source": "test_source",
            "attempted_sources": ["source1", "source2"],
            "fallback_sources": ["fallback1"],
            "hourly_prices": hourly_prices,
            "tomorrow_hourly_prices": tomorrow_hourly_prices,
            "has_tomorrow_prices": True
        }
        
        # Create a coroutine that returns the mock result
        async def mock_fetch(*args, **kwargs):
            return mock_result
            
        mock_instance.fetch_with_fallback.return_value = mock_fetch()
        
        # Mock the data processor
        self.manager._data_processor = MagicMock()
        self.manager._data_processor.process.return_value = mock_result
        
        # Call the method
        result = await self.manager.fetch_data()
        
        # Verify the result
        self.assertIsNotNone(result)
        self.assertEqual(len(result["hourly_prices"]), 24)
        self.assertEqual(len(result["tomorrow_hourly_prices"]), 24)
        self.assertTrue(result["has_tomorrow_prices"])

if __name__ == "__main__":
    unittest.main()