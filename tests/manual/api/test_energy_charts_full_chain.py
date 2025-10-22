#!/usr/bin/env python3
"""Manual test for Energy-Charts API - Full chain with REAL API calls.

This test makes actual API calls to Energy-Charts to verify:
1. API client can fetch real data
2. Parser can process real responses
3. Data structure matches expectations
4. All bidding zones work correctly

Run from project root:
    python tests/manual/api/test_energy_charts_full_chain.py
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from custom_components.ge_spot.api.energy_charts import EnergyChartsAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency


async def test_single_area(api: EnergyChartsAPI, area: str):
    """Test fetching and parsing data for a single area."""
    print(f"\n{'='*80}")
    print(f"Testing Area: {area}")
    print(f"{'='*80}")

    try:
        # Fetch raw data
        print(f"📡 Fetching data from Energy-Charts API...")
        raw_data = await api.fetch_raw_data(area)

        if not raw_data:
            print(f"❌ No data returned for {area}")
            return False

        # Validate raw data structure
        print(f"✅ Raw data received")
        print(f"   Keys: {list(raw_data.keys())}")

        assert "raw_data" in raw_data, "Missing 'raw_data' key"
        assert "timezone" in raw_data, "Missing 'timezone' key"
        assert "currency" in raw_data, "Missing 'currency' key"
        assert "area" in raw_data, "Missing 'area' key"
        assert "source" in raw_data, "Missing 'source' key"

        # Validate raw API response
        raw_api_response = raw_data["raw_data"]
        assert isinstance(
            raw_api_response, dict
        ), f"raw_data should be dict, got {type(raw_api_response)}"
        assert "unix_seconds" in raw_api_response, "Missing 'unix_seconds' in raw_data"
        assert "price" in raw_api_response, "Missing 'price' in raw_data"

        unix_seconds = raw_api_response["unix_seconds"]
        prices = raw_api_response["price"]

        print(f"   Timezone: {raw_data['timezone']}")
        print(f"   Currency: {raw_data['currency']}")
        print(f"   Source: {raw_data['source']}")
        print(f"   Data points: {len(unix_seconds)}")

        assert len(unix_seconds) > 0, "unix_seconds array is empty"
        assert len(prices) > 0, "price array is empty"
        assert len(unix_seconds) == len(
            prices
        ), f"Array length mismatch: {len(unix_seconds)} vs {len(prices)}"

        # Validate metadata
        assert (
            raw_data["timezone"] == "Europe/Berlin"
        ), f"Expected Europe/Berlin, got {raw_data['timezone']}"
        assert raw_data["currency"] == Currency.EUR, f"Expected EUR, got {raw_data['currency']}"
        assert (
            raw_data["source"] == Source.ENERGY_CHARTS
        ), f"Expected energy_charts, got {raw_data['source']}"
        assert raw_data["area"] == area, f"Expected {area}, got {raw_data['area']}"

        # Check data quality
        print(f"\n📊 Raw Data Quality Check:")
        print(f"   First timestamp: {datetime.fromtimestamp(unix_seconds[0])}")
        print(f"   Last timestamp: {datetime.fromtimestamp(unix_seconds[-1])}")
        print(f"   Price range: {min(prices):.2f} - {max(prices):.2f} EUR/MWh")
        print(f"   Average price: {sum(prices)/len(prices):.2f} EUR/MWh")

        # Validate timestamps are sequential
        for i in range(1, min(5, len(unix_seconds))):
            diff = unix_seconds[i] - unix_seconds[i - 1]
            print(f"   Interval {i}: {diff} seconds ({diff/60:.0f} minutes)")

        # Parse the data
        print(f"\n🔄 Parsing data...")
        parsed_data = api.parser.parse(raw_data)

        assert parsed_data is not None, "Parser returned None"
        assert isinstance(parsed_data, dict), "Parsed data should be a dictionary"

        # Validate parsed structure
        print(f"✅ Parsed data structure:")
        print(f"   Keys: {list(parsed_data.keys())}")

        required_fields = ["interval_raw", "currency", "timezone", "source", "source_unit", "area"]
        for field in required_fields:
            assert field in parsed_data, f"Missing required field: {field}"

        # Validate parsed metadata
        assert (
            parsed_data["source"] == Source.ENERGY_CHARTS
        ), f"Expected energy_charts, got {parsed_data['source']}"
        assert (
            parsed_data["currency"] == Currency.EUR
        ), f"Expected EUR, got {parsed_data['currency']}"
        assert (
            parsed_data["timezone"] == "Europe/Berlin"
        ), f"Expected Europe/Berlin, got {parsed_data['timezone']}"
        assert (
            parsed_data["source_unit"] == "MWh"
        ), f"Expected MWh, got {parsed_data['source_unit']}"
        assert parsed_data["area"] == area, f"Expected {area}, got {parsed_data['area']}"

        # Validate interval data
        interval_raw = parsed_data["interval_raw"]
        assert isinstance(
            interval_raw, dict
        ), f"interval_raw should be dict, got {type(interval_raw)}"
        assert len(interval_raw) > 0, "interval_raw is empty"

        print(f"   Interval count: {len(interval_raw)}")
        print(f"   Expected: ~96 (15-minute intervals for 1 day)")

        # Check interval timestamps are ISO format
        sample_keys = list(interval_raw.keys())[:3]
        print(f"   Sample timestamps: {sample_keys}")

        for timestamp in sample_keys:
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                assert "T" in timestamp, f"Timestamp not in ISO format: {timestamp}"
            except ValueError as e:
                print(f"❌ Invalid timestamp format: {timestamp}")
                raise

        # Validate prices
        sample_prices = [(k, v) for k, v in list(interval_raw.items())[:5]]
        print(f"\n📈 Sample parsed prices (first 5):")
        for ts, price in sample_prices:
            print(f"   {ts}: {price:.2f} EUR/MWh")

        # Price validation
        all_prices = list(interval_raw.values())
        assert all(isinstance(p, (int, float)) for p in all_prices), "All prices should be numeric"

        min_price = min(all_prices)
        max_price = max(all_prices)
        avg_price = sum(all_prices) / len(all_prices)

        print(f"\n💰 Price Statistics:")
        print(f"   Minimum: {min_price:.2f} EUR/MWh")
        print(f"   Maximum: {max_price:.2f} EUR/MWh")
        print(f"   Average: {avg_price:.2f} EUR/MWh")

        # Sanity check on price range
        assert -200 <= min_price <= 1000, f"Minimum price {min_price} outside reasonable range"
        assert -200 <= max_price <= 1000, f"Maximum price {max_price} outside reasonable range"

        # Check interval spacing
        sorted_timestamps = sorted(interval_raw.keys())
        if len(sorted_timestamps) >= 2:
            print(f"\n⏱️  Interval Spacing Check (first 5):")
            for i in range(1, min(6, len(sorted_timestamps))):
                ts1 = datetime.fromisoformat(sorted_timestamps[i - 1].replace("Z", "+00:00"))
                ts2 = datetime.fromisoformat(sorted_timestamps[i].replace("Z", "+00:00"))
                diff_minutes = (ts2 - ts1).total_seconds() / 60
                print(
                    f"   {sorted_timestamps[i-1]} -> {sorted_timestamps[i]}: {diff_minutes:.0f} min"
                )

                # Energy-Charts provides native 15-minute data
                assert (
                    10 <= diff_minutes <= 20
                ), f"Expected ~15 min intervals, got {diff_minutes} min"

        # License info check
        if "license_info" in parsed_data:
            print(f"\n📄 License Info: {parsed_data['license_info']}")

        print(f"\n✅ {area}: ALL CHECKS PASSED")
        return True

    except Exception as e:
        print(f"\n❌ {area}: TEST FAILED")
        print(f"   Error: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run full chain tests for multiple bidding zones."""
    print(
        f"""
{'='*80}
Energy-Charts API - Full Chain Test (REAL API CALLS)
{'='*80}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Testing: API fetch → Parser → Validation

⚠️  WARNING: This test makes REAL API calls to Energy-Charts
⚠️  Please ensure you have internet connectivity
⚠️  Rate limiting may apply
{'='*80}
"""
    )

    # Initialize API client
    api = EnergyChartsAPI()

    # Test multiple bidding zones
    test_areas = [
        "DE-LU",  # Germany-Luxembourg (main market)
        "FR",  # France
        "NL",  # Netherlands
        "BE",  # Belgium
        "AT",  # Austria
    ]

    results = {}

    for area in test_areas:
        success = await test_single_area(api, area)
        results[area] = success

        # Small delay to avoid rate limiting
        if area != test_areas[-1]:
            print(f"\n⏳ Waiting 2 seconds before next request...")
            await asyncio.sleep(2)

    # Summary
    print(f"\n{'='*80}")
    print(f"TEST SUMMARY")
    print(f"{'='*80}")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total - passed

    for area, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{area:10} {status}")

    print(f"\n{'='*80}")
    print(f"Total: {total} | Passed: {passed} | Failed: {failed}")
    print(f"{'='*80}")

    if failed == 0:
        print(f"\n🎉 ALL TESTS PASSED! Energy-Charts integration is working correctly.")
        return 0
    else:
        print(f"\n⚠️  SOME TESTS FAILED. Please review the errors above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
