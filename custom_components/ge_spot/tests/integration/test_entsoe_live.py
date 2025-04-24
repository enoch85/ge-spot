import pytest
import os
from datetime import datetime

from custom_components.ge_spot.api.entsoe import EntsoeAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.config import Config

# Mark all tests in this file as live API tests
pytestmark = pytest.mark.liveapi

# Get ENTSO-E token from environment variable
ENTSOE_TOKEN = os.environ.get("ENTSOE_TOKEN")

# Skip all tests in this file if the token is not set
pytestmark = pytest.mark.skipif(not ENTSOE_TOKEN, reason="ENTSOE_TOKEN environment variable not set")

@pytest.fixture
def entsoe_api():
    """Provides an EntsoeAPI instance configured with the token."""
    config = {Config.API_TOKEN: ENTSOE_TOKEN}
    return EntsoeAPI(config=config)

@pytest.mark.asyncio
@pytest.mark.parametrize("area", ["DE-LU", "FR", "ES", "FI"]) # Test a few diverse areas
async def test_entsoe_live_fetch_parse(entsoe_api, area):
    """Tests fetching and parsing live ENTSO-E data for a given area."""
    print(f"\nTesting ENTSO-E live API for area: {area}...")
    try:
        # Act: Fetch Raw Data
        # Note: ENTSO-E fetch_raw_data often returns the parsed data directly
        # Let's call the higher-level method expected by the fetcher
        parsed_data = await entsoe_api.fetch_day_ahead_prices(area=area)

        # Assert: Parsed Data Structure
        assert parsed_data is not None
        assert isinstance(parsed_data, dict)
        assert parsed_data.get("source") == Source.ENTSOE
        assert parsed_data.get("area") == area
        assert "currency" in parsed_data # Currency varies by region
        assert "api_timezone" in parsed_data # Timezone varies
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
            
            print(f"ENTSO-E Live Test ({area}): OK - Found {len(parsed_data['hourly_prices'])} prices. First hour: {first_key} -> {first_value} {parsed_data['currency']}")
        else:
            # This might indicate an issue or just that data isn't published yet
            print(f"ENTSO-E Live Test ({area}): WARNING - No hourly prices found.")

    except Exception as e:
        pytest.fail(f"ENTSO-E live API test for {area} failed: {e}")
    finally:
        # Close session if created internally
        if hasattr(entsoe_api, 'session') and entsoe_api.session:
             await entsoe_api.session.close() 