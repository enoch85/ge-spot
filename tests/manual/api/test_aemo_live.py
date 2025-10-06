"""Integration test for AEMO NEMWEB API (live data)."""

import asyncio
import sys
from pathlib import Path

# Add custom_components to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from custom_components.ge_spot.api.aemo import AemoAPI
from custom_components.ge_spot.api.parsers.aemo_parser import AemoParser


async def test_aemo_live():
    """Test live AEMO NEMWEB data fetch and parse."""
    print("\n" + "=" * 70)
    print("AEMO NEMWEB Live Integration Test")
    print("=" * 70)
    
    test_region = "NSW1"
    
    print(f"\n1. Testing region: {test_region}")
    print("-" * 70)
    
    # Initialize API
    config = {"area": test_region}
    api = AemoAPI(config=config)
    parser = AemoParser()
    
    try:
        # Fetch raw data
        print("\n2. Fetching data from NEMWEB...")
        raw_data = await api.fetch_raw_data(area=test_region)
        
        if not raw_data:
            print("❌ FAILED: No data returned from API")
            return False
        
        print(f"✓ API fetch successful")
        print(f"  - CSV size: {len(raw_data.get('csv_content', '')):,} characters")
        print(f"  - Timezone: {raw_data.get('timezone')}")
        print(f"  - Currency: {raw_data.get('currency')}")
        
        # Parse data
        print("\n3. Parsing CSV data...")
        parsed_data = parser.parse(raw_data)
        
        if not parsed_data or not parsed_data.get("interval_raw"):
            print("❌ FAILED: Parser returned no interval data")
            return False
        
        interval_raw = parsed_data["interval_raw"]
        print(f"✓ Parser successful")
        print(f"  - Intervals parsed: {len(interval_raw)}")
        print(f"  - Source interval: {parsed_data.get('source_interval_minutes')} minutes")
        
        # Validate data
        print("\n4. Validating data...")
        
        # Check interval count (should have data, exact count varies)
        if len(interval_raw) == 0:
            print("❌ FAILED: No intervals in parsed data")
            return False
        
        print(f"✓ Interval count: {len(interval_raw)} intervals")
        
        # Check prices
        prices = list(interval_raw.values())
        min_price = min(prices)
        max_price = max(prices)
        avg_price = sum(prices) / len(prices)
        
        print(f"\n5. Price statistics:")
        print(f"  - Minimum: ${min_price:>8.2f}/MWh")
        print(f"  - Maximum: ${max_price:>8.2f}/MWh")
        print(f"  - Average: ${avg_price:>8.2f}/MWh")
        
        # AEMO typical range: -$1000 to $16,600/MWh
        if min_price < -2000 or max_price > 20000:
            print(f"⚠️  WARNING: Prices outside typical range")
        else:
            print(f"✓ Prices within reasonable range")
        
        # Show sample data
        print(f"\n6. Sample intervals (first 5):")
        for i, (timestamp, price) in enumerate(list(interval_raw.items())[:5]):
            print(f"  {timestamp}: ${price:>8.2f}/MWh")
        
        # Check metadata
        print(f"\n7. Metadata validation:")
        print(f"  - Source: {parsed_data.get('source')}")
        print(f"  - Area: {parsed_data.get('area')}")
        print(f"  - Timezone: {parsed_data.get('timezone')}")
        print(f"  - Currency: {parsed_data.get('currency')}")
        print(f"  - Source unit: {parsed_data.get('source_unit')}")
        
        print("\n" + "=" * 70)
        print("✓ TEST PASSED")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n❌ FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run test."""
    print("\n🧪 Starting AEMO NEMWEB integration test...")
    
    success = await test_aemo_live()
    
    if success:
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Test failed!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
