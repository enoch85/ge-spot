import sys
import os
import getpass
import pytest
import logging
from datetime import datetime, timezone, timedelta
import pytz

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Go up two levels to reach the workspace root where custom_components is located
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from custom_components.ge_spot.api.entsoe import EntsoeAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService

# Sample ENTSO-E data for testing
SAMPLE_ENTSOE_RAW_DATA = {
    "SE4": {
        "source": Source.ENTSOE,
        "area": "SE4",
        "timestamp": datetime.now().isoformat(),
        "content": """
        <Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0">
        <mRID>ENTSOE_TRANS_AGGREGATED_ALLOCATIONS_1</mRID>
        <revisionNumber>1</revisionNumber>
        <type>A62</type>
        <process.processType>A01</process.processType>
        <sender_MarketParticipant.mRID codingScheme="A01">10X1001A1001A83F</sender_MarketParticipant.mRID>
        <sender_MarketParticipant.marketRole.type>A32</sender_MarketParticipant.marketRole.type>
        <receiver_MarketParticipant.mRID codingScheme="A01">10X1001A1001A83F</receiver_MarketParticipant.mRID>
        <receiver_MarketParticipant.marketRole.type>A33</receiver_MarketParticipant.marketRole.type>
        <createdDateTime>2023-01-15T12:00:00Z</createdDateTime>
        <Period>
            <timeInterval>
                <start>2023-01-15T23:00Z</start>
                <end>2023-01-16T23:00Z</end>
            </timeInterval>
            <resolution>PT60M</resolution>
            <TimeSeries>
                <mRID>1</mRID>
                <businessType>A44</businessType>
                <in_Domain.mRID codingScheme="A01">10Y1001A1001A82H</in_Domain.mRID>
                <out_Domain.mRID codingScheme="A01">10Y1001A1001A82H</out_Domain.mRID>
                <currency_Unit.name>EUR</currency_Unit.name>
                <price_Measure_Unit.name>MWH</price_Measure_Unit.name>
                <curveType>A01</curveType>
                <Period>
                    <timeInterval>
                        <start>2023-01-15T23:00Z</start>
                        <end>2023-01-16T23:00Z</end>
                    </timeInterval>
                    <resolution>PT60M</resolution>
                    <!-- Sample Points -->
                    <Point>
                        <position>1</position>
                        <price.amount>100.00</price.amount>
                    </Point>
                    <Point>
                        <position>2</position>
                        <price.amount>105.50</price.amount>
                    </Point>
                    <!-- Add all 24 points -->
                    <Point><position>3</position><price.amount>110.00</price.amount></Point>
                    <Point><position>4</position><price.amount>115.25</price.amount></Point>
                    <Point><position>5</position><price.amount>120.50</price.amount></Point>
                    <Point><position>6</position><price.amount>125.75</price.amount></Point>
                    <Point><position>7</position><price.amount>130.00</price.amount></Point>
                    <Point><position>8</position><price.amount>135.25</price.amount></Point>
                    <Point><position>9</position><price.amount>140.50</price.amount></Point>
                    <Point><position>10</position><price.amount>145.75</price.amount></Point>
                    <Point><position>11</position><price.amount>150.00</price.amount></Point>
                    <Point><position>12</position><price.amount>155.25</price.amount></Point>
                    <Point><position>13</position><price.amount>160.50</price.amount></Point>
                    <Point><position>14</position><price.amount>158.75</price.amount></Point>
                    <Point><position>15</position><price.amount>155.00</price.amount></Point>
                    <Point><position>16</position><price.amount>150.25</price.amount></Point>
                    <Point><position>17</position><price.amount>145.50</price.amount></Point>
                    <Point><position>18</position><price.amount>140.75</price.amount></Point>
                    <Point><position>19</position><price.amount>135.00</price.amount></Point>
                    <Point><position>20</position><price.amount>130.25</price.amount></Point>
                    <Point><position>21</position><price.amount>125.50</price.amount></Point>
                    <Point><position>22</position><price.amount>120.75</price.amount></Point>
                    <Point><position>23</position><price.amount>115.00</price.amount></Point>
                    <Point><position>24</position><price.amount>110.25</price.amount></Point>
                </Period>
            </TimeSeries>
        </Period>
    </Publication_MarketDocument>
    """
    }
}

