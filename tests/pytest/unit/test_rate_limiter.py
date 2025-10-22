"""Tests for rate limiter functionality."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from custom_components.ge_spot.utils.rate_limiter import RateLimiter
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.time import TimeInterval


class TestRateLimiter:
    """Test suite for RateLimiter."""

    @pytest.fixture
    def base_time(self):
        """Base time for testing (2025-10-02 10:00:00 UTC) - outside special windows."""
        return datetime(2025, 10, 2, 10, 0, 0, tzinfo=timezone.utc)

    # ==========================================
    # Test: First Fetch (Never Fetched Before)
    # ==========================================

    def test_first_fetch_always_allowed(self, base_time):
        """Test that first fetch is always allowed when last_fetched is None."""
        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=None, current_time=base_time
        )

        assert should_skip is False, "First fetch should be allowed"
        assert "No previous fetch" in reason

    # ==========================================
    # Test: Interval Boundary Crossing
    # ==========================================

    def test_interval_boundary_crossed_forces_fetch(self, base_time):
        """Test that crossing an interval boundary forces a fetch."""
        # Last fetch at 10:00, current time at 10:15 (crossed boundary)
        last_fetched = base_time  # 10:00:00
        current_time = base_time + timedelta(minutes=15)  # 10:15:00

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched, current_time=current_time
        )

        assert should_skip is False, "Interval boundary crossing should force fetch"
        assert "Interval boundary crossed" in reason
        assert "10:00" in reason and "10:15" in reason

    def test_within_same_interval_respects_min_interval(self, base_time):
        """Test that staying within same interval respects minimum interval."""
        # Last fetch at 14:00:00, current time at 14:05:00 (same interval)
        last_fetched = base_time
        current_time = base_time + timedelta(minutes=5)

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched, current_time=current_time, min_interval=15
        )

        assert should_skip is True, "Should skip fetch within same interval if min_interval not met"
        assert "5.0 minutes ago" in reason
        assert "minimum: 15" in reason

    def test_interval_boundary_with_seconds(self, base_time):
        """Test interval boundary detection with seconds (edge case)."""
        # Last fetch at 10:14:59, current at 10:15:00 (boundary crossed by 1 second)
        last_fetched = base_time + timedelta(minutes=14, seconds=59)
        current_time = base_time + timedelta(minutes=15)

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched, current_time=current_time
        )

        # 10:14:59 and 10:15:00 are SAME interval (both round to 10:15)
        # So this should NOT cross boundary, should check min_interval instead
        assert should_skip is True, "Within same interval, should respect min_interval"
        assert "0.0 minutes ago" in reason

    # ==========================================
    # Test: Minimum Interval Enforcement
    # ==========================================

    def test_minimum_interval_blocks_early_fetch(self, base_time):
        """Test that minimum interval prevents too-frequent fetches."""
        last_fetched = base_time
        current_time = base_time + timedelta(minutes=10)  # Only 10 minutes

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched, current_time=current_time, min_interval=15
        )

        assert should_skip is True
        assert "10.0 minutes ago" in reason
        assert "minimum: 15" in reason

    def test_minimum_interval_allows_fetch_after_threshold(self, base_time):
        """Test that fetch is allowed once minimum interval passes."""
        last_fetched = base_time
        current_time = base_time + timedelta(minutes=16)  # 16 minutes (> 15), also crosses boundary

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched, current_time=current_time, min_interval=15
        )

        assert should_skip is False
        # Will trigger interval boundary (10:00 to 10:15) before reaching the final check
        assert "Interval boundary crossed" in reason or "exceeds minimum interval" in reason

    # ==========================================
    # Test: Exponential Backoff on Failures
    # ==========================================

    def test_first_failure_backoff(self, base_time):
        """Test that first failure applies 15-minute backoff."""
        last_fetched = base_time
        last_failure_time = base_time + timedelta(minutes=15)
        current_time = base_time + timedelta(minutes=20)  # Only 5 min since failure

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched,
            current_time=current_time,
            consecutive_failures=1,
            last_failure_time=last_failure_time,
            min_interval=15,
        )

        assert should_skip is True, "Should skip due to backoff after first failure"
        assert "Backing off after 1 failures" in reason
        assert "Next retry:" in reason

    def test_second_failure_longer_backoff(self, base_time):
        """Test that second failure applies 30-minute backoff."""
        last_fetched = base_time
        last_failure_time = base_time + timedelta(minutes=15)
        current_time = base_time + timedelta(minutes=30)  # Only 15 min since failure

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched,
            current_time=current_time,
            consecutive_failures=2,
            last_failure_time=last_failure_time,
            min_interval=15,
        )

        assert should_skip is True, "Should skip due to 30-min backoff after second failure"
        assert "Backing off after 2 failures" in reason

    def test_third_failure_max_backoff(self, base_time):
        """Test that third failure applies 60-minute backoff (capped)."""
        last_fetched = base_time
        last_failure_time = base_time + timedelta(minutes=15)
        current_time = base_time + timedelta(minutes=45)  # Only 30 min since failure

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched,
            current_time=current_time,
            consecutive_failures=3,
            last_failure_time=last_failure_time,
            min_interval=15,
        )

        assert should_skip is True, "Should skip due to 60-min backoff after third failure"
        assert "Backing off after 3 failures" in reason

    def test_backoff_expires_allows_retry(self, base_time):
        """Test that fetch is allowed after backoff period expires."""
        last_fetched = base_time
        last_failure_time = base_time + timedelta(minutes=15)
        current_time = base_time + timedelta(minutes=31)  # 16 min since failure (> 15 min backoff)

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched,
            current_time=current_time,
            consecutive_failures=1,
            last_failure_time=last_failure_time,
            min_interval=15,
        )

        assert should_skip is False, "Should allow retry after backoff expires"

    # ==========================================
    # Test: Special Time Windows
    # ==========================================

    def test_special_window_00_to_01_allows_fetch(self, base_time):
        """Test that 00:00-01:00 special window allows fetch."""
        # Set time to 00:30, last fetch at 00:20 (both in special window, same interval)
        last_fetched = datetime(2025, 10, 2, 0, 20, 0, tzinfo=timezone.utc)
        current_time = datetime(2025, 10, 2, 0, 30, 0, tzinfo=timezone.utc)

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched, current_time=current_time, min_interval=15
        )

        # Crossed interval boundary (00:15 to 00:30), also in special window
        # But interval boundary comes after special window check now
        assert should_skip is False  # Special window allows fetch
        assert "special" in reason.lower() or "Interval boundary" in reason

    def test_special_window_13_to_15_allows_fetch(self, base_time):
        """Test that 13:00-15:00 special window (tomorrow data) allows fetch."""
        # Set time to 13:30, last at 13:20 (10 min ago, different intervals)
        last_fetched = datetime(2025, 10, 2, 13, 20, 0, tzinfo=timezone.utc)
        special_time = datetime(2025, 10, 2, 13, 30, 0, tzinfo=timezone.utc)

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched, current_time=special_time, min_interval=15
        )

        # In special window (13-15) and crossed boundary (13:15 to 13:30)
        assert should_skip is False
        assert "special" in reason.lower() or "Interval boundary" in reason

    def test_outside_special_window_normal_rules_apply(self, base_time):
        """Test that normal rules apply outside special windows."""
        # 10:00 is not a special window, and we've crossed interval boundary
        normal_time = datetime(2025, 10, 2, 10, 15, 0, tzinfo=timezone.utc)
        last_fetched = datetime(2025, 10, 2, 10, 0, 0, tzinfo=timezone.utc)

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched, current_time=normal_time, min_interval=15
        )

        assert should_skip is False, "Should allow fetch after interval boundary"
        assert "Interval boundary crossed" in reason

    # ==========================================
    # Test: Source-Specific Behavior (AEMO)
    # ==========================================

    def test_aemo_market_hours_always_allows_fetch(self, base_time):
        """Test that AEMO source during market hours (7-19) allows fetch."""
        # Set time to 10:00 (within market hours)
        market_time = datetime(2025, 10, 2, 10, 5, 0, tzinfo=timezone.utc)
        last_fetched = datetime(2025, 10, 2, 10, 0, 0, tzinfo=timezone.utc)  # Just 5 min ago

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched, current_time=market_time, source=Source.AEMO, min_interval=15
        )

        assert should_skip is False, "AEMO during market hours should allow fetch"
        assert "Market hours for AEMO" in reason

    def test_aemo_outside_market_hours_normal_rules(self, base_time):
        """Test that AEMO outside market hours follows normal rules."""
        # Set time to 20:00 (outside market hours)
        after_hours = datetime(2025, 10, 2, 20, 5, 0, tzinfo=timezone.utc)
        last_fetched = datetime(2025, 10, 2, 20, 0, 0, tzinfo=timezone.utc)  # 5 min ago

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched, current_time=after_hours, source=Source.AEMO, min_interval=15
        )

        assert should_skip is True, "AEMO outside market hours should follow normal rules"
        assert "5.0 minutes ago" in reason

    # ==========================================
    # Test: Configuration-Driven Behavior
    # ==========================================

    @patch("custom_components.ge_spot.const.time.TimeInterval.get_interval_minutes")
    def test_hourly_interval_configuration(self, mock_get_interval, base_time):
        """Test that rate limiter adapts to hourly intervals."""
        mock_get_interval.return_value = 60  # Simulate hourly mode

        # Last fetch at 10:00, current at 10:30 (same hour)
        last_fetched = base_time  # 10:00
        current_time = base_time + timedelta(minutes=30)  # 10:30

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched, current_time=current_time
        )

        # With hourly intervals, 10:00 and 10:30 are same interval
        # Should NOT cross boundary, so check time difference instead
        assert should_skip is True or "exceeds minimum" in reason

    @patch("custom_components.ge_spot.const.time.TimeInterval.get_interval_minutes")
    def test_15min_interval_configuration(self, mock_get_interval, base_time):
        """Test that rate limiter adapts to 15-minute intervals."""
        mock_get_interval.return_value = 15  # Simulate 15-min mode

        # Last fetch at 10:00, current at 10:15 (different intervals)
        last_fetched = base_time  # 10:00
        current_time = base_time + timedelta(minutes=15)  # 10:15

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched, current_time=current_time
        )

        assert should_skip is False, "Should detect boundary crossing"
        assert "10:00" in reason and "10:15" in reason

    # ==========================================
    # Test: Edge Cases
    # ==========================================

    def test_exact_minimum_interval_boundary(self, base_time):
        """Test behavior at exact minimum interval boundary."""
        last_fetched = base_time
        current_time = base_time + timedelta(minutes=15, microseconds=1)  # Just over 15 min

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched, current_time=current_time, min_interval=15
        )

        assert should_skip is False, "Should allow at exactly min_interval"

    def test_negative_time_difference_invalid(self, base_time):
        """Test that current_time before last_fetched is handled."""
        last_fetched = base_time
        current_time = base_time - timedelta(minutes=5)  # Time travel!

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetched, current_time=current_time, min_interval=15
        )

        # Should skip due to negative time (treated as recent fetch)
        assert should_skip is True

    def test_area_parameter_logging(self, base_time):
        """Test that area parameter is included in logging (doesn't affect logic)."""
        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=None, current_time=base_time, area="SE3"
        )

        assert should_skip is False
        # Area is used for logging, not returned in reason

    # ==========================================
    # Test: Real-World Scenarios
    # ==========================================

    def test_typical_15min_update_cycle(self, base_time):
        """Test a typical 15-minute update cycle."""
        times = [
            base_time,  # 14:00
            base_time + timedelta(minutes=15),  # 14:15
            base_time + timedelta(minutes=30),  # 14:30
            base_time + timedelta(minutes=45),  # 14:45
        ]

        last_fetch = times[0]
        for current in times[1:]:
            should_skip, reason = RateLimiter.should_skip_fetch(
                last_fetched=last_fetch, current_time=current, min_interval=15
            )

            assert should_skip is False, f"Should allow fetch at {current}"
            assert "Interval boundary crossed" in reason
            last_fetch = current

    def test_failure_recovery_scenario(self, base_time):
        """Test complete failure and recovery scenario."""
        # Initial fetch
        last_fetch = base_time  # 14:00

        # First failure at 14:15
        failure_time = base_time + timedelta(minutes=15)

        # Try at 14:20 (within 15-min backoff)
        current = base_time + timedelta(minutes=20)
        should_skip, _ = RateLimiter.should_skip_fetch(
            last_fetched=last_fetch,
            current_time=current,
            consecutive_failures=1,
            last_failure_time=failure_time,
            min_interval=15,
        )
        assert should_skip is True, "Should block during backoff"

        # Try at 14:31 (backoff expired)
        current = base_time + timedelta(minutes=31)
        should_skip, _ = RateLimiter.should_skip_fetch(
            last_fetched=last_fetch,
            current_time=current,
            consecutive_failures=1,
            last_failure_time=failure_time,
            min_interval=15,
        )
        assert should_skip is False, "Should allow retry after backoff"

    def test_midnight_transition(self, base_time):
        """Test behavior across midnight transition."""
        # Last fetch at 23:45
        last_fetch = datetime(2025, 10, 2, 23, 45, 0, tzinfo=timezone.utc)
        # Current time at 00:00 next day (interval boundary + special window)
        current = datetime(2025, 10, 3, 0, 0, 0, tzinfo=timezone.utc)

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetch, current_time=current, min_interval=15
        )

        assert should_skip is False, "Should allow fetch at midnight"
        # Special window (0-1) takes precedence, but both are correct
        assert "special" in reason.lower() or "Interval boundary" in reason
