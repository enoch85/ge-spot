import pytest
from datetime import datetime

from custom_components.ge_spot.api.epex import EpexAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency

# Mark all tests in this file as live API tests
pytestmark = pytest.mark.liveapi

@pytest.mark.asyncio
@pytest.mark.parametrize("area", ["FR", "DE-LU"]) # EPEX covers FR, DE-LU, AT, BE, CH, GB, NL
async def test_epex_live_fetch_parse(area):
    """Tests fetching and parsing live EPEX data for a given area."""
    print(f"\nTesting EPEX Spot live API for area: {area}...")
    # Arrange
    api = EpexAPI()

    try:
        # Act: Fetch Raw Data
        # EPEX fetch_raw_data seems designed to return the structure ready for parsing
        raw_data = await api.fetch_raw_data(area=area)
        
        # Assert: Raw Data Structure (Varies based on EPEX response)
        assert raw_data is not None
        assert isinstance(raw_data, list) # EPEX seems to return a list of price points
        # We rely on the parser to handle the raw structure

        # Act: Parse Raw Data
        parsed_data = await api.parse_raw_data(raw_data)
        
        # Assert: Parsed Data Structure
        assert parsed_data is not None
        assert isinstance(parsed_data, dict)
        assert parsed_data.get("source") == Source.EPEX
        assert parsed_data.get("area") == area
        assert parsed_data.get("currency") == Currency.EUR # EPEX seems to use EUR
        assert parsed_data.get("api_timezone") # Should have a timezone (likely CET/CEST)
        assert "hourly_prices" in parsed_data
        assert isinstance(parsed_data["hourly_prices"], dict)
        
        # Assert: Hourly Prices Content (if available)
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
            
            print(f"EPEX Live Test ({area}): OK - Found {len(parsed_data['hourly_prices'])} prices. First hour: {first_key} -> {first_value}")
        else:
            print(f"EPEX Live Test ({area}): WARNING - No hourly prices found.")

    except Exception as e:
        pytest.fail(f"EPEX live API test for {area} failed: {e}")
    finally:
        if hasattr(api, 'session') and api.session:
             await api.session.close() 