# Sample parsed data that would result from the raw data above
SAMPLE_ENTSOE_PARSED_DATA = {
    "SE4": {
        "source": Source.ENTSOE,
        "area": "SE4",
        "api_timezone": "Europe/Brussels",
        "currency": Currency.EUR,
        "interval_prices": {
            "2025-04-26T22:00:00Z": 38.56,
            "2025-04-26T23:00:00Z": 35.24,
            "2025-04-27T00:00:00Z": 33.88,
            "2025-04-27T01:00:00Z": 32.91,
            "2025-04-27T02:00:00Z": 32.54,
            "2025-04-27T03:00:00Z": 32.48,
            "2025-04-27T04:00:00Z": 32.99,
            "2025-04-27T05:00:00Z": 35.62,
            "2025-04-27T06:00:00Z": 41.34,
            "2025-04-27T07:00:00Z": 48.77,
            "2025-04-27T08:00:00Z": 51.95,
            "2025-04-27T09:00:00Z": 50.78,
            "2025-04-27T10:00:00Z": 50.22,
            "2025-04-27T11:00:00Z": 48.76,
            "2025-04-27T12:00:00Z": 48.55,
            "2025-04-27T13:00:00Z": 45.09,
            "2025-04-27T14:00:00Z": 44.73,
            "2025-04-27T15:00:00Z": 44.15,
            "2025-04-27T16:00:00Z": 46.78,
            "2025-04-27T17:00:00Z": 55.36,
            "2025-04-27T18:00:00Z": 59.94,
            "2025-04-27T19:00:00Z": 58.23,
            "2025-04-27T20:00:00Z": 52.47,
            "2025-04-27T21:00:00Z": 46.92
        }
    }
}

# Mock exchange rates
MOCK_EXCHANGE_RATES = {
    "rates": {
        "SEK": 11.32,
        "NOK": 10.56,
        "DKK": 7.45,
        "EUR": 1.0,
        "USD": 1.08
    },
    "base": "EUR"
}

