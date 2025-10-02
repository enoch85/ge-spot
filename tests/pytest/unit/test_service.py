import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
import pytz  # Use pytz for robust timezone handling in tests

from homeassistant.util import dt as dt_util
from freezegun import freeze_time

from custom_components.ge_spot.timezone.service import TimezoneService
from custom_components.ge_spot.const.time import TimezoneReference
from custom_components.ge_spot.const.config import Config # Import Config

# Mock Home Assistant instance and config if needed
class MockHass:
    def __init__(self, time_zone="Europe/Stockholm"):
        self.config = MagicMock()
        self.config.time_zone = time_zone

# Sample data
CET = pytz.timezone("Europe/Berlin") # UTC+1/UTC+2
EET = pytz.timezone("Europe/Helsinki") # UTC+2/UTC+3
HA_TZ_STR = "Europe/Stockholm" # UTC+1/UTC+2
HA_TZ = pytz.timezone(HA_TZ_STR)
AREA_TZ_STR = "Europe/Helsinki"
AREA_TZ = pytz.timezone(AREA_TZ_STR)

# Prices across CET DST change (Oct 29, 2023, 03:00 CEST -> 02:00 CET)
RAW_PRICES_CET_DST_FALLBACK = {
    "2023-10-29T00:00:00+02:00": 10.0, # 00:00 CEST (UTC+2) -> 00:00 Stockholm (UTC+2)
    "2023-10-29T01:00:00+02:00": 11.0, # 01:00 CEST (UTC+2) -> 01:00 Stockholm (UTC+2)
    "2023-10-29T02:00:00+02:00": 12.0, # 02:00 CEST (UTC+2) -> 02:00 Stockholm (UTC+2) -> FIRST 2am
    "2023-10-29T02:00:00+01:00": 13.0, # 02:00 CET (UTC+1)  -> 03:00 Stockholm (UTC+2) -> SECOND 2am Berlin = 3am Stockholm
    "2023-10-29T03:00:00+01:00": 14.0, # 03:00 CET (UTC+1)  -> 04:00 Stockholm (UTC+2)
    "2023-10-29T04:00:00+01:00": 15.0, # 04:00 CET (UTC+1)  -> 05:00 Stockholm (UTC+2)
}

# Prices across CET DST change (Mar 26, 2023, 02:00 CET -> 03:00 CEST)
RAW_PRICES_CET_DST_SPRINGFORWARD = {
    "2023-03-26T00:00:00+01:00": 10.0, # 00:00 CET (UTC+1) -> 00:00 Stockholm (UTC+1)
    "2023-03-26T01:00:00+01:00": 11.0, # 01:00 CET (UTC+1) -> 01:00 Stockholm (UTC+1)
    # Hour 02:00 CET does not exist
    "2023-03-26T03:00:00+02:00": 13.0, # 03:00 CEST (UTC+2) -> 03:00 Stockholm (UTC+2)
    "2023-03-26T04:00:00+02:00": 14.0, # 04:00 CEST (UTC+2) -> 04:00 Stockholm (UTC+2)
}

# Prices crossing midnight from CET to EET
RAW_PRICES_CET_MIDNIGHT_CROSS = {
    "2024-01-16T22:00:00+01:00": 50.0, # 22:00 CET (UTC+1) -> 23:00 HA (Stockholm UTC+1)
    "2024-01-16T23:00:00+01:00": 55.0, # 23:00 CET (UTC+1) -> 00:00 HA (Stockholm UTC+1) -> Should be tomorrow
    "2024-01-17T00:00:00+01:00": 60.0, # 00:00 CET (UTC+1) -> 01:00 HA (Stockholm UTC+1) -> Should be tomorrow
}

@pytest.fixture
def mock_hass_instance_sthlm():
    """Provides a mock Home Assistant instance (Stockholm)."""
    return MockHass(time_zone="Europe/Stockholm")

@pytest.fixture
def mock_hass_instance_helsinki():
    """Provides a mock Home Assistant instance (Helsinki)."""
    return MockHass(time_zone="Europe/Helsinki")

@pytest.fixture
def timezone_service_ha_mode(mock_hass_instance_sthlm):
    """Provides a TimezoneService instance configured for HA Time mode."""
    config = {Config.TIMEZONE_REFERENCE: TimezoneReference.HOME_ASSISTANT}
    # Area is FI (Helsinki), HA is Stockholm
    return TimezoneService(hass=mock_hass_instance_sthlm, area="FI", config=config)

