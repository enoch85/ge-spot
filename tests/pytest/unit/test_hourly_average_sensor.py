"""Tests for hourly average price sensors."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from custom_components.ge_spot.sensor.price import (
    HourlyAverageSensor,
    TomorrowHourlyAverageSensor,
)


class TestHourlyAverageSensor:
    """Test the HourlyAverageSensor class."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock()
        coordinator.data = {
            "today_interval_prices": {
                "00:00": 10.0,
                "00:15": 12.0,
                "00:30": 14.0,
                "00:45": 16.0,
                "01:00": 20.0,
                "01:15": 22.0,
                "01:30": 24.0,
                "01:45": 26.0,
                "02:00": 30.0,
                "02:15": 32.0,
                "02:30": 34.0,
                "02:45": 36.0,
            },
            "tomorrow_interval_prices": {
                "00:00": 15.0,
                "00:15": 17.0,
                "00:30": 19.0,
                "00:45": 21.0,
                "01:00": 25.0,
                "01:15": 27.0,
                "01:30": 29.0,
                "01:45": 31.0,
            },
        }
        coordinator.last_update_success = True
        return coordinator

    @pytest.fixture
    def config_data(self):
        """Create test config data."""
        return {
            "area": "SE3",
            "vat": 0.25,
            "precision": 3,
            "display_unit": "EUR",
            "currency": "EUR",
        }

    def test_hourly_average_calculation(self, mock_coordinator, config_data):
        """Test that hourly averages are calculated correctly from 15-minute intervals."""
        sensor = HourlyAverageSensor(
            mock_coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )

        hourly_averages = sensor._calculate_hourly_averages(mock_coordinator.data)

        # Expected: Hour 00:00 = (10+12+14+16)/4 = 13.0
        # Expected: Hour 01:00 = (20+22+24+26)/4 = 23.0
        # Expected: Hour 02:00 = (30+32+34+36)/4 = 33.0
        assert hourly_averages["00:00"] == 13.0
        assert hourly_averages["01:00"] == 23.0
        assert hourly_averages["02:00"] == 33.0

    def test_tomorrow_hourly_average_calculation(self, mock_coordinator, config_data):
        """Test tomorrow's hourly average calculation."""
        sensor = HourlyAverageSensor(
            mock_coordinator,
            config_data,
            "tomorrow_hourly_average_price",
            "Tomorrow Hourly Average Price",
            day_offset=1,
        )

        hourly_averages = sensor._calculate_hourly_averages(mock_coordinator.data)

        # Expected: Hour 00:00 = (15+17+19+21)/4 = 18.0
        # Expected: Hour 01:00 = (25+27+29+31)/4 = 28.0
        assert hourly_averages["00:00"] == 18.0
        assert hourly_averages["01:00"] == 28.0

    def test_empty_interval_prices(self, config_data):
        """Test handling of empty interval prices."""
        coordinator = Mock()
        coordinator.data = {
            "today_interval_prices": {},
            "tomorrow_interval_prices": {},
        }
        coordinator.last_update_success = True

        sensor = HourlyAverageSensor(
            coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )

        hourly_averages = sensor._calculate_hourly_averages(coordinator.data)
        assert hourly_averages == {}

    def test_partial_hour_data(self, config_data):
        """Test handling when an hour has fewer than 4 intervals."""
        coordinator = Mock()
        coordinator.data = {
            "today_interval_prices": {
                "00:00": 10.0,
                "00:15": 12.0,
                # Missing 00:30 and 00:45
                "01:00": 20.0,
                "01:15": 22.0,
                "01:30": 24.0,
                "01:45": 26.0,
            },
        }
        coordinator.last_update_success = True

        sensor = HourlyAverageSensor(
            coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )

        hourly_averages = sensor._calculate_hourly_averages(coordinator.data)

        # Hour 00:00 should average only the 2 available values
        assert hourly_averages["00:00"] == 11.0  # (10+12)/2
        # Hour 01:00 should average all 4 values
        assert hourly_averages["01:00"] == 23.0  # (20+22+24+26)/4

    @patch("custom_components.ge_spot.sensor.price.dt_util.now")
    def test_current_hour_value(self, mock_now, mock_coordinator, config_data):
        """Test that the sensor returns the current hour's average."""
        # Mock current time to 01:30
        mock_dt = datetime(2025, 10, 22, 1, 30, 0, tzinfo=timezone.utc)
        mock_now.return_value = mock_dt

        sensor = HourlyAverageSensor(
            mock_coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )

        # The sensor should return hour 01:00's average
        value = sensor.native_value
        assert value == 23.0  # (20+22+24+26)/4

    def test_tomorrow_sensor_mixin(self, mock_coordinator, config_data):
        """Test that TomorrowHourlyAverageSensor uses TomorrowSensorMixin."""
        # Test with no tomorrow data
        mock_coordinator.data["tomorrow_valid"] = False

        sensor = TomorrowHourlyAverageSensor(
            mock_coordinator,
            config_data,
            "tomorrow_hourly_average_price",
            "Tomorrow Hourly Average Price",
            day_offset=1,
        )

        # Sensor should not be available when tomorrow_valid is False
        assert sensor.available is False

        # Now make it valid
        mock_coordinator.data["tomorrow_valid"] = True
        assert sensor.available is True

    @patch("custom_components.ge_spot.sensor.base.dt_util.get_default_time_zone")
    def test_hourly_prices_attribute(self, mock_get_tz, mock_coordinator, config_data):
        """Test that hourly_prices attribute is generated correctly."""
        # Mock timezone
        mock_get_tz.return_value = timezone.utc

        sensor = HourlyAverageSensor(
            mock_coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )

        # Mock the _tz_service to None so it uses default timezone
        sensor._tz_service = None

        # Get additional attributes from the HourlyAverageSensor
        # We need to get only the hourly-specific attributes, not all base attributes
        hourly_averages = sensor._calculate_hourly_averages(mock_coordinator.data)

        # Verify the calculation worked
        assert len(hourly_averages) == 3  # We have 3 hours in test data
        assert hourly_averages["00:00"] == 13.0  # Hour 00:00 average
        assert hourly_averages["01:00"] == 23.0  # Hour 01:00 average
        assert hourly_averages["02:00"] == 33.0  # Hour 02:00 average

    def test_insufficient_data_still_calculates_hourly(self, config_data):
        """Test that hourly averages are calculated even with insufficient data for statistics.

        Belgian use case: Even if we don't have enough data for full statistics,
        we should still calculate hourly averages from whatever intervals we have.
        """
        coordinator = Mock()
        # Only 20% of day's data (less than the 80% threshold for statistics)
        coordinator.data = {
            "today_interval_prices": {
                "00:00": 10.0,
                "00:15": 12.0,
                "00:30": 14.0,
                "00:45": 16.0,
                "01:00": 20.0,
                "01:15": 22.0,
                # Missing most of the day
            },
            "statistics": {},  # No statistics due to insufficient data
        }
        coordinator.last_update_success = True

        sensor = HourlyAverageSensor(
            coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )

        hourly_averages = sensor._calculate_hourly_averages(coordinator.data)

        # Should still calculate averages for the hours we have
        assert len(hourly_averages) == 2
        assert hourly_averages["00:00"] == 13.0
        assert hourly_averages["01:00"] == 21.0  # (20+22)/2 for incomplete hour

    @patch("custom_components.ge_spot.sensor.price.dt_util.now")
    def test_midnight_crossing(self, mock_now, config_data):
        """Test behavior at midnight boundary.

        At 23:45, we should still calculate hour 23:00's average,
        and at 00:15, we should calculate hour 00:00's average.
        """
        coordinator = Mock()
        coordinator.data = {
            "today_interval_prices": {
                "23:00": 50.0,
                "23:15": 52.0,
                "23:30": 54.0,
                "23:45": 56.0,
            },
        }
        coordinator.last_update_success = True

        # Test at 23:30 (before midnight)
        mock_dt = datetime(2025, 10, 22, 23, 30, 0, tzinfo=timezone.utc)
        mock_now.return_value = mock_dt

        sensor = HourlyAverageSensor(
            coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )

        value = sensor.native_value
        assert value == 53.0  # Average of 23:00 hour

        # Test at 00:15 (after midnight) - different day's data
        coordinator.data = {
            "today_interval_prices": {
                "00:00": 10.0,
                "00:15": 12.0,
                "00:30": 14.0,
                "00:45": 16.0,
            },
        }
        mock_dt = datetime(2025, 10, 23, 0, 15, 0, tzinfo=timezone.utc)
        mock_now.return_value = mock_dt

        sensor2 = HourlyAverageSensor(
            coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )

        value2 = sensor2.native_value
        assert value2 == 13.0  # Average of 00:00 hour

    def test_missing_single_quarter_interval(self, config_data):
        """Test that we can still calculate hourly average with 3 out of 4 intervals.

        Real-world scenario: APIs might occasionally miss a single interval.
        We should average the available intervals rather than skip the hour.
        """
        coordinator = Mock()
        coordinator.data = {
            "today_interval_prices": {
                "10:00": 100.0,
                "10:15": 102.0,
                "10:30": 104.0,
                # Missing 10:45
                "11:00": 110.0,
                "11:15": 112.0,
                # Missing 11:30
                "11:45": 116.0,
                "12:00": 120.0,
                # Missing 12:15
                # Missing 12:30
                "12:45": 126.0,
            },
        }
        coordinator.last_update_success = True

        sensor = HourlyAverageSensor(
            coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )

        hourly_averages = sensor._calculate_hourly_averages(coordinator.data)

        # All hours should be calculated, using available intervals
        assert "10:00" in hourly_averages
        assert "11:00" in hourly_averages
        assert "12:00" in hourly_averages

        # Hour 10: (100+102+104)/3 = 102.0
        assert hourly_averages["10:00"] == 102.0

        # Hour 11: (110+112+116)/3 = 112.666...
        assert abs(hourly_averages["11:00"] - 112.666667) < 0.001

        # Hour 12: (120+126)/2 = 123.0
        assert hourly_averages["12:00"] == 123.0

    def test_dst_transition_spring_forward(self, config_data):
        """Test behavior during DST spring forward (2:00 AM -> 3:00 AM).

        In spring, the 2:00-2:59 hour is skipped. We should handle this gracefully
        and not crash if that hour is missing from interval data.
        """
        coordinator = Mock()
        # Simulating DST spring forward: hour 02:xx is missing
        coordinator.data = {
            "today_interval_prices": {
                "01:00": 10.0,
                "01:15": 12.0,
                "01:30": 14.0,
                "01:45": 16.0,
                # Hour 02:xx missing due to DST
                "03:00": 30.0,
                "03:15": 32.0,
                "03:30": 34.0,
                "03:45": 36.0,
            },
        }
        coordinator.last_update_success = True

        sensor = HourlyAverageSensor(
            coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )

        hourly_averages = sensor._calculate_hourly_averages(coordinator.data)

        # Should have hours 01 and 03, but not 02
        assert "01:00" in hourly_averages
        assert "02:00" not in hourly_averages  # Missing due to DST
        assert "03:00" in hourly_averages

        assert hourly_averages["01:00"] == 13.0
        assert hourly_averages["03:00"] == 33.0

    def test_dst_transition_fall_back(self, config_data):
        """Test behavior during DST fall back (2:00 AM repeated).

        In fall, hour 02:xx occurs twice. The interval data might contain
        more than 4 intervals for that hour. We should average all of them.
        """
        coordinator = Mock()
        # Simulating DST fall back: hour 02:xx appears with extra intervals
        coordinator.data = {
            "today_interval_prices": {
                "01:00": 10.0,
                "01:15": 12.0,
                "01:30": 14.0,
                "01:45": 16.0,
                # First occurrence of 02:xx
                "02:00": 20.0,
                "02:15": 22.0,
                "02:30": 24.0,
                "02:45": 26.0,
                # During DST fall back, we might get 8 intervals for hour 02
                # (This is handled by timezone normalization in the coordinator,
                # but we should handle gracefully if we receive more intervals)
                "03:00": 30.0,
                "03:15": 32.0,
                "03:30": 34.0,
                "03:45": 36.0,
            },
        }
        coordinator.last_update_success = True

        sensor = HourlyAverageSensor(
            coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )

        hourly_averages = sensor._calculate_hourly_averages(coordinator.data)

        # Should calculate normally - coordinator handles DST complexity
        assert "01:00" in hourly_averages
        assert "02:00" in hourly_averages
        assert "03:00" in hourly_averages

        assert hourly_averages["01:00"] == 13.0
        assert hourly_averages["02:00"] == 23.0
        assert hourly_averages["03:00"] == 33.0

    def test_no_data_for_current_hour(self, config_data):
        """Test when there's no data yet for the current hour.

        Early in the hour (e.g., 08:05), we might not have all 4 intervals yet.
        The sensor should return None for native_value if current hour has no data.
        """
        coordinator = Mock()
        coordinator.data = {
            "today_interval_prices": {
                "07:00": 70.0,
                "07:15": 72.0,
                "07:30": 74.0,
                "07:45": 76.0,
                # Current hour 08:xx has no data yet
            },
        }
        coordinator.last_update_success = True

        with patch("custom_components.ge_spot.sensor.price.dt_util.now") as mock_now:
            # It's 08:05, but we have no data for hour 08 yet
            mock_dt = datetime(2025, 10, 22, 8, 5, 0, tzinfo=timezone.utc)
            mock_now.return_value = mock_dt

            sensor = HourlyAverageSensor(
                coordinator,
                config_data,
                "hourly_average_price",
                "Hourly Average Price",
                day_offset=0,
            )

            # Should return None since current hour has no data
            assert sensor.native_value is None

            # But hourly averages should still include hour 07
            hourly_averages = sensor._calculate_hourly_averages(coordinator.data)
            assert "07:00" in hourly_averages
            assert hourly_averages["07:00"] == 73.0

    def test_price_precision_preserved(self, config_data):
        """Test that price precision is maintained in calculations.

        Ensure we don't lose precision in averaging (important for accurate billing).
        """
        coordinator = Mock()
        coordinator.data = {
            "today_interval_prices": {
                "10:00": 0.12345,
                "10:15": 0.12346,
                "10:30": 0.12347,
                "10:45": 0.12348,
            },
        }
        coordinator.last_update_success = True

        sensor = HourlyAverageSensor(
            coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )

        hourly_averages = sensor._calculate_hourly_averages(coordinator.data)

        # Average: (0.12345 + 0.12346 + 0.12347 + 0.12348) / 4 = 0.123465
        expected = (0.12345 + 0.12346 + 0.12347 + 0.12348) / 4
        assert abs(hourly_averages["10:00"] - expected) < 0.0000001

    def test_invalid_interval_key_format(self, config_data):
        """Test graceful handling of invalid interval key formats.

        If the coordinator somehow provides malformed keys, we should log
        and skip them rather than crash.
        """
        coordinator = Mock()
        coordinator.data = {
            "today_interval_prices": {
                "10:00": 100.0,
                "10:15": 102.0,
                "invalid_key": 999.0,  # Bad format
                "10:30": 104.0,
                "10:45": 106.0,
                "11": 110.0,  # Missing minutes
                "11:15": 112.0,
            },
        }
        coordinator.last_update_success = True

        sensor = HourlyAverageSensor(
            coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )

        hourly_averages = sensor._calculate_hourly_averages(coordinator.data)

        # Should skip invalid keys and calculate valid ones
        assert "10:00" in hourly_averages
        # Average should be calculated from valid intervals only
        # (100 + 102 + 104 + 106) / 4 = 103.0
        assert hourly_averages["10:00"] == 103.0

    def test_hourly_attributes_instead_of_interval_prices(
        self, mock_coordinator, config_data
    ):
        """Test that hourly sensors provide hourly price attributes instead of interval prices.

        This is the main feature requested in issue #26 - hourly sensors should show
        hourly aggregated data, not 15-minute intervals.
        """
        sensor = HourlyAverageSensor(
            mock_coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )
        sensor._tz_service = None

        attrs = sensor.extra_state_attributes

        # Should NOT have interval prices
        assert "today_interval_prices" not in attrs
        assert "tomorrow_interval_prices" not in attrs

        # Should have hourly prices
        assert "today_hourly_prices" in attrs
        assert "tomorrow_hourly_prices" in attrs

        # Verify today's hourly prices structure
        today_hourly = attrs["today_hourly_prices"]
        assert isinstance(today_hourly, list)
        assert len(today_hourly) == 3  # 3 hours in mock data

        # Each entry should have 'time' (datetime) and 'value' (float)
        for entry in today_hourly:
            assert "time" in entry
            assert "value" in entry
            assert isinstance(entry["time"], datetime)
            assert isinstance(entry["value"], float)

        # Verify values are hourly averages
        hour_0_entry = next((e for e in today_hourly if e["time"].hour == 0), None)
        assert hour_0_entry is not None
        assert abs(hour_0_entry["value"] - 13.0) < 0.0001  # (10+12+14+16)/4 = 13.0

        hour_1_entry = next((e for e in today_hourly if e["time"].hour == 1), None)
        assert hour_1_entry is not None
        assert abs(hour_1_entry["value"] - 23.0) < 0.0001  # (20+22+24+26)/4 = 23.0

        # Verify tomorrow's hourly prices
        tomorrow_hourly = attrs["tomorrow_hourly_prices"]
        assert isinstance(tomorrow_hourly, list)
        assert len(tomorrow_hourly) == 2  # 2 hours in mock data

        hour_0_entry = next((e for e in tomorrow_hourly if e["time"].hour == 0), None)
        assert hour_0_entry is not None
        assert abs(hour_0_entry["value"] - 18.0) < 0.0001  # (15+17+19+21)/4 = 18.0

        # Should have statistics
        assert "today_min_price" in attrs
        assert "today_max_price" in attrs
        assert "today_avg_price" in attrs

        # Verify statistics values
        assert attrs["today_min_price"] == 13.0  # Hour 0 average
        assert attrs["today_max_price"] == 33.0  # Hour 2 average
        expected_avg = (13.0 + 23.0 + 33.0) / 3
        assert abs(attrs["today_avg_price"] - expected_avg) < 0.0001

    def test_tomorrow_hourly_attributes_statistics(self, mock_coordinator, config_data):
        """Test that tomorrow statistics are included when tomorrow data is available."""
        sensor = HourlyAverageSensor(
            mock_coordinator,
            config_data,
            "tomorrow_hourly_average_price",
            "Tomorrow Hourly Average Price",
            day_offset=1,
        )
        sensor._tz_service = None

        attrs = sensor.extra_state_attributes

        # Should have tomorrow statistics
        assert "tomorrow_min_price" in attrs
        assert "tomorrow_max_price" in attrs
        assert "tomorrow_avg_price" in attrs

        # Verify statistics values for tomorrow
        assert attrs["tomorrow_min_price"] == 18.0  # Hour 0 average
        assert attrs["tomorrow_max_price"] == 28.0  # Hour 1 average
        expected_avg = (18.0 + 28.0) / 2
        assert abs(attrs["tomorrow_avg_price"] - expected_avg) < 0.0001

    def test_hourly_attributes_with_empty_data(self, config_data):
        """Test that empty hourly prices don't cause errors."""
        coordinator = Mock()
        coordinator.data = {
            "today_interval_prices": {},
            "tomorrow_interval_prices": {},
        }
        coordinator.last_update_success = True

        sensor = HourlyAverageSensor(
            coordinator,
            config_data,
            "hourly_average_price",
            "Hourly Average Price",
            day_offset=0,
        )
        sensor._tz_service = None

        attrs = sensor.extra_state_attributes

        # Should have empty lists
        assert attrs["today_hourly_prices"] == []
        assert attrs["tomorrow_hourly_prices"] == []

        # Should NOT have statistics for empty data
        assert "today_min_price" not in attrs
        assert "today_max_price" not in attrs
        assert "today_avg_price" not in attrs