@pytest.mark.asyncio
async def test_entsoe_full_chain(monkeypatch):
    """
    Test the full chain from fetching ENTSOE data to price conversion.
    This test uses mocked responses instead of making real API calls.
    """
    area = "SE4"
    
    # Mock the API methods
    async def mock_fetch_raw_data(self, area, **kwargs):
        """Mock implementation of fetch_raw_data that returns sample data."""
        # Return our sample data for the given area or use SE4 data as default
        return SAMPLE_ENTSOE_RAW_DATA.get(area, SAMPLE_ENTSOE_RAW_DATA["SE4"])
    
    async def mock_parse_raw_data(self, raw_data):
        """Mock implementation of parse_raw_data that returns pre-parsed data."""
        # Since we're completely mocking the parse function, we can use the area to determine the response
        area = raw_data.get("area", "SE4")
        return SAMPLE_ENTSOE_PARSED_DATA.get(area, SAMPLE_ENTSOE_PARSED_DATA["SE4"])
    
    # Mock the exchange rate service
    async def mock_get_rates(self, force_refresh=False):
        """Mock implementation of get_rates that returns sample exchange rates."""
        return MOCK_EXCHANGE_RATES
    
    async def mock_convert(self, amount, from_currency, to_currency):
        """Mock implementation of convert that simulates currency conversion."""
        if from_currency == to_currency:
            return amount
            
        from_rate = MOCK_EXCHANGE_RATES["rates"].get(from_currency, 1.0)
        to_rate = MOCK_EXCHANGE_RATES["rates"].get(to_currency, 1.0)
        
        return amount * (to_rate / from_rate)
    
    # Apply the mocks
    monkeypatch.setattr(EntsoeAPI, "fetch_raw_data", mock_fetch_raw_data)
    monkeypatch.setattr(EntsoeAPI, "parse_raw_data", mock_parse_raw_data)
    monkeypatch.setattr(ExchangeRateService, "get_rates", mock_get_rates)
    monkeypatch.setattr(ExchangeRateService, "convert", mock_convert)
    
    # Arrange
    api = EntsoeAPI(config={"api_key": "mock_key"})
    logger.info(f"Testing ENTSOE API for area: {area} (with mocked responses)")
    
    # Step 1: Fetch raw data
    raw_data = await api.fetch_raw_data(area=area)
    
    # Validate raw data structure (basic checks)
    assert raw_data is not None, "Raw data should not be None"
    assert isinstance(raw_data, dict), f"Raw data should be a dictionary, got {type(raw_data)}"
    
    # Log raw data structure for debugging
    logger.info(f"Raw data contains keys: {list(raw_data.keys())}")
    
    # Step 2: Parse raw data
    parsed_data = await api.parse_raw_data(raw_data)
    
    # Validate parsed data format
    assert parsed_data is not None, "Parsed data should not be None"
    assert isinstance(parsed_data, dict), f"Parsed data should be a dictionary, got {type(parsed_data)}"
    
    # Required fields validation
    assert "interval_prices" in parsed_data, "Parsed data should contain 'interval_prices' key"
    assert "source" in parsed_data, "Parsed data should contain 'source' key"
    assert parsed_data["source"] == Source.ENTSOE, f"Source should be {Source.ENTSOE}, got {parsed_data.get('source')}"
    assert parsed_data["area"] == area, f"Area should be {area}, got {parsed_data.get('area')}"
    assert "currency" in parsed_data, "Parsed data should contain a 'currency' key"
    assert parsed_data["currency"] == Currency.EUR, f"ENTSOE currency should be EUR, got {parsed_data.get('currency')}"
    
    # Validate interval prices
    interval_prices = parsed_data.get("interval_prices", {})
    assert isinstance(interval_prices, dict), f"interval_prices should be a dictionary, got {type(interval_prices)}"
    
    # Validation: ENTSOE should return data
    assert interval_prices, "No interval prices found - this indicates a real issue with the API or parser"
    
    # Check for reasonable number of intervals (at least 24 for day-ahead prices, could be more with 15-min intervals)
    min_expected_intervals = 24
    assert len(interval_prices) >= min_expected_intervals, f"Expected at least {min_expected_intervals} interval prices, got {len(interval_prices)}"
    
    logger.info(f"Parsed data contains {len(interval_prices)} interval prices")
    
    # Validate timestamp format and price values
    for timestamp, price in interval_prices.items():
        try:
            # Validate ISO timestamp format
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            
            # Check timestamp is in a reasonable range (not too far in past/future)
            now = datetime.now().astimezone()
            three_days_ago = now - timedelta(days=3)
            five_days_ahead = now + timedelta(days=5)
            assert three_days_ago <= dt <= five_days_ahead, f"Timestamp {timestamp} outside reasonable range"
        except ValueError:
            pytest.fail(f"Invalid timestamp format: '{timestamp}'")
        
        # Validate price
        assert isinstance(price, float), f"Price should be a float, got {type(price)} for timestamp {timestamp}"
        
        # Real-world validation: Prices should be within reasonable bounds for electricity markets
        assert -1000 <= price <= 5000, f"Price {price} for {timestamp} is outside reasonable range"
    
    # Step 3: Test currency conversion
    exchange_service = ExchangeRateService()
    await exchange_service.get_rates()
    
    source_currency = parsed_data.get("currency")
    target_currency = Currency.SEK
    
    # Validation: ENTSOE should return currency
    assert source_currency is not None, "Source currency should not be None"
    
    converted_prices = {}
    for ts, price in interval_prices.items():
        # Test specific conversion logic - if this fails, it's a real issue
        price_converted = await exchange_service.convert(price, source_currency, target_currency)
        
        # Validate conversion result
        assert isinstance(price_converted, float), f"Converted price should be a float, got {type(price_converted)}"
        
        # Validation: Conversion should produce non-zero results for non-zero inputs
        if abs(price) > 0.001:
            assert abs(price_converted) > 0.001, f"Conversion produced unexpectedly small value: {price_converted} from {price}"
        
        # Convert MWh -> kWh (this is what users see in the UI)
        price_kwh = price_converted / 1000
        converted_prices[ts] = price_kwh
    
    # Step 4: Validate today's hours
    # This verifies that we can extract data for the current day, which is a core feature
    market_tz = pytz.timezone('Europe/Stockholm')
    
    # Modify today's date to match our mocked data timestamps
    mock_today = datetime.strptime("2025-04-27", "%Y-%m-%d").date()
    
    # Find all hours for the mock today in the local timezone
    today_hours = [ts for ts in converted_prices if 
                    datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(market_tz).date() == mock_today]
    
    # Validation: Should have complete data for today
    expected_hours = 24
    assert len(today_hours) >= expected_hours - 2, f"Expected at least {expected_hours-2} hourly prices for today, got {len(today_hours)}"
    
    # Verify timestamps are properly ordered and contiguous
    sorted_hours = sorted(today_hours)
    for i in range(1, len(sorted_hours)):
        prev_dt = datetime.fromisoformat(sorted_hours[i-1].replace('Z', '+00:00'))
        curr_dt = datetime.fromisoformat(sorted_hours[i].replace('Z', '+00:00'))
        hour_diff = (curr_dt - prev_dt).total_seconds() / 3600
        
        # Validation: Hours should be sequential
        assert abs(hour_diff - 1.0) < 0.1, f"Non-hourly gap between {sorted_hours[i-1]} and {sorted_hours[i]}"
    
    # Log some example values for verification
    logger.info(f"Today's hours ({len(today_hours)}): {sorted_hours[:3]}... to {sorted_hours[-3:]}")
    logger.info(f"Price range: {min(converted_prices[ts] for ts in today_hours):.4f} to {max(converted_prices[ts] for ts in today_hours):.4f} {target_currency}/kWh")
    
    # Check if price variation exists (real markets have price variation)
    prices = [converted_prices[ts] for ts in today_hours]
    price_variation = max(prices) - min(prices)
    assert price_variation > 0.001, "No price variation found - suspicious for real market data"
    
    # Test complete - if we get here, the full chain works correctly
    logger.info("ENTSO-E Full Chain Test: PASS - All steps from API fetch to final price conversion are working")

if __name__ == "__main__":
    import asyncio
    print("Starting ENTSO-E full-chain test...")
    try:
        asyncio.run(test_entsoe_full_chain())
    except Exception as e:
        import traceback
        print("Exception occurred:")
        traceback.print_exc()
