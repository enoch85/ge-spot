import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from custom_components.ge_spot.coordinator.data_processor import DataProcessor
from custom_components.ge_spot.api.base.data_structure import StandardizedPriceData, PriceStatistics
from custom_components.ge_spot.const.currencies import Currency

# Sample data resembling output from PriceDataFetcher.fetch_with_fallback
# This data has NOT been processed by DataProcessor yet
RAW_FETCHED_DATA_EUR = {
    "source": "mock_source_eur",
    "area": "FI",
    "currency": Currency.EUR,
    "api_timezone": "Europe/Helsinki",
    "fetched_at": datetime.now().isoformat(),
    "hourly_prices": {
        "2024-01-16T00:00:00+02:00": 0.05,
        "2024-01-16T01:00:00+02:00": 0.04,
        "2024-01-16T02:00:00+02:00": 0.03,
        # ... add more hours for completeness testing ...
    },
    "raw_data": "original_api_response_eur",
    "attempted_sources": ["mock_source_eur"],
    "fallback_sources": [],
    "using_cached_data": False,
}

RAW_FETCHED_DATA_SEK = {
    "source": "mock_source_sek",
    "area": "SE3",
    "currency": Currency.SEK,
    "api_timezone": "Europe/Stockholm",
    "fetched_at": datetime.now().isoformat(),
    "hourly_prices": {
        "2024-01-16T00:00:00+01:00": 60.0, # ~0.05 EUR
        "2024-01-16T01:00:00+01:00": 50.0, # ~0.04 EUR
        "2024-01-16T02:00:00+01:00": 40.0, # ~0.03 EUR
    },
    "raw_data": "original_api_response_sek",
    "attempted_sources": ["mock_source_sek"],
    "fallback_sources": [],
    "using_cached_data": False,
}

# Sample data with full 24 hours for stats testing
RAW_FETCHED_DATA_EUR_FULL = {
    "source": "mock_source_eur_full",
    "area": "FI",
    "currency": Currency.EUR,
    "api_timezone": "Europe/Helsinki", # UTC+2
    "fetched_at": datetime.now().isoformat(),
    "hourly_prices": {f"2024-01-16T{h:02d}:00:00+02:00": (h+1)/100.0 for h in range(24)}, # 0.01 to 0.24
    "raw_data": "original_api_response_eur_full",
    "attempted_sources": ["mock_source_eur_full"],
    "fallback_sources": [],
    "using_cached_data": False,
}

@pytest.fixture
def mock_tz_service():
    service = MagicMock()
    service.ha_timezone = pytz.timezone("Europe/Stockholm") # Assume HA is Stockholm
    # Mock normalize_hourly_prices to return simple HH:00 keys for testing
    # In reality, this would do timezone conversion
    def mock_normalize(raw_prices, source_tz_str):
        # Simplified mock: just return prices with HH:00 keys from ISO string
        normalized = {}
        for iso_key, price in raw_prices.items():
            dt_obj = datetime.fromisoformat(iso_key.replace('Z', '+00:00'))
            # Convert to HA timezone before getting hour key
            dt_ha = dt_obj.astimezone(service.ha_timezone)
            normalized[dt_ha.strftime("%H:00")] = price
        return normalized
    service.normalize_hourly_prices = mock_normalize
    service.get_current_hour_key = MagicMock(return_value="01:00") # Assume current hour is 01:00 HA time
    service.get_next_hour_key = MagicMock(return_value="02:00")
    service.get_today_range = MagicMock(return_value=[f"{h:02d}:00" for h in range(24)])
    return service

@pytest.fixture
def mock_exchange_service():
    service = AsyncMock()
    # Mock convert method
    async def mock_convert(amount, from_curr, to_curr):
        if from_curr == to_curr: return amount
        if from_curr == Currency.EUR and to_curr == Currency.SEK: return amount * 11.5
        if from_curr == Currency.SEK and to_curr == Currency.EUR: return amount / 11.5
        if from_curr == Currency.EUR and to_curr == Currency.EUR: return amount # Ensure EUR->EUR works
        # Add other pairs as needed for tests
        raise ValueError(f"Mock conversion not set up for {from_curr}->{to_curr}")
    service.convert = mock_convert
    # Mock rate info method
    service.get_exchange_rate_info = MagicMock(return_value={ "formatted": "1 EUR = 11.5000 SEK", "timestamp": datetime.now().isoformat()})
    return service

