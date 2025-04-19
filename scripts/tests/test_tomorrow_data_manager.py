#!/usr/bin/env python3
"""Tests for the TomorrowDataManager and date handling in ElectricityPriceAdapter.

This script tests the TomorrowDataManager's ability to find and process tomorrow's data,
as well as the ElectricityPriceAdapter's handling of date information in hourly prices.
"""
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

from custom_components.ge_spot.coordinator.tomorrow_data_manager import TomorrowDataManager
from custom_components.ge_spot.price.adapter import ElectricityPriceAdapter
from custom_components.ge_spot.const.network import Network
from scripts.tests.mocks.hass import MockHass

class TestTomorrowDataManager(unittest.TestCase):
    """Test the TomorrowDataManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        self.price_cache = MagicMock()
        self.tz_service = MagicMock()
        self.refresh_callback = MagicMock()
        
        self.config = {
            "display_unit": "decimal"
        }
        
        self.manager = TomorrowDataManager(
            hass=self.hass,
            area="SE1",
            currency="SEK",
            config=self.config,
            price_cache=self.price_cache,
            tz_service=self.tz_service,
            session=None,
            refresh_callback=self.refresh_callback
        )

    def test_init(self):
        """Test initialization."""
        self.assertEqual(self.manager.area, "SE1")
        self.assertEqual(self.manager.currency, "SEK")
        self.assertEqual(self.manager._search_active, False)
        self.assertEqual(self.manager._attempt_count, 0)
        self.assertEqual(self.manager._last_attempt, None)
        self.assertEqual(self.manager._has_tomorrow_data, False)

    def test_calculate_wait_time(self):
        """Test wait time calculation."""
        # Initial retry
        self.assertEqual(self.manager.calculate_wait_time(), 15)
        
        # First backoff
        self.manager._attempt_count = 1
        self.assertEqual(self.manager.calculate_wait_time(), 15.0)
        
        # Second backoff
        self.manager._attempt_count = 2
        self.assertEqual(self.manager.calculate_wait_time(), 22.5)
        
        # Cap at 3 hours (180 minutes)
        self.manager._attempt_count = 20
        self.assertEqual(self.manager.calculate_wait_time(), 180)

    @patch('custom_components.ge_spot.coordinator.tomorrow_data_manager.dt_util')
    def test_should_search_before_special_window(self, mock_dt_util):
        """Test should_search before special window."""
        # Before special window (13:00-14:00)
        mock_now = datetime(2023, 1, 1, 12, 0)
        mock_dt_util.now.return_value = mock_now
        
        result = self.manager.should_search(mock_now)
        self.assertFalse(result)

    @patch('custom_components.ge_spot.coordinator.tomorrow_data_manager.dt_util')
    def test_should_search_after_special_window(self, mock_dt_util):
        """Test should_search after special window."""
        # After special window (13:00-14:00)
        mock_now = datetime(2023, 1, 1, 14, 30)
        mock_dt_util.now.return_value = mock_now
        
        # Mock that we don't have tomorrow's data
        self.manager._check_if_has_tomorrow_data = MagicMock(return_value=False)
        
        result = self.manager.should_search(mock_now)
        self.assertTrue(result)
        self.assertTrue(self.manager._search_active)
        self.assertEqual(self.manager._attempt_count, 0)

    @patch('custom_components.ge_spot.coordinator.tomorrow_data_manager.dt_util')
    def test_should_search_with_tomorrow_data(self, mock_dt_util):
        """Test should_search when we already have tomorrow's data."""
        mock_now = datetime(2023, 1, 1, 14, 30)
        mock_dt_util.now.return_value = mock_now
        
        # Mock that we have tomorrow's data
        self.manager._check_if_has_tomorrow_data = MagicMock(return_value=True)
        
        result = self.manager.should_search(mock_now)
        self.assertFalse(result)

    @patch('custom_components.ge_spot.coordinator.tomorrow_data_manager.dt_util')
    def test_should_search_near_midnight(self, mock_dt_util):
        """Test should_search near midnight."""
        mock_now = datetime(2023, 1, 1, 23, 50)
        mock_dt_util.now.return_value = mock_now
        
        # Activate search
        self.manager._search_active = True
        
        result = self.manager.should_search(mock_now)
        self.assertFalse(result)
        self.assertFalse(self.manager._search_active)

    @patch('custom_components.ge_spot.coordinator.tomorrow_data_manager.dt_util')
    def test_should_search_after_attempt(self, mock_dt_util):
        """Test should_search after an attempt."""
        mock_now = datetime(2023, 1, 1, 14, 30)
        mock_dt_util.now.return_value = mock_now
        
        # Mock that we don't have tomorrow's data
        self.manager._check_if_has_tomorrow_data = MagicMock(return_value=False)
        
        # Set up as if we've already made an attempt
        self.manager._search_active = True
        self.manager._attempt_count = 1
        self.manager._last_attempt = mock_now - timedelta(minutes=10)  # 10 minutes ago
        
        # Wait time should be 15 minutes for first retry
        self.manager.calculate_wait_time = MagicMock(return_value=15)
        
        # Should not search yet (only 10 minutes passed, need 15)
        result = self.manager.should_search(mock_now)
        self.assertFalse(result)
        
        # Now set last attempt to 20 minutes ago
        self.manager._last_attempt = mock_now - timedelta(minutes=20)
        
        # Should search now (20 minutes passed, need 15)
        result = self.manager.should_search(mock_now)
        self.assertTrue(result)

    def test_update_data_status(self):
        """Test update_data_status method."""
        # Test with data that has tomorrow_valid=True
        data = {"tomorrow_valid": True}
        self.manager.update_data_status(data)
        self.assertTrue(self.manager._has_tomorrow_data)
        
        # Test with data that has tomorrow_valid=False
        data = {"tomorrow_valid": False}
        self.manager.update_data_status(data)
        # Should still be True because we don't override True with False
        self.assertTrue(self.manager._has_tomorrow_data)
        
        # Reset and test again
        self.manager._has_tomorrow_data = False
        self.manager.update_data_status(data)
        self.assertFalse(self.manager._has_tomorrow_data)

    def test_get_status(self):
        """Test get_status method."""
        self.manager._search_active = True
        self.manager._attempt_count = 2
        self.manager._last_attempt = datetime(2023, 1, 1, 14, 30)
        
        # Mock calculate_wait_time
        self.manager.calculate_wait_time = MagicMock(return_value=30)
        
        status = self.manager.get_status()
        self.assertEqual(status["search_active"], True)
        self.assertEqual(status["attempt_count"], 2)
        self.assertEqual(status["last_attempt"], "2023-01-01T14:30:00")
        
        # Next attempt should be 30 minutes after last attempt
        expected_next = (self.manager._last_attempt + timedelta(minutes=30)).isoformat()
        self.assertEqual(status["next_attempt"], expected_next)

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
        # Load sample data from file
        return self._load_sample_data("sample_data_with_dates.json")
    
    def _create_test_data_without_dates(self) -> Dict[str, Any]:
        """Create test data without dates in hourly_prices."""
        # Load sample data from file
        data = self._load_sample_data("sample_data_with_separate_tomorrow.json")
        # Remove tomorrow_hourly_prices to get just today's data
        if "tomorrow_hourly_prices" in data:
            data.pop("tomorrow_hourly_prices")
        return data
    
    def _create_test_data_mixed(self) -> Dict[str, Any]:
        """Create test data with mixed today's and tomorrow's data in hourly_prices."""
        # Load sample data from file
        return self._load_sample_data("sample_data_with_dates.json")
    
    def test_adapter_with_dates(self):
        """Test ElectricityPriceAdapter with dates in hourly_prices."""
        # Create adapter with data that has dates
        adapter = ElectricityPriceAdapter(self.hass, [self.test_data_with_dates], False)
        
        # Check if adapter preserves dates
        hourly_prices = adapter.hourly_prices
        
        # Log the keys to see what format they are in
        logger.info(f"Hourly price keys: {list(hourly_prices.keys())[:5]}")
        
        # The adapter should now handle ISO format dates correctly
        self.assertEqual(len(hourly_prices), 24, "Adapter should extract 24 hours for today")
        
        # Check if all hours are present
        for hour in range(24):
            hour_key = f"{hour:02d}:00"
            self.assertIn(hour_key, hourly_prices, f"Hour {hour_key} should be present")
            
        # Check if tomorrow's data is correctly extracted
        tomorrow_prices = adapter.tomorrow_prices
        self.assertEqual(len(tomorrow_prices), 24, "Adapter should extract 24 hours for tomorrow")
        
        # Check if is_tomorrow_valid returns True
        self.assertTrue(adapter.is_tomorrow_valid(), "Adapter should validate tomorrow's data")
    
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
        
        # Log the keys to see what format they are in
        logger.info(f"Hourly price keys: {list(hourly_prices.keys())}")
        
        # The adapter should now extract tomorrow's data from hourly_prices
        # and move it to tomorrow_prices
        self.assertEqual(len(hourly_prices), 24, "Adapter should have 24 hours for today")
        
        # Check if tomorrow's data is correctly identified
        tomorrow_prices = adapter.tomorrow_prices
        self.assertEqual(len(tomorrow_prices), 24, "Adapter should extract 24 hours for tomorrow")
        
        # Check if is_tomorrow_valid returns True
        self.assertTrue(adapter.is_tomorrow_valid(), "Adapter should validate tomorrow's data")
    
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
        
        # Create adapter
        adapter = ElectricityPriceAdapter(self.hass, [data], False)
        
        # Check if adapter correctly identifies tomorrow's data
        self.assertEqual(len(adapter.tomorrow_prices), 24, "Adapter should have 24 hours for tomorrow")
        self.assertTrue(adapter.is_tomorrow_valid(), "Adapter should validate tomorrow's data")
    
    def test_adapter_with_dates_in_tomorrow_data(self):
        """Test ElectricityPriceAdapter with dates in tomorrow_hourly_prices."""
        # Create data with dates in tomorrow_hourly_prices
        data = self._create_test_data_without_dates()
        
        # Add tomorrow's data with dates
        tomorrow_hourly_prices = {}
        for hour in range(24):
            dt = datetime.combine(self.tomorrow, datetime.min.time().replace(hour=hour), timezone.utc)
            iso_key = dt.isoformat()
            tomorrow_hourly_prices[iso_key] = 50.0 + hour
        
        data["tomorrow_hourly_prices"] = tomorrow_hourly_prices
        
        # Create adapter
        adapter = ElectricityPriceAdapter(self.hass, [data], False)
        
        # Check if adapter correctly processes tomorrow_hourly_prices with ISO format dates
        tomorrow_prices = adapter.tomorrow_prices
        
        # Log the keys to see what format they are in
        logger.info(f"Tomorrow price keys: {list(tomorrow_prices.keys())[:5]}")
        
        # The adapter should now handle ISO format dates correctly
        self.assertEqual(len(tomorrow_prices), 24, "Adapter should extract 24 hours for tomorrow")
        
        # Check if all hours are present
        for hour in range(24):
            hour_key = f"{hour:02d}:00"
            self.assertIn(hour_key, tomorrow_prices, f"Hour {hour_key} should be present in tomorrow_prices")
            
        # Check if is_tomorrow_valid returns True
        self.assertTrue(adapter.is_tomorrow_valid(), "Adapter should validate tomorrow's data")

if __name__ == "__main__":
    unittest.main()
