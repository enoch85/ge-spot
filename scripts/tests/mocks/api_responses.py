"""Mock utilities for API responses in tests.

This module provides utility functions and sample response data for mocking
API calls in tests without requiring actual network requests.
"""
import os
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

# Path to sample data files
MOCK_DATA_DIR = Path(os.path.dirname(os.path.dirname(__file__))) / "data"

def get_sample_data_path(filename):
    """Get the full path to a sample data file."""
    return MOCK_DATA_DIR / filename

def load_sample_json(filename):
    """Load a sample JSON file from the data directory."""
    file_path = get_sample_data_path(filename)
    with open(file_path, 'r') as f:
        return json.load(f)

def load_sample_xml(filename):
    """Load a sample XML file from the data directory."""
    file_path = get_sample_data_path(filename)
    with open(file_path, 'r') as f:
        return f.read()

def load_sample_text(filename):
    """Load a sample text file from the data directory."""
    file_path = get_sample_data_path(filename)
    with open(file_path, 'r') as f:
        return f.read()

def mock_api_client_response(content, status=200):
    """Create a mock response object similar to what ApiClient would return."""
    mock_response = MagicMock()
    mock_response.status = status
    
    # For JSON responses
    if isinstance(content, (dict, list)):
        mock_response.json = AsyncMock(return_value=content)
        mock_response.text = AsyncMock(return_value=json.dumps(content))
    # For XML or text responses
    else:
        mock_response.text = AsyncMock(return_value=content)
        mock_response.json = AsyncMock(side_effect=ValueError("Not JSON"))
    
    return mock_response

def patch_api_client(return_value, status=200):
    """Create a patch for ApiClient.fetch that returns the specified content."""
    mock_response = mock_api_client_response(return_value, status)
    return patch('custom_components.ge_spot.utils.api_client.ApiClient.fetch', 
                 return_value=AsyncMock(return_value=mock_response))

def generate_hourly_prices(start_datetime, hours=24, base_price=50.0, volatility=10.0):
    """Generate realistic sample hourly prices starting from the specified datetime.
    
    Args:
        start_datetime: Starting datetime (with timezone)
        hours: Number of hours to generate prices for
        base_price: Base price value
        volatility: Price volatility (max random deviation from base price)
        
    Returns:
        Dict of ISO format timestamps to price values
    """
    prices = {}
    
    for hour in range(hours):
        # Create timestamp for this hour
        timestamp = start_datetime + timedelta(hours=hour)
        iso_timestamp = timestamp.isoformat()
        
        # Generate a somewhat realistic price with some randomness
        # Using a deterministic pattern based on the hour for test repeatability
        hourly_factor = 1.0 + (((hour % 24) - 12) / 12) * 0.5  # Daily curve pattern
        price = base_price * hourly_factor
        
        # Add some "randomness" based on the hour number for variation but deterministic results
        variation = ((hour * 7919) % 1000) / 1000.0 * volatility  # Using prime number for pseudo-randomness
        price += variation - (volatility / 2)
        
        prices[iso_timestamp] = round(price, 2)
    
    return prices