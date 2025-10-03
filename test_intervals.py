#!/usr/bin/env python3
"""Test script to verify 15-minute interval functionality."""
import sys
sys.path.insert(0, '/workspaces/ge-spot')

from custom_components.ge_spot.const.time import TimeInterval
from custom_components.ge_spot.timezone.service import TimezoneService
from datetime import datetime
import pytz

print("=" * 80)
print("TESTING 15-MINUTE INTERVAL CONFIGURATION")
print("=" * 80)

# Test 1: TimeInterval configuration
print("\n1. TimeInterval Configuration:")
print(f"   - DEFAULT: {TimeInterval.DEFAULT}")
print(f"   - Interval minutes: {TimeInterval.get_interval_minutes()}")
print(f"   - Intervals per hour: {TimeInterval.get_intervals_per_hour()}")
print(f"   - Intervals per day: {TimeInterval.get_intervals_per_day()}")
print(f"   - Intervals per day (DST spring): {TimeInterval.get_intervals_per_day_dst_spring()}")
print(f"   - Intervals per day (DST fall): {TimeInterval.get_intervals_per_day_dst_fall()}")

expected_intervals = 96
actual_intervals = TimeInterval.get_intervals_per_day()
if actual_intervals == expected_intervals:
    print(f"   ✅ PASS: Intervals per day = {actual_intervals}")
else:
    print(f"   ❌ FAIL: Expected {expected_intervals}, got {actual_intervals}")

# Test 2: TimezoneService ranges
print("\n2. TimezoneService Range Generation:")
try:
    config = {"timezone": "Europe/Stockholm", "area": "SE4"}
    tz_service = TimezoneService(config)
    
    today_range = tz_service.get_today_range()
    tomorrow_range = tz_service.get_tomorrow_range()
    
    print(f"   - Today range length: {len(today_range)}")
    print(f"   - Today first 5 keys: {today_range[:5]}")
    print(f"   - Today last 5 keys: {today_range[-5:]}")
    print(f"   - Tomorrow range length: {len(tomorrow_range)}")
    
    if len(today_range) == expected_intervals:
        print(f"   ✅ PASS: Today range has {expected_intervals} intervals")
    else:
        print(f"   ❌ FAIL: Expected {expected_intervals} intervals, got {len(today_range)}")
        
    if len(tomorrow_range) == expected_intervals:
        print(f"   ✅ PASS: Tomorrow range has {expected_intervals} intervals")
    else:
        print(f"   ❌ FAIL: Expected {expected_intervals} intervals, got {len(tomorrow_range)}")
        
    # Check format
    if all(":" in key and len(key) == 5 for key in today_range):
        print(f"   ✅ PASS: All keys in HH:MM format")
    else:
        print(f"   ❌ FAIL: Some keys not in HH:MM format")
        
except Exception as e:
    print(f"   ❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Interval calculator
print("\n3. IntervalCalculator:")
try:
    from custom_components.ge_spot.timezone.interval_calculator import IntervalCalculator
    
    stockholm_tz = pytz.timezone('Europe/Stockholm')
    calc = IntervalCalculator(timezone=stockholm_tz, system_timezone=stockholm_tz)
    
    current_key = calc.get_current_interval_key()
    next_key = calc.get_next_interval_key()
    
    print(f"   - Current interval key: {current_key}")
    print(f"   - Next interval key: {next_key}")
    
    if ":" in current_key and len(current_key) == 5:
        print(f"   ✅ PASS: Current key in HH:MM format")
    else:
        print(f"   ❌ FAIL: Current key not in HH:MM format: {current_key}")
        
    if ":" in next_key and len(next_key) == 5:
        print(f"   ✅ PASS: Next key in HH:MM format")
    else:
        print(f"   ❌ FAIL: Next key not in HH:MM format: {next_key}")
        
    # Test that next key is 15 minutes after current
    current_parts = current_key.split(":")
    next_parts = next_key.split(":")
    current_total_mins = int(current_parts[0]) * 60 + int(current_parts[1])
    next_total_mins = int(next_parts[0]) * 60 + int(next_parts[1])
    diff = (next_total_mins - current_total_mins) % (24 * 60)
    
    if diff == 15:
        print(f"   ✅ PASS: Next key is 15 minutes after current")
    else:
        print(f"   ❌ FAIL: Expected 15 minute difference, got {diff}")
        
except Exception as e:
    print(f"   ❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
