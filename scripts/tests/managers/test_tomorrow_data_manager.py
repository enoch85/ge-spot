#!/usr/bin/env python3
"""Tests for the TomorrowDataManager and date handling in ElectricityPriceAdapter.

This script tests the TomorrowDataManager's ability to find and process tomorrow's data,
as well as the ElectricityPriceAdapter's handling of date information in hourly prices.
It also tests with real ENTSO-E API data to verify the adapter can extract tomorrow's data.
"""
import sys
import os
import asyncio
import unittest
import logging
import json
import xml.etree.ElementTree as ET
import argparse
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
from custom_components.ge_spot.api.parsers.entsoe_parser import EntsoeParser
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
        adapter = ElectricityPriceAdapter(self.hass, [self.test_data_with_dates], Source.NORDPOOL, False)
        
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
        adapter = ElectricityPriceAdapter(self.hass, [self.test_data_without_dates], Source.NORDPOOL, False)
        
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
        adapter = ElectricityPriceAdapter(self.hass, [self.test_data_mixed], Source.NORDPOOL, False)
        
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
        adapter = ElectricityPriceAdapter(self.hass, [data], Source.NORDPOOL, False)
        
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
        adapter = ElectricityPriceAdapter(self.hass, [data], Source.NORDPOOL, False)
        
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

class ImprovedElectricityPriceAdapter(ElectricityPriceAdapter):
    """
    This class now extends the standard ElectricityPriceAdapter.
    
    The improved functionality has been incorporated into the main ElectricityPriceAdapter class.
    This class is kept for backward compatibility with existing tests.
    """
    # Since all the improved functionality is now in the parent class,
    # we don't need to implement any additional methods


