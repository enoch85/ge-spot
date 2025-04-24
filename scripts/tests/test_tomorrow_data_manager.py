#!/usr/bin/env python3
"""Tests for the UnifiedPriceManager - Tomorrow data functionality and adapter date handling."""
import sys
import os
import asyncio
import unittest
import logging
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

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

class TestTomorrowDataHandling(unittest.TestCase):
    """Test the UnifiedPriceManager's tomorrow data handling."""

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
    async def test_fetch_data_with_tomorrow_data(self, mock_fetcher):
        """Test fetch_data when tomorrow's data is available."""
        # Set up the mock to return data with tomorrow prices
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
            "tomorrow_hourly_prices": tomorrow_hourly_prices
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
        self.assertEqual(self.manager._active_source, "test_source")
        self.assertEqual(self.manager._attempted_sources, ["source1", "source2"])
        self.assertEqual(self.manager._consecutive_failures, 0)
        
        # Check that tomorrow prices are available
        self.assertIn("tomorrow_hourly_prices", result)
        self.assertEqual(len(result["tomorrow_hourly_prices"]), 24)

class TestAdapterDateHandling(unittest.TestCase):
    """Test the date handling in ElectricityPriceAdapter."""

    def setUp(self):
        """Set up test fixtures."""
        self.hass = MockHass()
        
        # Get current date and tomorrow's date
        self.today = datetime.now(timezone.utc).date()
        self.tomorrow = self.today + timedelta(days=1)
        
        # Create test data with dates in hourly_prices
        self.test_data_with_dates = self._create_test_data_with_dates()
        self.test_data_without_dates = self._create_test_data_without_dates()
        self.test_data_mixed = self._create_test_data_mixed()
        
    def _load_sample_data(self, filename: str) -> Dict[str, Any]:
        """Load sample data from a JSON file.
        
        Args:
            filename: Name of the JSON file in the data directory
            
        Returns:
            Dictionary with sample data
        """
        file_path = os.path.join(os.path.dirname(__file__), "data", filename)
        with open(file_path, "r") as f:
            return json.load(f)
    
    def _create_test_data_with_dates(self) -> Dict[str, Any]:
        """Create test data with ISO format dates in hourly_prices."""
        # Create sample data with ISO format dates
        data = {
            "source": "test_source",
            "area": "SE1",
            "currency": "SEK",
            "hourly_prices": {}
        }
        
        # Add today's hourly prices with ISO format dates
        for hour in range(24):
            dt = datetime.combine(self.today, datetime.min.time().replace(hour=hour), timezone.utc)
            data["hourly_prices"][dt.isoformat()] = 10.0 + hour
            
        # Add tomorrow's hourly prices with ISO format dates
        for hour in range(24):
            dt = datetime.combine(self.tomorrow, datetime.min.time().replace(hour=hour), timezone.utc)
            data["hourly_prices"][dt.isoformat()] = 50.0 + hour
            
        return data
    
    def _create_test_data_without_dates(self) -> Dict[str, Any]:
        """Create test data without dates in hourly_prices."""
        # Create sample data without dates
        data = {
            "source": "test_source",
            "area": "SE1",
            "currency": "SEK",
            "hourly_prices": {}
        }
        
        # Add today's hourly prices without dates
        for hour in range(24):
            data["hourly_prices"][f"{hour:02d}:00"] = 10.0 + hour
            
        return data
    
    def _create_test_data_mixed(self) -> Dict[str, Any]:
        """Create test data with mixed today's and tomorrow's data in hourly_prices."""
        # This is the same as test_data_with_dates for our purposes
        return self._create_test_data_with_dates()
    
    def test_adapter_with_dates(self):
        """Test ElectricityPriceAdapter with dates in hourly_prices."""
        # Create adapter with data that has dates
        adapter = ElectricityPriceAdapter(self.hass, [self.test_data_with_dates], False)
        
        # Check if adapter preserves dates
        hourly_prices = adapter.hourly_prices
        
        # The adapter should have at least 24 hours of data
        self.assertGreaterEqual(len(hourly_prices), 24, "Adapter should extract at least 24 hours")
        
        # Since the adapter is using full ISO timestamps as keys, we should 
        # check for the presence of each hour in the timestamps
        today_date_str = self.today.isoformat()
        for hour in range(24):
            # Look for the pattern "YYYY-MM-DDThh:" in the keys
            hour_pattern = f"{today_date_str}T{hour:02d}:"
            hour_exists = any(hour_pattern in key for key in hourly_prices.keys())
            self.assertTrue(hour_exists, f"Hour {hour:02d} should be present in hourly_prices")
            
        # Check if tomorrow's data is correctly extracted
        tomorrow_prices = adapter.get_tomorrow_prices()
        self.assertEqual(len(tomorrow_prices), 24, "Adapter should extract 24 hours for tomorrow")
        
        # Check if has_tomorrow_prices returns True
        self.assertTrue(adapter.has_tomorrow_prices(), "Adapter should have tomorrow's data")
    
    def test_adapter_without_dates(self):
        """Test ElectricityPriceAdapter without dates in hourly_prices."""
        # Create adapter with data that doesn't have dates
        adapter = ElectricityPriceAdapter(self.hass, [self.test_data_without_dates], False)
        
        # Check if adapter has all hours
        hourly_prices = adapter.hourly_prices
        self.assertEqual(len(hourly_prices), 24, "Adapter should have 24 hours")
        
        # Check if the hours are in the expected format (HH:00)
        for hour in range(24):
            hour_key = f"{hour:02d}:00"
            self.assertIn(hour_key, hourly_prices, f"Hour {hour_key} should be present")
    
    def test_adapter_with_mixed_data(self):
        """Test ElectricityPriceAdapter with mixed today's and tomorrow's data."""
        # Create adapter with mixed data
        adapter = ElectricityPriceAdapter(self.hass, [self.test_data_mixed], False)
        
        # Check if adapter has all hours
        hourly_prices = adapter.hourly_prices
        
        # The adapter now combines data by default
        self.assertGreaterEqual(len(hourly_prices), 24, "Adapter should have at least 24 hours")
        
        # Check if tomorrow's data is correctly identified
        tomorrow_prices = adapter.get_tomorrow_prices()
        self.assertEqual(len(tomorrow_prices), 24, "Adapter should extract 24 hours for tomorrow")
        
        # Check if has_tomorrow_prices returns True
        self.assertTrue(adapter.has_tomorrow_prices(), "Adapter should have tomorrow's data")
    
    def test_adapter_with_separate_tomorrow_data(self):
        """Test ElectricityPriceAdapter with separate tomorrow_hourly_prices."""
        # Create data with separate tomorrow_hourly_prices
        data = self._create_test_data_without_dates()
        
        # Add tomorrow's data
        tomorrow_hourly_prices = {}
        for hour in range(24):
            hour_key = f"{hour:02d}:00"
            tomorrow_hourly_prices[hour_key] = 50.0 + hour
        
        data["tomorrow_hourly_prices"] = tomorrow_hourly_prices
        data["has_tomorrow_prices"] = True  # Add this flag to indicate tomorrow data is valid
        
        # Create adapter
        adapter = ElectricityPriceAdapter(self.hass, [data], False)
        
        # Check if adapter correctly identifies tomorrow's data
        tomorrow_prices = adapter.get_tomorrow_prices()
        self.assertEqual(len(tomorrow_prices), 24, "Adapter should have 24 hours for tomorrow")
        self.assertTrue(adapter.has_tomorrow_prices(), "Adapter should have tomorrow's data")

if __name__ == "__main__":
    unittest.main()
