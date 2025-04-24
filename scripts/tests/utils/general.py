"""General utility functions for GE-Spot testing."""
import argparse
import logging
import os
import getpass
from typing import Dict, Any, Optional, Set

from custom_components.ge_spot.const.config import Config
from custom_components.ge_spot.const.areas import Area, AreaMapping
from custom_components.ge_spot.const.sources import Source

# Cache for keys entered interactively during the run
_INTERACTIVE_KEYS = {}
_ASKED_KEYS: Set[str] = set()  # Track keys we've already asked for

# Define constants for API keys and other configuration needed by APIs
API_KEY_CONFIG = {
    Source.ENTSOE: {"key": "API_KEY", "description": "ENTSO-E API Key"},
    Source.EPEX: {
        "keys": [
            {"key": "RTE_CLIENT_ID", "description": "RTE Client ID", "needed_for_area": Area.FR},
            {"key": "RTE_CLIENT_SECRET", "description": "RTE Client Secret", "needed_for_area": Area.FR, "secret": True}
        ]
    }
}


def get_all_areas():
    """Get all unique areas from all area mappings."""
    all_areas = set()
    
    # Add areas from all mapping dictionaries
    for mapping_dict in [
        AreaMapping.NORDPOOL_AREAS,
        AreaMapping.ENERGI_DATA_AREAS,
        AreaMapping.ENTSOE_AREAS,
        AreaMapping.EPEX_AREAS,
        AreaMapping.OMIE_AREAS,
        AreaMapping.AEMO_AREAS,
        AreaMapping.STROMLIGNING_AREAS,
        AreaMapping.COMED_AREAS,  # Added ComEd areas
    ]:
        all_areas.update(mapping_dict.keys())
    
    # Convert to sorted list for consistent testing order
    return sorted(all_areas)


def get_all_apis():
    """Get all available APIs."""
    return Source.ALL


def get_area_display_name(area: str) -> str:
    """Get display name for an area."""
    for mapping_dict in [
        AreaMapping.NORDPOOL_AREAS,
        AreaMapping.ENERGI_DATA_AREAS,
        AreaMapping.ENTSOE_AREAS,
        AreaMapping.EPEX_AREAS,
        AreaMapping.OMIE_AREAS,
        AreaMapping.AEMO_AREAS,
        AreaMapping.STROMLIGNING_AREAS,
        AreaMapping.COMED_AREAS,  # Added ComEd areas
    ]:
        if area in mapping_dict:
            return mapping_dict[area]
    
    return area


def _get_api_key(key_name: str, is_required: bool, is_secret: bool = False) -> str:
    """Get API key from env vars, cache, or interactive prompt.
    
    Args:
        key_name: Name of the environment variable for the API key
        is_required: Whether the key is required for the current test
        is_secret: Whether the key should be hidden during input
        
    Returns:
        The API key value or an empty string if not available
    """
    global _ASKED_KEYS  # noqa: F824
    
    # Check environment variables first
    value = os.environ.get(key_name)
    if value:
        return value

    # Check interactive cache
    if key_name in _INTERACTIVE_KEYS:
        return _INTERACTIVE_KEYS[key_name]  # Return cached value (even if empty)

    # If not required for this specific test, return empty string
    if not is_required:
        return ""

    # If required, not in env, and not in cache, ask the user (only once per key)
    if key_name not in _ASKED_KEYS:
        _ASKED_KEYS.add(key_name)  # Mark as asked
        prompt = f"Enter {key_name} (leave blank to skip tests requiring it): "
        try:
            if is_secret:
                # Attempt to use getpass, fallback to input
                try:
                    value = getpass.getpass(prompt)
                except (ImportError, OSError, IOError):  # Handle environments where getpass is unavailable
                     value = input(prompt)
            else:
                value = input(prompt)
            _INTERACTIVE_KEYS[key_name] = value.strip()  # Cache the entered value (or empty string)
            return _INTERACTIVE_KEYS[key_name]
        except EOFError:  # Handle non-interactive environments
             logging.warning(f"Cannot prompt for {key_name} in non-interactive mode. Skipping.")
             _INTERACTIVE_KEYS[key_name] = ""
             return ""
    else:
        # Already asked, but not in cache (meaning user left it blank before)
        return ""


def build_api_key_config(api_name: str, area: str) -> Dict[str, Any]:
    """Build configuration with API keys for a specific API and area.
    
    Args:
        api_name: Name of the API
        area: Area code to test
    
    Returns:
        Dictionary with API configuration including keys
    """
    config = {
        Config.DISPLAY_UNIT: "kWh"
    }
    
    # Add API-specific keys
    if api_name in API_KEY_CONFIG:
        api_config = API_KEY_CONFIG[api_name]
        
        # Simple key configuration
        if "key" in api_config:
            key_name = api_config["key"]
            is_required = True
            config[Config.API_KEY] = _get_api_key(key_name, is_required)
        
        # Multiple keys configuration
        elif "keys" in api_config:
            for key_info in api_config["keys"]:
                key_name = key_info["key"]
                is_secret = key_info.get("secret", False)
                
                # Check if key is needed for this area
                needed_for_area = key_info.get("needed_for_area")
                is_required = needed_for_area is None or area == needed_for_area
                
                # Map key name to config key
                if key_name == "API_KEY":
                    config_key = Config.API_KEY
                elif key_name == "RTE_CLIENT_ID":
                    # Use string key if Config constants not defined
                    config_key = "rte_client_id"
                elif key_name == "RTE_CLIENT_SECRET":
                    # Use string key if Config constants not defined
                    config_key = "rte_client_secret"
                else:
                    config_key = key_name
                
                # Get the key
                config[config_key] = _get_api_key(key_name, is_required, is_secret)
    
    return config


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Test GE-Spot API modules and regions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test all APIs and regions
  python scripts/tests/test_all_apis.py
  
  # Test specific APIs only
  python scripts/tests/test_all_apis.py --apis nordpool entsoe
  
  # Test specific regions only
  python scripts/tests/test_all_apis.py --regions SE1 SE2 DE-LU
  
  # Test specific APIs with specific regions
  python scripts/tests/test_all_apis.py --apis nordpool --regions SE1 SE2
  
  # Increase verbosity for debug logging
  python scripts/tests/test_all_apis.py --log-level DEBUG
  
  # Set a longer timeout for API requests
  python scripts/tests/test_all_apis.py --timeout 60
        """
    )
    parser.add_argument('--apis', nargs='+', help='Specific APIs to test (default: all)')
    parser.add_argument('--regions', nargs='+', help='Specific regions to test (default: all)')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        default=os.environ.get('LOG_LEVEL', 'INFO'),
                        help='Set logging level (default: INFO)')
    parser.add_argument('--timeout', type=int,
                        default=int(os.environ.get('REQUEST_TIMEOUT', 30)),
                        help='Set request timeout in seconds (default: 30)')
    return parser.parse_args()