@pytest.fixture
def data_processor(mock_tz_service, mock_exchange_service):
    """Provides a DataProcessor instance with mocked services."""
    mock_hass = MagicMock()
    config = { Config.VAT: 0, Config.INCLUDE_VAT: False, Config.DISPLAY_UNIT: "kWh" } # Basic config
    target_currency = Currency.EUR # Default target
    return DataProcessor(mock_hass, "FI", target_currency, config, mock_tz_service, mock_exchange_service)

@pytest.fixture
def data_processor_eur_target(mock_tz_service, mock_exchange_service):
    """Provides a DataProcessor instance targeting EUR."""
    mock_hass = MagicMock()
    config = { Config.VAT: 0, Config.INCLUDE_VAT: False, Config.DISPLAY_UNIT: "kWh" } 
    return DataProcessor(mock_hass, "FI", Currency.EUR, config, mock_tz_service, mock_exchange_service)

@pytest.fixture
def data_processor_sek_target(mock_tz_service, mock_exchange_service):
    """Provides a DataProcessor instance targeting SEK."""
    mock_hass = MagicMock()
    config = { Config.VAT: 0, Config.INCLUDE_VAT: False, Config.DISPLAY_UNIT: "kWh" } 
    return DataProcessor(mock_hass, "SE3", Currency.SEK, config, mock_tz_service, mock_exchange_service)

@pytest.fixture
def data_processor_vat(mock_tz_service, mock_exchange_service):
    """Provides a DataProcessor instance with VAT enabled."""
    mock_hass = MagicMock()
    config = { Config.VAT: 25, Config.INCLUDE_VAT: True, Config.DISPLAY_UNIT: "kWh" } 
    return DataProcessor(mock_hass, "FI", Currency.EUR, config, mock_tz_service, mock_exchange_service)

@pytest.fixture
def data_processor_subunit(mock_tz_service, mock_exchange_service):
    """Provides a DataProcessor instance with subunit display."""
    mock_hass = MagicMock()
    config = { Config.VAT: 0, Config.INCLUDE_VAT: False, Config.DISPLAY_UNIT: DisplayUnit.CENTS }
    return DataProcessor(mock_hass, "FI", Currency.EUR, config, mock_tz_service, mock_exchange_service)

# --- Test Cases ---

@pytest.mark.asyncio
async def test_process_basic_eur(data_processor_eur_target):
    """Test processing data that is already in EUR, no VAT."""
    result = await data_processor_eur_target.process(RAW_FETCHED_DATA_EUR)
    
    assert result["source"] == "mock_source_eur"
    assert result["target_currency"] == Currency.EUR
    assert result["source_currency"] == Currency.EUR
    assert result["hourly_prices"]["01:00"] == 0.04 # 01:00 Helsinki (UTC+2) -> 00:00 UTC -> 01:00 Stockholm (UTC+1)
    assert result["current_price"] == 0.04 # Based on mock_tz_service current key "01:00"
    assert result["next_hour_price"] == 0.03 # Based on mock_tz_service next key "02:00"
    assert result["vat_included"] is False
    assert result["statistics"]["complete_data"] is False # Data is incomplete

@pytest.mark.asyncio
async def test_process_convert_sek_to_eur(data_processor_eur_target):
    """Test processing data, converting SEK to EUR."""
    result = await data_processor_eur_target.process(RAW_FETCHED_DATA_SEK)
    
    assert result["source"] == "mock_source_sek"
    assert result["target_currency"] == Currency.EUR
    assert result["source_currency"] == Currency.SEK
    # Check conversion (based on mock rate 11.5) and timezone (Stockholm UTC+1 -> Stockholm UTC+1)
    assert result["hourly_prices"]["01:00"] == pytest.approx(50.0 / 11.5)
    assert result["current_price"] == pytest.approx(50.0 / 11.5)
    assert result["next_hour_price"] == pytest.approx(40.0 / 11.5)
    assert result["vat_included"] is False
    assert result["statistics"]["complete_data"] is False # Data is incomplete