class TestAdapterWithRealData(unittest.TestCase):
    """Test the ElectricityPriceAdapter with real ENTSO-E API data."""

    def setUp(self):
        """Set up test fixtures."""
        self.hass = MockHass()
        
        # Path to the ENTSO-E API response files
        self.entsoe_response_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "entsoe_responses")
        
    def _load_entsoe_response(self, filename: str) -> str:
        """Load ENTSO-E API response from file.
        
        Args:
            filename: Name of the XML file in the entsoe_responses directory
            
        Returns:
            XML response as string
        """
        file_path = os.path.join(self.entsoe_response_dir, filename)
        if not os.path.exists(file_path):
            logger.warning(f"ENTSO-E response file not found: {file_path}")
            return None
            
        with open(file_path, "r") as f:
            return f.read()
    
    def test_adapter_with_real_entsoe_data(self):
        """Test ElectricityPriceAdapter with real ENTSO-E API data."""
        # Load ENTSO-E API response
        xml_data = self._load_entsoe_response("entsoe_A44_range1.xml")
        if not xml_data:
            self.skipTest("ENTSO-E response file not found. Run test_entsoe_tomorrow_data.py first.")
            
        # Parse the XML data using EntsoeParser
        parser = EntsoeParser()
        hourly_prices = parser.parse_hourly_prices(xml_data, "SE4")
        
        # Print some of the hourly prices to see the format
        logger.info(f"Sample hourly prices from parser: {list(hourly_prices.items())[:5]}")
        
        # Create raw data structure
        raw_data = {
            "hourly_prices": hourly_prices,
            "source": "entsoe",
            "currency": "EUR",
            "area": "SE4"
        }
        
        # Test with original adapter
        logger.info("\n--- Testing with original adapter ---\n")
        adapter = ElectricityPriceAdapter(self.hass, [raw_data], Source.ENTSOE, False)
        
        # Check if adapter correctly extracts tomorrow's data
        tomorrow_prices = adapter.tomorrow_prices
        
        # Log the keys to see what format they are in
        logger.info(f"Original adapter - Hourly price keys: {list(adapter.hourly_prices.keys())[:5]}")
        logger.info(f"Original adapter - Tomorrow price keys: {list(tomorrow_prices.keys())[:5] if tomorrow_prices else 'None'}")
        
        # Check if tomorrow's data is correctly identified
        is_tomorrow_valid = adapter.is_tomorrow_valid()
        
        # Log the results
        logger.info(f"Original adapter - Tomorrow data validation: {is_tomorrow_valid}")
        logger.info(f"Original adapter - Today hours: {len(adapter.hourly_prices)}, Tomorrow hours: {len(tomorrow_prices)}")
        
        # Test with improved adapter
        logger.info("\n--- Testing with improved adapter ---\n")
        improved_adapter = ImprovedElectricityPriceAdapter(self.hass, [raw_data], Source.ENTSOE, False)
        
        # Check if improved adapter correctly extracts tomorrow's data
        improved_tomorrow_prices = improved_adapter.tomorrow_prices
        
        # Log the keys to see what format they are in
        logger.info(f"Improved adapter - Hourly price keys: {list(improved_adapter.hourly_prices.keys())[:5]}")
        logger.info(f"Improved adapter - Tomorrow price keys: {list(improved_tomorrow_prices.keys())[:5] if improved_tomorrow_prices else 'None'}")
        
        # Check if tomorrow's data is correctly identified
        improved_is_tomorrow_valid = improved_adapter.is_tomorrow_valid()
        
        # Log the results
        logger.info(f"Improved adapter - Tomorrow data validation: {improved_is_tomorrow_valid}")
        logger.info(f"Improved adapter - Today hours: {len(improved_adapter.hourly_prices)}, Tomorrow hours: {len(improved_tomorrow_prices)}")
        
        # Compare results
        logger.info("\n--- Comparison ---\n")
        logger.info(f"Original adapter: Tomorrow valid: {is_tomorrow_valid}, Tomorrow hours: {len(tomorrow_prices)}")
        logger.info(f"Improved adapter: Tomorrow valid: {improved_is_tomorrow_valid}, Tomorrow hours: {len(improved_tomorrow_prices)}")
        
        # Assert that the improved adapter can extract tomorrow's data
        self.assertTrue(improved_is_tomorrow_valid, "Improved adapter should validate tomorrow's data")
        self.assertGreaterEqual(len(improved_tomorrow_prices), 20, "Improved adapter should extract at least 20 hours for tomorrow")
    
    def test_adapter_with_all_entsoe_responses(self):
        """Test ElectricityPriceAdapter with all ENTSO-E API responses."""
        # Find all ENTSO-E response files
        if not os.path.exists(self.entsoe_response_dir):
            self.skipTest("ENTSO-E response directory not found. Run test_entsoe_tomorrow_data.py first.")
            
        response_files = [f for f in os.listdir(self.entsoe_response_dir) if f.startswith("entsoe_") and f.endswith(".xml")]
        if not response_files:
            self.skipTest("No ENTSO-E response files found. Run test_entsoe_tomorrow_data.py first.")
            
        # Test each response file
        for filename in response_files:
            logger.info(f"\n\n=== Testing with ENTSO-E response file: {filename} ===\n")
            
            # Load ENTSO-E API response
            xml_data = self._load_entsoe_response(filename)
            if not xml_data:
                logger.warning(f"Could not load ENTSO-E response file: {filename}")
                continue
                
            # Parse the XML data using EntsoeParser
            parser = EntsoeParser()
            hourly_prices = parser.parse_hourly_prices(xml_data, "SE4")
            
            # Create raw data structure
            raw_data = {
                "hourly_prices": hourly_prices,
                "source": "entsoe",
                "currency": "EUR",
                "area": "SE4"
            }
            
            # Test with original adapter
            logger.info("\n--- Testing with original adapter ---\n")
            adapter = ElectricityPriceAdapter(self.hass, [raw_data], Source.ENTSOE, False)
            
            # Check if adapter correctly extracts tomorrow's data
            tomorrow_prices = adapter.tomorrow_prices
            is_tomorrow_valid = adapter.is_tomorrow_valid()
            
            # Log the results
            logger.info(f"Original adapter - File: {filename}, Tomorrow valid: {is_tomorrow_valid}")
            logger.info(f"Original adapter - Today hours: {len(adapter.hourly_prices)}, Tomorrow hours: {len(tomorrow_prices)}")
            
            # Test with improved adapter
            logger.info("\n--- Testing with improved adapter ---\n")
            improved_adapter = ImprovedElectricityPriceAdapter(self.hass, [raw_data], Source.ENTSOE, False)
            
            # Check if improved adapter correctly extracts tomorrow's data
            improved_tomorrow_prices = improved_adapter.tomorrow_prices
            improved_is_tomorrow_valid = improved_adapter.is_tomorrow_valid()
            
            # Log the results
            logger.info(f"Improved adapter - File: {filename}, Tomorrow valid: {improved_is_tomorrow_valid}")
            logger.info(f"Improved adapter - Today hours: {len(improved_adapter.hourly_prices)}, Tomorrow hours: {len(improved_tomorrow_prices)}")
            
            # Compare results
            logger.info("\n--- Comparison ---\n")
            logger.info(f"Original adapter: Tomorrow valid: {is_tomorrow_valid}, Tomorrow hours: {len(tomorrow_prices)}")
            logger.info(f"Improved adapter: Tomorrow valid: {improved_is_tomorrow_valid}, Tomorrow hours: {len(improved_tomorrow_prices)}")
            
            # We expect at least one of the files to have valid tomorrow data with the improved adapter
            if improved_is_tomorrow_valid:
                logger.info(f"Found valid tomorrow data in file: {filename} with improved adapter")
                logger.info(f"Tomorrow hours: {sorted(list(improved_tomorrow_prices.keys()))}")
                
                # If we found valid tomorrow data, the test passes
                self.assertTrue(True)
                return
                
        # If we get here, none of the files had valid tomorrow data even with the improved adapter
        self.fail("No valid tomorrow data found in any ENTSO-E response file, even with the improved adapter")


