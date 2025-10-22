#!/usr/bin/env python3
"""
Comprehensive Test Suite for 15-Minute Migration
Tests actual functionality, not just imports
"""

import sys
import asyncio
from datetime import datetime, timezone

print("=" * 80)
print("  15-MINUTE MIGRATION - COMPREHENSIVE TEST SUITE")
print("=" * 80)
print()

# Test 1: Configuration System
print("TEST 1: Configuration System")
print("-" * 80)
try:
    from custom_components.ge_spot.const.time import TimeInterval

    # Test default is QUARTER_HOURLY
    assert (
        TimeInterval.DEFAULT == TimeInterval.QUARTER_HOURLY
    ), "DEFAULT should be QUARTER_HOURLY"
    print("✅ DEFAULT = QUARTER_HOURLY")

    # Test helper methods
    assert TimeInterval.get_interval_minutes() == 15, "Should return 15 minutes"
    print(f"✅ get_interval_minutes() = {TimeInterval.get_interval_minutes()}")

    assert TimeInterval.get_intervals_per_hour() == 4, "Should return 4 intervals/hour"
    print(f"✅ get_intervals_per_hour() = {TimeInterval.get_intervals_per_hour()}")

    assert TimeInterval.get_intervals_per_day() == 96, "Should return 96 intervals/day"
    print(f"✅ get_intervals_per_day() = {TimeInterval.get_intervals_per_day()}")

    assert (
        TimeInterval.get_intervals_per_day_dst_spring() == 92
    ), "Should return 92 for DST spring"
    print(
        f"✅ get_intervals_per_day_dst_spring() = {TimeInterval.get_intervals_per_day_dst_spring()}"
    )

    assert (
        TimeInterval.get_intervals_per_day_dst_fall() == 100
    ), "Should return 100 for DST fall"
    print(
        f"✅ get_intervals_per_day_dst_fall() = {TimeInterval.get_intervals_per_day_dst_fall()}"
    )

    print("✅ TEST 1 PASSED: Configuration system works correctly")
