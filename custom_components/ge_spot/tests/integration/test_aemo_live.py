import pytest
from datetime import datetime

from custom_components.ge_spot.api.aemo import AemoAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency

# Mark all tests in this file as live API tests
pytestmark = pytest.mark.liveapi

@pytest.mark.asyncio
@pytest.mark.parametrize("area", ["NSW1", "VIC1"]) # Test major Australian states
async def test_aemo_live_fetch_parse(area):
    """Tests fetching and parsing live AEMO data for a given area."""
    print(f"\nTesting AEMO live API for area: {area}...")
    # Arrange
    api = AemoAPI()

    try:
        # Act: Fetch Raw Data
        # AEMO seems to have a specific fetch logic
        raw_data = await api.fetch_raw_data(area=area)
        
        # Assert: Raw Data Structure 
        assert raw_data is not None
        # AEMO raw data structure might be complex; rely on parser validation
        assert isinstance(raw_data, list) # Assuming it fetches a list of intervals
        # We rely on the parser to handle the rest

        # Act: Parse Raw Data
        parsed_data = await api.parse_raw_data(raw_data)
        
        # Assert: Parsed Data Structure
        assert parsed_data is not None
        assert isinstance(parsed_data, dict)
        assert parsed_data.get("source") == Source.AEMO
        assert parsed_data.get("area") == area
        assert parsed_data.get("currency") == Currency.AUD # Should be AUD
        assert parsed_data.get("api_timezone") # Should have a timezone (Australian)
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
            
            print(f"AEMO Live Test ({area}): OK - Found {len(parsed_data['hourly_prices'])} prices. First hour: {first_key} -> {first_value}")
        else:
            # AEMO data might be interval-based and might not align perfectly hourly initially
            print(f"AEMO Live Test ({area}): WARNING - No hourly prices found (or parsing failed to aggregate).")

    except Exception as e:
        pytest.fail(f"AEMO live API test for {area} failed: {e}")
    finally:
        if hasattr(api, 'session') and api.session:
             await api.session.close() 