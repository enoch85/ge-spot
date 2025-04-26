import pytest
import os
from datetime import datetime

from custom_components.ge_spot.api.amber import AmberAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency

# Mark all tests in this file as live API tests
pytestmark = pytest.mark.liveapi

# Amber requires an API key, skip if not available in environment
skip_reason = "AMBER_API_KEY environment variable not set"

@pytest.mark.skipif(not os.environ.get("AMBER_API_KEY"), reason=skip_reason)
@pytest.mark.asyncio
async def test_amber_live_fetch_parse():
    """Tests fetching and parsing live Amber data."""
    print("\nTesting Amber live API...")
    # Arrange
    # AmberAPI likely reads API key from environment variables internally
    api = AmberAPI()

    try:
        # Act: Fetch Raw Data
        # Amber fetch might require specific parameters or use defaults/env vars
        # Assuming the base fetch works for the configured postcode/key
        raw_data = await api.fetch_raw_data() 
        
        # Assert: Raw Data Structure
        assert raw_data is not None
        # Amber raw data likely a list of price points
        assert isinstance(raw_data, list)
        assert len(raw_data) > 0 # Expect at least some data
        # Minimal check on the first item structure if possible
        assert isinstance(raw_data[0], dict)
        assert 'period' in raw_data[0] 
        assert 'spotPerKwh' in raw_data[0]

        # Act: Parse Raw Data
        parsed_data = await api.parse_raw_data(raw_data)
        
        # Assert: Parsed Data Structure
        assert parsed_data is not None
        assert isinstance(parsed_data, dict)
        assert parsed_data.get("source") == Source.AMBER
        assert parsed_data.get("area") # Amber should determine area
        assert parsed_data.get("currency") == Currency.AUD # Should be AUD
        assert parsed_data.get("api_timezone") # Should have a timezone (Australian)
        assert "hourly_prices" in parsed_data
        assert isinstance(parsed_data["hourly_prices"], dict)
        
        # Assert: Hourly Prices Content
        assert len(parsed_data["hourly_prices"]) > 0
        
        first_key = next(iter(parsed_data["hourly_prices"]))
        first_value = parsed_data["hourly_prices"][first_key]
        
        # Check key format (ISO timestamp)
        try:
            datetime.fromisoformat(first_key.replace("Z", "+00:00"))
        except ValueError:
            pytest.fail(f"Hourly price key '{first_key}' is not a valid ISO timestamp.")
            
        # Check value type (should be float)
        assert isinstance(first_value, float)
        
        print(f"Amber Live Test: OK - Found {len(parsed_data['hourly_prices'])} prices. First hour: {first_key} -> {first_value}")

    except Exception as e:
        pytest.fail(f"Amber live API test failed: {e}")
    finally:
        if hasattr(api, 'session') and api.session:
             await api.session.close() 