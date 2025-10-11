"""Test grace period bypassing rate limiting."""
import pytest
from datetime import datetime, timedelta
from custom_components.ge_spot.utils.rate_limiter import RateLimiter


class TestGracePeriodRateLimiting:
    """Test that grace period correctly bypasses rate limiting."""

    def test_grace_period_bypasses_minimum_interval(self):
        """Test that grace period allows fetch even when minimum interval not met."""
        last_fetch = datetime(2025, 10, 11, 10, 0, 0)
        current_time = datetime(2025, 10, 11, 10, 5, 0)  # Only 5 minutes later
        min_interval = 15  # Normally requires 15 minutes

        # Without grace period - should be rate limited
        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetch,
            current_time=current_time,
            min_interval=min_interval,
            in_grace_period=False
        )
        assert should_skip is True
        assert "Last fetch was only" in reason

        # With grace period - should bypass rate limiting
        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetch,
            current_time=current_time,
            min_interval=min_interval,
            in_grace_period=True
        )
        assert should_skip is False
        assert "grace period" in reason.lower()
        assert "bypassing rate limiting" in reason.lower()

    def test_grace_period_bypasses_backoff(self):
        """Test that grace period bypasses exponential backoff after failures."""
        last_fetch = datetime(2025, 10, 11, 10, 0, 0)
        last_failure = datetime(2025, 10, 11, 10, 5, 0)
        current_time = datetime(2025, 10, 11, 10, 10, 0)  # Only 5 minutes after failure
        consecutive_failures = 2  # Would normally require 30min backoff

        # Without grace period - should be in backoff
        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetch,
            current_time=current_time,
            consecutive_failures=consecutive_failures,
            last_failure_time=last_failure,
            min_interval=15,
            in_grace_period=False
        )
        assert should_skip is True
        assert "Backing off" in reason

        # With grace period - should bypass backoff
        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetch,
            current_time=current_time,
            consecutive_failures=consecutive_failures,
            last_failure_time=last_failure,
            min_interval=15,
            in_grace_period=True
        )
        assert should_skip is False
        assert "grace period" in reason.lower()

    def test_grace_period_with_never_fetched(self):
        """Test that never fetched takes precedence over grace period."""
        current_time = datetime(2025, 10, 11, 10, 0, 0)

        # Never fetched should always return False regardless of grace period
        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=None,
            current_time=current_time,
            in_grace_period=True
        )
        assert should_skip is False
        assert "No previous fetch" in reason

        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=None,
            current_time=current_time,
            in_grace_period=False
        )
        assert should_skip is False
        assert "No previous fetch" in reason

    def test_grace_period_scenario_for_fallback(self):
        """Test realistic scenario: HA restart with fallback sources."""
        # Scenario: HA just restarted (grace period active)
        # Primary source (entsoe) was fetched 2 minutes ago
        # Need to try fallback source (nordpool) immediately
        
        last_fetch_entsoe = datetime(2025, 10, 11, 17, 55, 0)
        current_time = datetime(2025, 10, 11, 17, 57, 0)  # 2 minutes later
        
        # Try to fetch from nordpool (fallback source)
        # Without grace period - would be rate limited
        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetch_entsoe,
            current_time=current_time,
            min_interval=15,
            source="nordpool",
            area="SE4",
            in_grace_period=False
        )
        assert should_skip is True, "Without grace period, should be rate limited"
        
        # With grace period - should allow immediate fetch for fallback
        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetch_entsoe,
            current_time=current_time,
            min_interval=15,
            source="nordpool",
            area="SE4",
            in_grace_period=True
        )
        assert should_skip is False, "Grace period should bypass rate limiting for fallback"
        assert "grace period" in reason.lower()
        assert "bypassing rate limiting" in reason.lower()

    def test_grace_period_default_false(self):
        """Test that grace period defaults to False when not specified."""
        last_fetch = datetime(2025, 10, 11, 10, 0, 0)
        current_time = datetime(2025, 10, 11, 10, 5, 0)
        
        # Not passing in_grace_period should default to False
        should_skip, reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetch,
            current_time=current_time,
            min_interval=15
        )
        # Should be rate limited since grace period defaults to False
        assert should_skip is True
        assert "Last fetch was only" in reason