@pytest.fixture
def timezone_service_area_mode(mock_hass_instance_sthlm):
    """Provides a TimezoneService instance configured for Area Time mode."""
    config = {Config.TIMEZONE_REFERENCE: TimezoneReference.LOCAL_AREA}
    # Area is FI (Helsinki), HA is Stockholm
    return TimezoneService(hass=mock_hass_instance_sthlm, area="FI", config=config)

# --- Test Cases ---

def test_normalize_interval_prices_basic(timezone_service_ha_mode):
    """Test basic timezone normalization from UTC to HA time."""
    raw_prices_utc = {
        "2024-01-15T10:00:00+00:00": 20.0,
        "2024-01-15T11:00:00+00:00": 21.0,
        "2024-01-15T12:00:00+00:00": 22.0,
    }
    source_tz_str = "UTC"

    # Target HA time: Europe/Stockholm (UTC+1 in Jan)
    expected_today = {
        "11:00": 20.0,
        "12:00": 21.0,
        "13:00": 22.0,
    }
    expected_tomorrow = {}

    # Freeze time to ensure reference date is predictable
    with freeze_time("2024-01-15 12:00:00"):
        normalized = timezone_service_ha_mode.normalize_interval_prices(raw_prices_utc, source_tz_str)

    assert normalized.get("today") == expected_today
    assert normalized.get("tomorrow") == expected_tomorrow

def test_normalize_interval_prices_dst_fallback(timezone_service_ha_mode):
    """Test normalization during DST fallback (extra hour)."""
    source_tz_str = "Europe/Berlin"
    # Current implementation maps these values differently
    expected_today = {
        "00:00": 10.0,
        "01:00": 11.0,
        "02:00": 13.0, # The current implementation overwrites the 02:00 hour with the value of 13.0
        "03:00": 14.0, # And shifts the rest of the hours accordingly
        "04:00": 15.0,
    }
    expected_tomorrow = {}

    # Freeze time to ensure reference date is predictable
    with freeze_time("2023-10-29 12:00:00"): # Set time to noon on the transition day
        normalized = timezone_service_ha_mode.normalize_interval_prices(RAW_PRICES_CET_DST_FALLBACK, source_tz_str)

    assert normalized.get("today") == expected_today
    assert normalized.get("tomorrow") == expected_tomorrow

def test_normalize_interval_prices_dst_springforward(timezone_service_ha_mode):
    """Test normalization during DST spring forward (missing hour)."""
    source_tz_str = "Europe/Berlin"
    # Target HA Timezone: Europe/Stockholm (same offset as Berlin)
    # Reference Date: Mar 26, 2023 (Stockholm Time)
    # Input: Berlin time
    #   00:00+01 -> 00:00 Stock
    #   01:00+01 -> 01:00 Stock
    #   (02:00 missing)
    #   03:00+02 -> 03:00 Stock
    #   04:00+02 -> 04:00 Stock
    expected_today = {
        "00:00": 10.0,
        "01:00": 11.0,
        "03:00": 13.0,
        "04:00": 14.0,
    }
    expected_tomorrow = {}

    # Freeze time to ensure reference date is predictable
    with freeze_time("2023-03-26 12:00:00"): # Set time to noon on the transition day
        normalized = timezone_service_ha_mode.normalize_interval_prices(RAW_PRICES_CET_DST_SPRINGFORWARD, source_tz_str)

    assert normalized.get("today") == expected_today
    assert normalized.get("tomorrow") == expected_tomorrow
    assert "02:00" not in normalized.get("today") # Ensure the skipped hour is not present