@pytest.mark.asyncio
async def test_process_with_vat(data_processor_vat):
    """Test processing data with VAT calculation."""
    result = await data_processor_vat.process(RAW_FETCHED_DATA_EUR)
    original_price_01 = RAW_FETCHED_DATA_EUR["hourly_prices"]["2024-01-16T01:00:00+02:00"] # 0.04
    expected_price_01 = 0.04 * 1.25 # Apply 25% VAT
    
    assert result["vat_included"] is True
    assert result["hourly_prices"]["01:00"] == pytest.approx(expected_price_01)
    assert result["current_price"] == pytest.approx(expected_price_01)

@pytest.mark.asyncio
async def test_process_with_subunit(data_processor_subunit):
    """Test processing data with subunit conversion (to Cents)."""
    result = await data_processor_subunit.process(RAW_FETCHED_DATA_EUR)
    original_price_01 = RAW_FETCHED_DATA_EUR["hourly_prices"]["2024-01-16T01:00:00+02:00"] # 0.04 EUR
    expected_price_01 = 0.04 * 100 # Convert to cents
    
    assert result["display_unit"] == DisplayUnit.CENTS
    assert result["hourly_prices"]["01:00"] == pytest.approx(expected_price_01)
    assert result["current_price"] == pytest.approx(expected_price_01)

@pytest.mark.asyncio
async def test_process_statistics_complete(data_processor_eur_target):
    """Test statistics calculation with complete data."""
    # Use the fixture with full 24h data
    result = await data_processor_eur_target.process(RAW_FETCHED_DATA_EUR_FULL)
    
    assert result["statistics"] is not None
    assert result["statistics"]["complete_data"] is True
    # Prices are 0.01 to 0.24 EUR (converted to Stockholm time)
    # Check average (sum(0.01..0.24) / 24 = (24*25/2)/100 / 24 = 3.0 / 24 = 0.125)
    assert result["statistics"]["average"] == pytest.approx(0.125)
    assert result["statistics"]["min"] == pytest.approx(0.01)
    assert result["statistics"]["max"] == pytest.approx(0.24)

@pytest.mark.asyncio
async def test_process_statistics_incomplete(data_processor_eur_target):
    """Test statistics calculation with incomplete data."""
    # Uses the default fixture with only 3 hours
    result = await data_processor_eur_target.process(RAW_FETCHED_DATA_EUR)
    
    assert result["statistics"] is not None
    assert result["statistics"]["complete_data"] is False
    assert result["statistics"]["average"] is None
    assert result["statistics"]["min"] is None
    assert result["statistics"]["max"] is None

@pytest.mark.asyncio
async def test_process_missing_timezone(data_processor_eur_target):
    """Test error handling when source timezone is missing."""
    bad_data = RAW_FETCHED_DATA_EUR.copy()
    del bad_data["api_timezone"]
    
    result = await data_processor_eur_target.process(bad_data)
    assert result["error"] == "Missing source timezone"
    assert not result["hourly_prices"] # Should be empty on error
    assert result["statistics"]["complete_data"] is False

@pytest.mark.asyncio
async def test_process_missing_currency(data_processor_eur_target):
    """Test error handling when source currency is missing."""
    bad_data = RAW_FETCHED_DATA_EUR.copy()
    del bad_data["currency"]
    
    result = await data_processor_eur_target.process(bad_data)
    assert result["error"] == "Missing source currency"
    assert not result["hourly_prices"] # Should be empty on error
    assert result["statistics"]["complete_data"] is False

# TODO: Add test for VAT calculation - DONE
# TODO: Add test for subunit conversion (e.g., to Cents) - DONE
# TODO: Add test for statistics calculation with complete data - DONE
# TODO: Add test for incomplete data handling (stats should be None/incomplete) - DONE
# TODO: Add test for error handling (e.g., missing timezone/currency) - DONE 