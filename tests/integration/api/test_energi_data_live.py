import pytest
from datetime import datetime

from custom_components.ge_spot.api.energi_data import EnergiDataAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency

# Mark all tests in this file as live API tests
pytestmark = pytest.mark.liveapi

@pytest.mark.asyncio
@pytest.mark.parametrize("area", ["DK1", "DK2"]) # Energi Data Service is for Denmark
async def test_energi_data_live_fetch_parse(area):
    """Tests fetching and parsing live Energi Data Service data for a given area."""
    print(f"\nTesting Energi Data Service live API for area: {area}...")
    # Arrange
    api = EnergiDataAPI()

    try:
        # Act: Fetch Raw Data
        raw_data = await api.fetch_raw_data(area=area)
        
        # Assert: Raw Data Structure 
        assert raw_data is not None
        assert isinstance(raw_data, dict)
        assert "records" in raw_data # Specific structure for this API
        assert isinstance(raw_data["records"], list)
        # We rely on the parser to handle the rest

        # Act: Parse Raw Data
        parsed_data = await api.parse_raw_data(raw_data)
        
        # Assert: Parsed Data Structure
        assert parsed_data is not None
        assert isinstance(parsed_data, dict)
        assert parsed_data.get("source") == Source.ENERGI_DATA_SERVICE
        assert parsed_data.get("area") == area
        assert parsed_data.get("currency") == Currency.DKK # Should be DKK
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
            
            print(f"Energi Data Service Live Test ({area}): OK - Found {len(parsed_data['hourly_prices'])} prices. First hour: {first_key} -> {first_value}")
        else:
            print(f"Energi Data Service Live Test ({area}): WARNING - No hourly prices found.")

    except Exception as e:
        pytest.fail(f"Energi Data Service live API test for {area} failed: {e}")
    finally:
        if hasattr(api, 'session') and api.session:
             await api.session.close() 