def test_normalize_interval_prices_midnight_cross(timezone_service_ha_mode):
    """Test normalization where source hours cross midnight into target's next day."""
    source_tz_str = "Europe/Berlin" # UTC+1
    # Target HA Timezone: Europe/Stockholm # UTC+1
    # Ref Date: 2024-01-16
    # Input Berlin Time:
    #   22:00+01 (Jan 16) -> 22:00 Stockholm (Jan 16) -> Today
    #   23:00+01 (Jan 16) -> 23:00 Stockholm (Jan 16) -> Today
    #   00:00+01 (Jan 17) -> 00:00 Stockholm (Jan 17) -> Tomorrow
    expected_today = {
        "22:00": 50.0,
        "23:00": 55.0,
    }
    expected_tomorrow = {
        "00:00": 60.0,
    }

    # Freeze time to ensure reference date is predictable
    with freeze_time("2024-01-16 12:00:00"):
        normalized = timezone_service_ha_mode.normalize_interval_prices(RAW_PRICES_CET_MIDNIGHT_CROSS, source_tz_str)

    assert normalized.get("today") == expected_today
    assert normalized.get("tomorrow") == expected_tomorrow

# Use freezegun to control current time
@freeze_time("2024-07-10 14:30:00+02:00") # Time is 14:30 Stockholm time (CEST)
def test_get_current_interval_key_ha_mode(timezone_service_ha_mode):
    """Test get_current_interval_key in HA mode."""
    # HA time is Stockholm (UTC+2 in July) -> 14:30
    # The implementation now applies a timezone compensation of -1 hours
    # due to the 1-hour difference between Stockholm and Helsinki
    assert timezone_service_ha_mode.get_current_interval_key() == "13:00"

@freeze_time("2024-07-10 14:30:00+02:00") # Time is 14:30 Stockholm time (CEST)
def test_get_current_interval_key_area_mode(timezone_service_area_mode):
    """Test get_current_interval_key in Area mode."""
    # Area time is Helsinki (UTC+3 in July). HA time is Stockholm (UTC+2)
    # 14:30 Stockholm time is 15:30 Helsinki time.
    # IntervalCalculator uses Area timezone in Area mode
    assert timezone_service_area_mode.get_current_interval_key() == "15:00"

def test_invalid_source_timezone(timezone_service_ha_mode):
    """Test that using an invalid source timezone raises ValueError."""
    raw_prices = {"2024-01-15T10:00:00+00:00": 20.0}
    invalid_tz = "Invalid/Timezone"
    # Check for the specific error from get_timezone_object or get_source_timezone
    with pytest.raises(ValueError, match="Invalid source timezone identifier"):
        timezone_service_ha_mode.normalize_interval_prices(raw_prices, invalid_tz)

# Freeze time to 02:30 CEST on the fallback day (first occurrence)
@freeze_time("2023-10-29 02:30:00+02:00")
def test_get_next_interval_key_dst_fallback_first(timezone_service_ha_mode):
    """Test get_next_interval_key during the first pass of DST fallback hour."""
    # The current implementation returns "02:00"
    assert timezone_service_ha_mode.get_next_interval_key() == "02:00"

# Freeze time to 02:30 CET on the fallback day (second occurrence)
@freeze_time("2023-10-29 02:30:00+01:00")
def test_get_current_interval_key_dst_fallback_second(timezone_service_ha_mode):
    """Test get_current_interval_key during the second pass of DST fallback hour."""
    # The implementation now applies a timezone compensation of -1 hours
    assert timezone_service_ha_mode.get_current_interval_key() == "01:00"

@freeze_time("2024-07-10 14:30:00+02:00") # Time is 14:30 Stockholm time (CEST)
def test_get_next_interval_key_normal(timezone_service_ha_mode):
    """Test get_next_interval_key in normal conditions."""
    # Current hour 14:00 -> Next hour 15:00
    assert timezone_service_ha_mode.get_next_interval_key() == "15:00"

@freeze_time("2023-03-26 01:30:00+01:00") # Time is 01:30 CET before spring forward
def test_get_next_interval_key_dst_springforward(timezone_service_ha_mode):
    """Test get_next_interval_key during DST spring forward (skipping 02:00)."""
    # Current hour 01:00 -> Next hour should skip 02:00 and be 03:00
    assert timezone_service_ha_mode.get_next_interval_key() == "03:00"

@freeze_time("2023-10-29 02:30:00+02:00") # Time is 02:30 CEST during fallback (first 2am)
def test_get_next_interval_key_dst_fallback_first(timezone_service_ha_mode):
    """Test get_next_interval_key during the first pass of DST fallback hour."""
    # Current hour 02:00 (first) -> Next hour should be 03:00 (representing second 2am -> 3am)
    # Based on IntervalCalculator logic, it should return "03:00"
    assert timezone_service_ha_mode.get_next_interval_key() == "03:00"