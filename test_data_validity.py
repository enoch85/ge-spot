#!/usr/bin/env python3
"""Test the new DataValidity architecture."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add custom_components to path
sys.path.insert(0, str(Path(__file__).parent / "custom_components"))

from ge_spot.coordinator.data_validity import DataValidity
from ge_spot.coordinator.fetch_decision import FetchDecisionMaker

print("=" * 80)
print("Testing DataValidity Architecture")
print("=" * 80)

# Test 1: DataValidity creation and properties
print("\n1. Testing DataValidity creation...")
now = datetime(2025, 10, 2, 13, 0, 0)  # October 2, 2025 at 13:00
last_valid = datetime(2025, 10, 3, 23, 45, 0)  # Tomorrow at 23:45

validity = DataValidity(
    last_valid_interval=last_valid,
    interval_count=192,
    has_current_interval=True
)

print(f"   Last valid interval: {validity.last_valid_interval}")
print(f"   Data valid until: {validity.data_valid_until}")
print(f"   Interval count: {validity.interval_count}")
print(f"   Hours remaining: {validity.hours_remaining(now):.2f}")
print(f"   Is valid: {validity.is_valid()}")

assert validity.data_valid_until == last_valid
assert validity.interval_count == 192
assert validity.is_valid()
hours = validity.hours_remaining(now)
assert 34 < hours < 35  # Should be ~34.75 hours
print("   ✅ DataValidity creation works correctly")

# Test 2: Hours remaining calculation
print("\n2. Testing hours_remaining at different times...")
test_times = [
    (datetime(2025, 10, 2, 13, 0, 0), "13:00 (fetch time)", 34.75),
    (datetime(2025, 10, 2, 14, 0, 0), "14:00 (1h later)", 33.75),
    (datetime(2025, 10, 2, 23, 0, 0), "23:00 (evening)", 24.75),
    (datetime(2025, 10, 3, 0, 0, 0), "00:00 (midnight)", 23.75),
    (datetime(2025, 10, 3, 12, 0, 0), "12:00 (next day)", 11.75),
    (datetime(2025, 10, 3, 22, 0, 0), "22:00 (near end)", 1.75),
]

for test_time, desc, expected_hours in test_times:
    hours = validity.hours_remaining(test_time)
    print(f"   {desc}: {hours:.2f} hours (expected ~{expected_hours:.2f})")
    assert abs(hours - expected_hours) < 0.1
print("   ✅ Hours remaining calculation correct")

# Test 3: is_valid checks
print("\n3. Testing is_valid...")
assert validity.is_valid()  # Has data

# Empty data
empty = DataValidity(last_valid_interval=None, interval_count=0)
assert not empty.is_valid()

# Has interval but no count
partial = DataValidity(last_valid_interval=last_valid, interval_count=0)
assert not partial.is_valid()
print("   ✅ is_valid works correctly")

# Test 4: Edge cases
print("\n4. Testing edge cases...")

# Empty data
empty_validity = DataValidity(
    last_valid_interval=None,
    interval_count=0
)
assert empty_validity.hours_remaining(now) == 0
assert not empty_validity.is_valid()
print("   ✅ Empty data handled correctly")

# Expired data
expired_validity = DataValidity(
    last_valid_interval=datetime(2025, 10, 1, 23, 45, 0),  # Yesterday
    interval_count=96,
    has_current_interval=True
)
remaining = expired_validity.hours_remaining(now)
assert remaining == 0  # max(0, ...) prevents negative
assert expired_validity.is_valid()  # Still "valid" structure, just expired
print("   ✅ Expired data detected correctly")

# Test 5: FetchDecisionMaker with new logic
print("\n5. Testing FetchDecisionMaker with DataValidity...")

class MockTimezoneService:
    """Mock timezone service for testing."""
    
    def get_current_interval_key(self):
        return "13:00"

tz_service = MockTimezoneService()
decision_maker = FetchDecisionMaker(tz_service)

# Test scenario 1: Plenty of data remaining (34 hours)
print("\n   Scenario 1: 34 hours of data remaining at 13:00")
validity_plenty = DataValidity(
    last_valid_interval=datetime(2025, 10, 3, 23, 45, 0),
    interval_count=192,
    today_interval_count=96,
    tomorrow_interval_count=96,  # We have tomorrow's data
    has_current_interval=True  # We have data for now
)
should_fetch, reason = decision_maker.should_fetch(
    now=datetime(2025, 10, 2, 13, 0, 0),
    last_fetch=datetime(2025, 10, 2, 12, 0, 0),
    fetch_interval_minutes=15,
    data_validity=validity_plenty
)
print(f"   Should fetch: {should_fetch}")
print(f"   Reason: {reason}")
assert not should_fetch  # Should NOT fetch with 34h remaining
print("   ✅ Correctly skips fetch with plenty of data")

# Test scenario 2: Low data remaining (1.5 hours)
print("\n   Scenario 2: 1.5 hours of data remaining at 22:00")
validity_low = DataValidity(
    last_valid_interval=datetime(2025, 10, 2, 23, 45, 0),
    interval_count=96,
    today_interval_count=96,
    tomorrow_interval_count=0,  # No tomorrow data
    has_current_interval=True
)
should_fetch, reason = decision_maker.should_fetch(
    now=datetime(2025, 10, 2, 22, 0, 0),
    last_fetch=datetime(2025, 10, 2, 13, 0, 0),
    fetch_interval_minutes=15,
    data_validity=validity_low
)
print(f"   Should fetch: {should_fetch}")
print(f"   Reason: {reason}")
assert should_fetch  # SHOULD fetch with < 2h remaining
print("   ✅ Correctly triggers fetch when data running low")

# Test scenario 3: No data at all
print("\n   Scenario 3: No data available")
validity_empty = DataValidity(
    last_valid_interval=None,
    interval_count=0
)
should_fetch, reason = decision_maker.should_fetch(
    now=datetime(2025, 10, 2, 13, 0, 0),
    last_fetch=None,
    fetch_interval_minutes=15,
    data_validity=validity_empty
)
print(f"   Should fetch: {should_fetch}")
print(f"   Reason: {reason}")
assert should_fetch  # MUST fetch with no data
print("   ✅ Correctly triggers urgent fetch with no data")

# Test scenario 4: Special fetch window (13:00-14:00) with data expiring today
print("\n   Scenario 4: Special fetch window at 13:00, need tomorrow's data")
validity_need_tomorrow = DataValidity(
    last_valid_interval=datetime(2025, 10, 2, 23, 45, 0),  # Only have today
    interval_count=96,
    today_interval_count=96,
    tomorrow_interval_count=0,  # Missing tomorrow
    has_current_interval=True
)
should_fetch, reason = decision_maker.should_fetch(
    now=datetime(2025, 10, 2, 13, 0, 0),
    last_fetch=datetime(2025, 10, 2, 12, 0, 0),
    fetch_interval_minutes=15,
    data_validity=validity_need_tomorrow
)
print(f"   Should fetch: {should_fetch}")
print(f"   Reason: {reason}")
assert should_fetch  # SHOULD fetch in special window when need tomorrow
print("   ✅ Correctly fetches in special window when need tomorrow's data")

# Test scenario 5: Special fetch window but already have tomorrow
print("\n   Scenario 5: Special fetch window at 13:15, already have tomorrow")
validity_have_tomorrow = DataValidity(
    last_valid_interval=datetime(2025, 10, 3, 23, 45, 0),  # Have tomorrow
    interval_count=192,
    today_interval_count=96,
    tomorrow_interval_count=96,  # Have tomorrow
    has_current_interval=True
)
should_fetch, reason = decision_maker.should_fetch(
    now=datetime(2025, 10, 2, 13, 15, 0),
    last_fetch=datetime(2025, 10, 2, 13, 0, 0),
    fetch_interval_minutes=15,
    data_validity=validity_have_tomorrow
)
print(f"   Should fetch: {should_fetch}")
print(f"   Reason: {reason}")
assert not should_fetch  # Should NOT fetch if already have tomorrow
print("   ✅ Correctly skips fetch when already have tomorrow's data")

# Test scenario 6: Midnight transition (should NOT need to fetch)
print("\n   Scenario 6: Midnight transition with tomorrow's data")
validity_midnight = DataValidity(
    last_valid_interval=datetime(2025, 10, 3, 23, 45, 0),
    interval_count=192,
    today_interval_count=96,
    tomorrow_interval_count=96,
    has_current_interval=True
)
should_fetch, reason = decision_maker.should_fetch(
    now=datetime(2025, 10, 3, 0, 0, 0),
    last_fetch=datetime(2025, 10, 2, 13, 0, 0),
    fetch_interval_minutes=15,
    data_validity=validity_midnight
)
print(f"   Should fetch: {should_fetch}")
print(f"   Reason: {reason}")
assert not should_fetch  # Should NOT fetch at midnight if have tomorrow's data!
print("   ✅ Correctly skips midnight fetch when data valid")

# Test scenario 7: Rate limiting with valid data
print("\n   Scenario 7: Rate limited but have valid data")
validity_rate_limited = DataValidity(
    last_valid_interval=datetime(2025, 10, 3, 23, 45, 0),
    interval_count=192,
    today_interval_count=96,
    tomorrow_interval_count=96,
    has_current_interval=True
)
should_fetch, reason = decision_maker.should_fetch(
    now=datetime(2025, 10, 2, 13, 10, 0),
    last_fetch=datetime(2025, 10, 2, 13, 0, 0),  # Just fetched 10 min ago
    fetch_interval_minutes=15,
    data_validity=validity_rate_limited
)
print(f"   Should fetch: {should_fetch}")
print(f"   Reason: {reason}")
assert not should_fetch  # Should NOT fetch when rate limited and have data
print("   ✅ Correctly respects rate limiting when have valid data")

print("\n" + "=" * 80)
print("✅ ALL TESTS PASSED!")
print("=" * 80)
print("\nData Validity Architecture is working correctly!")
print("\nKey achievements:")
print("  ✅ Clear 'hours remaining' instead of confusing 'complete_data' boolean")
print("  ✅ No midnight fetch needed when have tomorrow's data")
print("  ✅ Safety buffer (2h) triggers fetch at right time")
print("  ✅ Special fetch window (13:00-14:00) handled correctly")
print("  ✅ Rate limiting works with data validity")
print("  ✅ Graceful handling of edge cases (no data, expired data)")