async def test_tomorrow_data_manager_with_real_api(api_key: str, area: str = "SE4"):
    """Test TomorrowDataManager with real API data.
    
    Args:
        api_key: ENTSOE API key
        area: Area code
        
    Returns:
        Test results
    """
    # Create mock HASS instance
    hass = MockHass()
    
    # Build config with API key
    config = {
        "api_key": api_key,
        "area": area
    }
    
    # Fetch data from the API
    logger.info(f"Fetching data from ENTSOE API for area {area}")
    
    from custom_components.ge_spot.api.entsoe import fetch_day_ahead_prices
    from custom_components.ge_spot.const.currencies import Currency
    
    data = await fetch_day_ahead_prices(
        source_type="entsoe",
        config=config,
        area=area,
        currency=Currency.EUR,
        hass=hass
    )
    
    # Check if we got a valid response
    if not data:
        logger.error("No data returned from ENTSOE API")
        return None
    
    # Log the raw data
    logger.info(f"Raw data: {data.keys()}")
    
    # Check if we have hourly_prices
    if "hourly_prices" in data:
        hourly_prices = data["hourly_prices"]
        logger.info(f"Hourly prices: {len(hourly_prices)} entries")
        
        # Log the first few entries
        sample_entries = list(hourly_prices.items())[:5]
        logger.info(f"Sample hourly prices: {sample_entries}")
        
        # Check if hourly_prices contains ISO format dates
        has_dates = any("T" in hour for hour in hourly_prices.keys())
        logger.info(f"Hourly prices contain ISO format dates: {has_dates}")
        
        # Check if we have tomorrow's data in hourly_prices
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date()
        tomorrow_hours = 0
        tomorrow_hour_keys = []
        
        for hour_key, price in hourly_prices.items():
            # Try to parse the hour key to check if it's for tomorrow
            if "T" in hour_key:  # ISO format with date
                try:
                    hour_dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                    if hour_dt.date() == tomorrow:
                        tomorrow_hours += 1
                        tomorrow_hour_keys.append(hour_key)
                except (ValueError, TypeError):
                    pass
        
        logger.info(f"Found {tomorrow_hours} hours of tomorrow's data in hourly_prices")
        if tomorrow_hours > 0:
            logger.info(f"Tomorrow hour keys: {tomorrow_hour_keys}")
    
    # Check if we have tomorrow_hourly_prices
    if "tomorrow_hourly_prices" in data:
        tomorrow_hourly_prices = data["tomorrow_hourly_prices"]
        logger.info(f"Tomorrow hourly prices: {len(tomorrow_hourly_prices)} entries")
        
        # Log the first few entries
        sample_entries = list(tomorrow_hourly_prices.items())[:5]
        logger.info(f"Sample tomorrow hourly prices: {sample_entries}")
    
    # Create adapter to test tomorrow data extraction
    adapter = ElectricityPriceAdapter(hass, [data], "entsoe", False)
    
    # Check if adapter correctly extracts tomorrow's data
    tomorrow_prices = adapter.tomorrow_prices
    
    # Log the keys to see what format they are in
    logger.info(f"Adapter hourly price keys: {list(adapter.hourly_prices.keys())[:5]}")
    logger.info(f"Adapter tomorrow price keys: {list(tomorrow_prices.keys())[:5] if tomorrow_prices else 'None'}")
    
    # Check if tomorrow's data is correctly identified
    is_tomorrow_valid = adapter.is_tomorrow_valid()
    
    # Log the results
    logger.info(f"Tomorrow data validation: {is_tomorrow_valid}")
    logger.info(f"Today hours: {len(adapter.hourly_prices)}, Tomorrow hours: {len(tomorrow_prices)}")
    
    # Create improved adapter to test tomorrow data extraction
    improved_adapter = ImprovedElectricityPriceAdapter(hass, [data], "entsoe", False)
    
    # Check if improved adapter correctly extracts tomorrow's data
    improved_tomorrow_prices = improved_adapter.tomorrow_prices
    
    # Log the keys to see what format they are in
    logger.info(f"Improved adapter hourly price keys: {list(improved_adapter.hourly_prices.keys())[:5]}")
    logger.info(f"Improved adapter tomorrow price keys: {list(improved_tomorrow_prices.keys())[:5] if improved_tomorrow_prices else 'None'}")
    
    # Check if tomorrow's data is correctly identified
    improved_is_tomorrow_valid = improved_adapter.is_tomorrow_valid()
    
    # Log the results
    logger.info(f"Improved adapter tomorrow data validation: {improved_is_tomorrow_valid}")
    logger.info(f"Improved adapter today hours: {len(improved_adapter.hourly_prices)}, Tomorrow hours: {len(improved_tomorrow_prices)}")
    
    # Create TomorrowDataManager
    from custom_components.ge_spot.coordinator.tomorrow_data_manager import TomorrowDataManager
    from custom_components.ge_spot.timezone import TimezoneService
    
    # Create TimezoneService
    tz_service = TimezoneService(hass, area, config)
    
    # Create TomorrowDataManager
    manager = TomorrowDataManager(
        hass=hass,
        area=area,
        currency=Currency.EUR,
        config=config,
        price_cache=None,
        tz_service=tz_service,
        session=None,
        refresh_callback=None
    )
    
    # Check if manager can find tomorrow's data
    is_tomorrow_valid = adapter.is_tomorrow_valid()
    if is_tomorrow_valid:
        # Update the manager's internal state
        manager._has_tomorrow_data = True
        
    # Now check if we should search
    should_search = manager.should_search(datetime.now())
    
    logger.info(f"TomorrowDataManager should_search: {should_search}")
    logger.info(f"TomorrowDataManager has_tomorrow_data: {manager._has_tomorrow_data}")
    
    # Try with improved adapter
    improved_is_tomorrow_valid = improved_adapter.is_tomorrow_valid()
    if improved_is_tomorrow_valid:
        # Update the manager's internal state
        manager._has_tomorrow_data = True
        
    # Now check if we should search
    improved_should_search = manager.should_search(datetime.now())
    
    logger.info(f"TomorrowDataManager with improved adapter should_search: {improved_should_search}")
    logger.info(f"TomorrowDataManager with improved adapter has_tomorrow_data: {manager._has_tomorrow_data}")
    
    return {
        "original_adapter": {
            "is_tomorrow_valid": is_tomorrow_valid,
            "today_hours": len(adapter.hourly_prices),
            "tomorrow_hours": len(tomorrow_prices)
        },
        "improved_adapter": {
            "is_tomorrow_valid": improved_is_tomorrow_valid,
            "today_hours": len(improved_adapter.hourly_prices),
            "tomorrow_hours": len(improved_tomorrow_prices)
        },
        "tomorrow_data_manager": {
            "should_search": should_search,
            "has_tomorrow_data": manager._has_tomorrow_data
        }
    }

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Test tomorrow data handling")
    parser.add_argument("--test-real-data", action="store_true", help="Run tests with real ENTSO-E API data")
    parser.add_argument("--test-real-api", action="store_true", help="Run tests with real ENTSO-E API")
    parser.add_argument("--api-key", help="ENTSO-E API key")
    parser.add_argument("--area", default="SE4", help="Area code")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    if args.test_real_api:
        # Run the test with real API
        if not args.api_key:
            print("Error: --api-key is required when using --test-real-api")
            sys.exit(1)
        
        # Run the test with real API
        asyncio.run(test_tomorrow_data_manager_with_real_api(args.api_key, args.area))
        sys.exit(0)
    elif args.test_real_data:
        # Run only the real data tests
        suite = unittest.TestSuite()
        suite.addTest(unittest.makeSuite(TestAdapterWithRealData))
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
    else:
        # Run all tests
        unittest.main()
