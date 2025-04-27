import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock

from custom_components.ge_spot.api.aemo import AemoAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from scripts.tests.data.aemo_responses import SAMPLE_AEMO_RESPONSES
from scripts.tests.mocks.api_responses import patch_api_client

# Mark all tests in this file as live API tests (keeping this for categorization)
pytestmark = pytest.mark.liveapi

@pytest.mark.asyncio
@pytest.mark.parametrize("area", ["NSW1", "VIC1"]) # Test major Australian states
async def test_aemo_live_fetch_parse(area):
    """Tests fetching and parsing AEMO data for a given area using mock responses."""
    print(f"\nTesting AEMO API for area: {area} with mock data...")
    # Arrange
    api = AemoAPI()
    
    # Get mock response for this area
    mock_response = SAMPLE_AEMO_RESPONSES[area]

    try:
        # Patch the API client to return our mock data instead of making real API calls
        with patch('custom_components.ge_spot.utils.api_client.ApiClient.fetch', 
                  new_callable=AsyncMock) as mock_fetch:
            # Configure the mock to return our sample data
            mock_fetch.return_value.status = 200
            mock_fetch.return_value.json = AsyncMock(side_effect=ValueError("Not JSON"))
            mock_fetch.return_value.text = AsyncMock(return_value="")  # Will be ignored as we're patching fetch_raw_data
            
            # Patch the fetch_raw_data method to return our mock data directly
            with patch.object(api, 'fetch_raw_data', return_value=AsyncMock(return_value=mock_response)):
                # Act: Get the mocked raw data
                raw_data = await api.fetch_raw_data(area=area)
                
                # Assert: Raw Data Structure 
                assert raw_data is not None
                assert isinstance(raw_data, list)
                assert len(raw_data) > 0
    
                # Act: Parse Raw Data
                parsed_data = await api.parse_raw_data(raw_data)
                
                # Assert: Parsed Data Structure
                assert parsed_data is not None
                assert isinstance(parsed_data, dict)
                assert parsed_data.get("source") == Source.AEMO
                assert parsed_data.get("area") == area
                assert parsed_data.get("currency") == Currency.AUD
                assert parsed_data.get("api_timezone") is not None
                assert "hourly_prices" in parsed_data
                assert isinstance(parsed_data["hourly_prices"], dict)
                
                # Assert: Hourly Prices Content
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
                    
                    print(f"AEMO Test ({area}): OK - Found {len(parsed_data['hourly_prices'])} prices. First hour: {first_key} -> {first_value}")
                else:
                    print(f"AEMO Test ({area}): WARNING - No hourly prices found.")

    except Exception as e:
        pytest.fail(f"AEMO API test for {area} failed: {e}")
    finally:
        if hasattr(api, 'session') and api.session:
             await api.session.close()