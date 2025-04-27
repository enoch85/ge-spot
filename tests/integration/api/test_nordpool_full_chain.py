import sys
import os
# Go up two levels to reach the workspace root where custom_components is located
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from custom_components.ge_spot.api.nordpool import NordpoolAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.const.areas import AreaMapping
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService

from datetime import datetime, timezone
import pytz

async def main():
    area = "SE4"
    api = NordpoolAPI()
    print(f"Fetching Nordpool data for area: {area}")
    raw_data = await api.fetch_raw_data(area=area)
    print("Raw data keys:", list(raw_data.keys()))
    print("Raw data sample (truncated):", str(raw_data)[:500])

    # Parse raw data
    parsed_data = await api.parse_raw_data(raw_data)
    print("Parsed data keys:", list(parsed_data.keys()))
    hourly_prices = parsed_data.get("hourly_prices", {})
    print(f"Parsed hourly_prices keys ({len(hourly_prices)}):", list(hourly_prices.keys()))
    print("parsed_data['hourly_prices']:", hourly_prices)

    # Print the contents of multiAreaEntries for today (move before early return)
    today_data = raw_data.get('today', {})
    multi_area_entries = today_data.get('multiAreaEntries', [])
    print(f"multiAreaEntries count: {len(multi_area_entries)}")
    for i, entry in enumerate(multi_area_entries):
        print(f"Entry {i}: deliveryStart={entry.get('deliveryStart')}, entryPerArea keys={list(entry.get('entryPerArea', {}).keys())}, price={entry.get('entryPerArea', {}).get(area)}")

    print("Full multiAreaEntries for today:")
    import json
    print(json.dumps(multi_area_entries, indent=2))

    if not hourly_prices:
        print("No hourly prices found! Test failed.")
        return

    # Currency and unit conversion: EUR/MWh -> SEK/kWh
    exchange_service = ExchangeRateService()
    await exchange_service.get_rates(force_refresh=True)
    converted_prices = {}
    for ts, price in hourly_prices.items():
        # EUR -> SEK
        price_sek = await exchange_service.convert(price, parsed_data.get("currency", Currency.EUR), Currency.SEK)
        # MWh -> kWh
        price_sek_kwh = price_sek / 1000
        converted_prices[ts] = price_sek_kwh
    print(f"Converted hourly_prices to SEK/kWh ({len(converted_prices)}):", list(converted_prices.items())[:3], "...")

    # Check for 24 hours for today
    # Adjust today_hours logic to match any date with 2025-04-26 (CET or UTC)
    market_tz = pytz.timezone('Europe/Stockholm')
    now = datetime.now(market_tz)
    today_local = now.date()
    today_hours = [ts for ts in converted_prices if datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(market_tz).date() == today_local]
    print(f"Today's hours found: {len(today_hours)} (should be 24)")
    assert len(today_hours) == 24, f"Expected 24 hourly prices for today, got {len(today_hours)}"

    # Print a summary
    print("First 3 converted prices:")
    for ts in sorted(today_hours)[:3]:
        print(f"  {ts}: {converted_prices[ts]:.4f} SEK/kWh")
    print("Test passed: All steps from API fetch to final price conversion are working.")

    # Print all parsed hourly price keys and their UTC/CET dates
    print("All parsed hourly price keys and their UTC/CET dates:")
    for ts in sorted(hourly_prices.keys()):
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        print(f"  {ts} -> {dt.date()} (UTC)")

if __name__ == "__main__":
    import asyncio
    print("Starting Nordpool full-chain test...")
    try:
        asyncio.run(main())
    except Exception as e:
        import traceback
        print("Exception occurred:")
        traceback.print_exc()