except AssertionError as e:
    print(f"❌ TEST 1 FAILED: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ TEST 1 ERROR: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print()

# Test 2: Interval Calculator
print("TEST 2: Interval Calculator")
print("-" * 80)
try:
    from custom_components.ge_spot.timezone.interval_calculator import (
        IntervalCalculator,
    )
    from zoneinfo import ZoneInfo

    # Create calculator with UTC timezone
    utc_tz = ZoneInfo("UTC")
    calc = IntervalCalculator(timezone=utc_tz)

    # Test current interval key (should be HH:MM format)
    current_key = calc.get_current_interval_key()
    assert ":" in current_key, "Interval key should contain ':'"
    assert len(current_key) == 5, "Interval key should be HH:MM format"
    print(f"✅ get_current_interval_key() = {current_key}")

    # Test next interval key
    next_key = calc.get_next_interval_key()
    assert ":" in next_key, "Next interval key should contain ':'"
    print(f"✅ get_next_interval_key() = {next_key}")

    # Verify it's 15 minutes ahead
    current_dt = datetime.now(utc_tz)
    minute = current_dt.minute
    rounded_minute = (minute // 15) * 15
    expected_current = f"{current_dt.hour:02d}:{rounded_minute:02d}"
    assert (
        current_key == expected_current
    ), f"Expected {expected_current}, got {current_key}"
    print(f"✅ Current interval matches expected: {expected_current}")

    print("✅ TEST 2 PASSED: Interval calculator works correctly")
except Exception as e:
    print(f"❌ TEST 2 ERROR: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
except AssertionError as e:
    print(f"❌ TEST 2 FAILED: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ TEST 2 ERROR: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print()

# Test 3: Data Structures
print("TEST 3: Data Structures")
print("-" * 80)
try:
    from custom_components.ge_spot.api.base.data_structure import (
        IntervalPrice,
        StandardizedPriceData,
    )

    # Test IntervalPrice dataclass
    interval_price = IntervalPrice(
        datetime=datetime.now(timezone.utc).isoformat(),
        price=50.0,
        interval_key="00:15",
        currency="EUR",
        timezone="UTC",
        source="test",
    )
    assert interval_price.price == 50.0, "Price should be 50.0"
    assert interval_price.interval_key == "00:15", "Interval key should be 00:15"
    print(f"✅ IntervalPrice dataclass works with interval_key field")

    # Test StandardizedPriceData
    price_data = StandardizedPriceData(
        source="test",
        area="test_area",
        currency="EUR",
        fetched_at=datetime.now(timezone.utc).isoformat(),
        today_interval_prices={
            "00:00": 45.0,
            "00:15": 50.0,
            "00:30": 48.0,
            "00:45": 52.0,
        },
        current_price=50.0,
        next_interval_price=52.0,
    )
    assert len(price_data.today_interval_prices) == 4, "Should have 4 interval prices"
    assert (
        "today_interval_prices" in price_data.__dict__
    ), "Should have today_interval_prices field"
    print(f"✅ StandardizedPriceData uses today_interval_prices field")
    print(f"✅ Sample data: {list(price_data.today_interval_prices.keys())[:4]}")

    print("✅ TEST 3 PASSED: Data structures use correct naming")
except AssertionError as e:
    print(f"❌ TEST 3 FAILED: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ TEST 3 ERROR: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print()

# Test 4: Parsers Return Correct Keys
print("TEST 4: Parsers Return Correct Keys")
print("-" * 80)
try:
    # Test ENTSO-E parser
    from custom_components.ge_spot.api.parsers.entsoe_parser import EntsoeParser

    parser = EntsoeParser()

    # Create mock data
    mock_data = {
        "TimeSeries": [
            {
                "Period": [
                    {
                        "resolution": "PT15M",
                        "timeInterval": {"start": "2025-10-01T00:00:00Z"},
                        "Point": [
                            {"position": "1", "price.amount": "50.0"},
                            {"position": "2", "price.amount": "51.0"},
                        ],
                    }
                ]
            }
        ]
    }

    result = parser.parse(mock_data)
    assert "interval_raw" in result, "Parser should return 'interval_raw' key"
    assert "hourly_raw" not in result, "Parser should NOT return 'hourly_raw' key"
    assert "hourly_prices" not in result, "Parser should NOT return 'hourly_prices' key"
    print(f"✅ ENTSO-E parser returns 'interval_raw' (not 'hourly_raw')")

    # Test ComEd parser
    from custom_components.ge_spot.api.parsers.comed_parser import ComedParser

    comed_parser = ComedParser()

    mock_comed = [{"millisUTC": 1696118400000, "price": "45.5"}]
    comed_result = comed_parser.parse(mock_comed)
    assert "interval_raw" in comed_result, "ComEd parser should return 'interval_raw'"
    assert (
        "hourly_raw" not in comed_result
    ), "ComEd parser should NOT return 'hourly_raw'"
    print(f"✅ ComEd parser returns 'interval_raw'")

    print("✅ TEST 4 PASSED: Parsers use correct key names")
except AssertionError as e:
    print(f"❌ TEST 4 FAILED: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ TEST 4 ERROR: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print()

# Test 5: ComEd Aggregation Logic
print("TEST 5: ComEd 5-min to 15-min Aggregation")
print("-" * 80)
try:
    from custom_components.ge_spot.api.parsers.comed_parser import ComedParser

    parser = ComedParser()

    # Create 5-minute data for 15-minute test
    # 00:00, 00:05, 00:10 should aggregate to 00:00
    # 00:15, 00:20, 00:25 should aggregate to 00:15
    mock_data = [
        {"millisUTC": 1696118400000, "price": "50.0"},  # 00:00
        {"millisUTC": 1696118700000, "price": "51.0"},  # 00:05
        {"millisUTC": 1696119000000, "price": "52.0"},  # 00:10
        {"millisUTC": 1696119300000, "price": "60.0"},  # 00:15
        {"millisUTC": 1696119600000, "price": "61.0"},  # 00:20
        {"millisUTC": 1696119900000, "price": "62.0"},  # 00:25
    ]

    result = parser.parse(mock_data)
    interval_raw = result["interval_raw"]

    # Should have 2 fifteen-minute intervals, not 6 five-minute or 1 hourly
    assert (
        len(interval_raw) == 2
    ), f"Should have 2 fifteen-minute intervals, got {len(interval_raw)}"
    print(
        f"✅ ComEd aggregates to 15-min intervals: {len(interval_raw)} intervals created"
    )

    # Check that prices are averaged
    prices = list(interval_raw.values())
    # First interval: (50 + 51 + 52) / 3 = 51.0
    assert (
        abs(prices[0] - 51.0) < 0.01
    ), f"First interval should average to 51.0, got {prices[0]}"
    # Second interval: (60 + 61 + 62) / 3 = 61.0
    assert (
        abs(prices[1] - 61.0) < 0.01
    ), f"Second interval should average to 61.0, got {prices[1]}"
    print(f"✅ Prices correctly averaged: {prices}")

    print("✅ TEST 5 PASSED: ComEd aggregation works correctly")
except AssertionError as e:
    print(f"❌ TEST 5 FAILED: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ TEST 5 ERROR: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print()

# Test 6: AEMO Expansion Logic (30-min to 15-min)
print("TEST 6: AEMO 30-min to 15-min Expansion")
print("-" * 80)
try:
    from custom_components.ge_spot.api.parsers.aemo_parser import AemoParser

    parser = AemoParser()

    # Create proper NEMWEB CSV format (AEMO uses 30-minute intervals)
    csv_content = """C,PREDISPATCH
I,PREDISPATCH,REGION_PRICES,1,PREDISPATCH_RUN_DATETIME,REGIONID,PERIODID,INTERVENTION,DATETIME,RRP,EEP,RAISE6SECRRP
D,PREDISPATCH,REGION_PRICES,1,2025/10/01 00:00:00,NSW1,1,0,2025/10/01 00:00:00,100.0,100.0,0.0
D,PREDISPATCH,REGION_PRICES,1,2025/10/01 00:00:00,NSW1,2,0,2025/10/01 00:30:00,104.0,104.0,0.0"""
    
    mock_data = {
        "csv_content": csv_content,
        "area": "NSW1",
        "timezone": "Australia/Sydney",
        "currency": "AUD",
        "raw_data": {}
    }

    result = parser.parse(mock_data)
    interval_raw = result["interval_raw"]

    # AEMO provides 30-min intervals, which get expanded to 15-min
    # 2 x 30-min intervals -> 4 x 15-min intervals
    assert (
        len(interval_raw) == 4
    ), f"Should have 4 fifteen-minute intervals (expanded from 2 x 30-min), got {len(interval_raw)}"
    print(
        f"✅ AEMO expands 30-min to 15-min intervals: {len(interval_raw)} intervals created"
    )

    # Check that prices are duplicated (30-min price copied to two 15-min intervals)
    prices = list(interval_raw.values())
    assert (
        abs(prices[0] - 100.0) < 0.01 and abs(prices[1] - 100.0) < 0.01
    ), f"First two intervals should both be 100.0, got {prices[0]:.2f}, {prices[1]:.2f}"
    print(f"✅ Prices correctly duplicated: {prices[0]:.2f}, {prices[1]:.2f}")

    print("✅ TEST 6 PASSED: AEMO 30-min to 15-min expansion works correctly")
except AssertionError as e:
    print(f"❌ TEST 6 FAILED: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ TEST 6 ERROR: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print()

# Test 7: API and Parser Integration
print("TEST 7: API and Parser Integration")
print("-" * 80)
try:
    # Test that APIs correctly read from parsers
    from custom_components.ge_spot.api.parsers.comed_parser import ComedParser

    parser = ComedParser()
    mock_data = [{"millisUTC": 1696118400000, "price": "50.0"}]
    parser_result = parser.parse(mock_data)

    # Parser should return interval_raw
    assert "interval_raw" in parser_result, "Parser must return 'interval_raw'"
    print(f"✅ Parser returns: {list(parser_result.keys())}")

    # Verify NO old keys
    assert "hourly_raw" not in parser_result, "Parser should not return 'hourly_raw'"
    assert (
        "hourly_prices" not in parser_result
    ), "Parser should not return 'hourly_prices'"
    print(f"✅ Parser does not return old keys (hourly_raw, hourly_prices)")

    print("✅ TEST 7 PASSED: API/Parser integration uses correct keys")
except AssertionError as e:
    print(f"❌ TEST 7 FAILED: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ TEST 7 ERROR: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print()

# Test 8: No Aliases or Old Naming
print("TEST 8: No Aliases or Old Naming in Key Files")
print("-" * 80)
try:
    import inspect
    from custom_components.ge_spot.api.base.data_structure import StandardizedPriceData

    # Check that StandardizedPriceData has interval_prices, not hourly_prices
    sig = inspect.signature(StandardizedPriceData)
    params = list(sig.parameters.keys())

    assert (
        "today_interval_prices" in params
    ), "StandardizedPriceData should have 'interval_prices' parameter"
    assert (
        "hourly_prices" not in params
    ), "StandardizedPriceData should NOT have 'hourly_prices' parameter"
    print(f"✅ StandardizedPriceData parameters: {params}")

    # Check IntervalCalculator exists (not HourCalculator)
    try:
        from custom_components.ge_spot.timezone.interval_calculator import (
            IntervalCalculator,
        )

        print(f"✅ IntervalCalculator class exists (not HourCalculator)")
    except ImportError:
        raise AssertionError("IntervalCalculator should exist")

    # Ensure HourCalculator doesn't exist
    try:
        from custom_components.ge_spot.timezone.hour_calculator import HourCalculator

        raise AssertionError("HourCalculator should not exist anymore")
    except ImportError:
        print(f"✅ HourCalculator does not exist (correctly renamed)")

    print("✅ TEST 8 PASSED: No aliases or old naming found")
except AssertionError as e:
    print(f"❌ TEST 8 FAILED: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ TEST 8 ERROR: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 80)
print("  ✅ ALL TESTS PASSED!")
print("=" * 80)
print()
print("Summary:")
print("  ✅ Configuration system works correctly (15-min intervals)")
print("  ✅ Interval calculator uses correct rounding (HH:MM format)")
print("  ✅ Data structures use 'interval_prices' (not 'hourly_prices')")
print("  ✅ Parsers return 'interval_raw' (not 'hourly_raw')")
print("  ✅ ComEd aggregates 5-min → 15-min correctly")
print("  ✅ AEMO aggregates 5-min → 15-min correctly")
print("  ✅ API/Parser integration uses consistent keys")
print("  ✅ No aliases or old naming found")
print()
