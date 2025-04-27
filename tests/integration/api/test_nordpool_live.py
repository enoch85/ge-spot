import pytest
import os
from datetime import datetime

from custom_components.ge_spot.api.nordpool import NordpoolAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency

# Mark all tests in this file as live API tests
pytestmark = pytest.mark.liveapi

@pytest.mark.asyncio
async def test_nordpool_live_fetch_parse_fi():
    """Tests fetching and parsing live Nordpool data for FI area."""
    # Arrange
    api = NordpoolAPI()
    area = "FI"

    try:
        # Act: Fetch Raw Data
        raw_data = await api.fetch_raw_data(area=area)
        
        # Assert: Raw Data Structure
        assert raw_data is not None
        assert isinstance(raw_data, dict)
        # Nordpool fetch returns 'today' and potentially 'tomorrow' keys
        assert "today" in raw_data 
        assert raw_data.get("source") == Source.NORDPOOL
        assert raw_data.get("area") == area
        assert raw_data.get("api_timezone") == "Europe/Oslo"
        
        # Act: Parse Raw Data
        parsed_data = await api.parse_raw_data(raw_data)
        
        # Assert: Parsed Data Structure
        assert parsed_data is not None
        assert isinstance(parsed_data, dict)
        assert parsed_data.get("source") == Source.NORDPOOL
        assert parsed_data.get("area") == area
        assert parsed_data.get("currency") == Currency.EUR # Nordpool defaults to EUR
        assert parsed_data.get("api_timezone") == "Europe/Oslo"
        assert "hourly_prices" in parsed_data
        assert isinstance(parsed_data["hourly_prices"], dict)
        
        # Assert: Hourly Prices Content (if available)
        # We can't assert specific values, but we check format and type
        if parsed_data["hourly_prices"]:
            first_key = next(iter(parsed_data["hourly_prices"]))
            first_value = parsed_data["hourly_prices"][first_key]
            
            # Check key format (ISO timestamp)
            try:
                datetime.fromisoformat(first_key.replace("Z", "+00:00"))
            except ValueError:
                pytest.fail(f"Hourly price key '{first_key}' is not a valid ISO timestamp.")
                
            # Check value type
            assert isinstance(first_value, float)
            
            print(f"Nordpool Live Test (FI): OK - Found {len(parsed_data['hourly_prices'])} prices. First hour: {first_key} -> {first_value}")
        else:
            # It's possible prices aren't available yet (e.g., ran before 13:00 CET)
            print(f"Nordpool Live Test (FI): OK - No hourly prices found (might be expected).")

    except Exception as e:
        pytest.fail(f"Nordpool live API test for {area} failed: {e}")
    finally:
        # Clean up session if necessary (ApiClient handles this internally if session wasn't passed)
        pass 

# TODO: Add similar tests for other key Nordpool areas (e.g., SE3, NO1, DK1) 