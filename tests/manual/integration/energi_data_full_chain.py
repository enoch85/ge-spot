#!/usr/bin/env python3
"""
Manual full chain test for Energi Data Service API (Denmark).

This script performs an end-to-end test of the Energi Data Service API integration:
1. Fetches real data from the Energi Data Service API
2. Parses the raw data
3. Applies currency conversion
4. Validates and displays the results

Usage:
    python energi_data_full_chain.py [area]

    area: Optional area code (DK1, DK2)
          Defaults to DK1 if not provided
"""

import sys
import os
import argparse
from datetime import datetime
import asyncio
import pytz
import logging
import json
import warnings

# Suppress aiohttp ResourceWarning for unclosed sessions in tests
# These warnings appear during event loop cleanup and don't indicate real problems
warnings.filterwarnings("ignore", message="unclosed", category=ResourceWarning)

# Add the root directory to the path so we can import the component modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from custom_components.ge_spot.api.energi_data import EnergiDataAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService
from custom_components.ge_spot.api.parsers.energi_data_parser import EnergiDataParser

# Danish price areas
DANISH_AREAS = ["DK1", "DK2"]

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
_LOGGER = logging.getLogger(__name__)

# Suppress asyncio warnings about unclosed sessions during cleanup
# These are harmless in test context where the event loop is shutting down
logging.getLogger("asyncio").setLevel(logging.CRITICAL)


async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Test Energi Data Service API integration"
    )
    parser.add_argument(
        "area",
        nargs="?",
        default="DK1",
        choices=DANISH_AREAS,
        help="Area code (DK1, DK2)",
    )
    args = parser.parse_args()
    area = args.area

    print(f"\n===== Energi Data Service API Full Chain Test for {area} =====\n")

    # Initialize the API client
    api = EnergiDataAPI()

    try:
        # Step 1: Fetch raw data
        _LOGGER.info(f"Fetching Energi Data Service data for area: {area}")
        raw_data_wrapper = await api.fetch_raw_data(area=area)
        _LOGGER.debug(
            f"[EnergiDataService RAW DATA - {area}] Full raw_data object: {json.dumps(raw_data_wrapper, default=str, indent=2)}"
        )

        if not raw_data_wrapper:
            _LOGGER.error("Error: Failed to fetch data from Energi Data Service API")
            print("Error: Failed to fetch data from Energi Data Service API")
            return 1

        # Step 2: Parse the raw data
        _LOGGER.info(f"Parsing Energi Data Service data...")
        parser = api.get_parser_for_area(area)
        parsed_data = parser.parse(raw_data_wrapper)

        if not parsed_data:
            _LOGGER.error("Error: Failed to parse data")
            print("Error: Failed to parse data")
            return 1

        # Check if we have interval_raw (the processed prices)
        if "interval_raw" not in parsed_data:
            _LOGGER.error("Error: interval_raw key is missing from parsed data.")
            print("Error: No interval prices in parsed data")
            return 1

        interval_raw_prices = parsed_data.get("interval_raw", {})

        # Extract the actual API responses for today and tomorrow if available in nested structure
        nested_raw = raw_data_wrapper.get("raw_data", {})
        api_response_today = (
            nested_raw.get("today") if isinstance(nested_raw, dict) else None
        )
        api_response_tomorrow = (
            nested_raw.get("tomorrow") if isinstance(nested_raw, dict) else None
        )

        if api_response_today:
            print(
                f"Today's raw data sample (truncated): {str(api_response_today)[:300]}..."
            )
            if isinstance(api_response_today, dict) and "records" in api_response_today:
                print(
                    f"Number of hourly records today: {len(api_response_today['records'])}"
                )
                if api_response_today["records"]:
                    print(
                        f"First record sample today: {api_response_today['records'][0]}"
                    )
        if api_response_tomorrow:
            print(
                f"Tomorrow's raw data sample (truncated): {str(api_response_tomorrow)[:300]}..."
            )
            if (
                isinstance(api_response_tomorrow, dict)
                and "records" in api_response_tomorrow
            ):
                print(
                    f"Number of hourly records tomorrow: {len(api_response_tomorrow['records'])}"
                )

        # Print info about the expanded interval data
        print(f"\nExpanded interval prices: {len(interval_raw_prices)} intervals")
        print(f"Currency: {raw_data_wrapper.get('currency', Currency.DKK)}")
        print(f"Timezone: {raw_data_wrapper.get('timezone', 'Europe/Copenhagen')}")

        if not interval_raw_prices:
            _LOGGER.error("Error: No interval prices found in the response.")
            return 1

        # Step 2: The data is already parsed and expanded - use it directly
        print("\nUsing already-parsed interval data...")

        parsed_data = {
            "interval_raw": interval_raw_prices,
            "area": raw_data_wrapper.get("area", area),
            "source": raw_data_wrapper.get("source", Source.ENERGI_DATA_SERVICE),
            "currency": raw_data_wrapper.get("currency", Currency.DKK),
            "timezone": raw_data_wrapper.get("timezone", "Europe/Copenhagen"),
        }

        print(
            f"Found {len(interval_raw_prices)} interval prices (already expanded from hourly)"
        )

        # Step 3: Currency conversion (DKK -> EUR)
        print("\nConverting prices from DKK to EUR...")
        exchange_service = ExchangeRateService()
        await exchange_service.get_rates(force_refresh=True)

        converted_prices = {}
        for ts, price in interval_raw_prices.items():  # Changed from hourly_raw_prices
            price_eur = await exchange_service.convert(
                price, parsed_data.get("currency", Currency.DKK), Currency.EUR
            )
            price_eur_kwh = price_eur / 1000
            converted_prices[ts] = price_eur_kwh

        # Step 4: Display results
        print("\nPrice Information:")
        print(f"Original Currency: {parsed_data.get('currency', Currency.DKK)}/MWh")
        print(f"Converted Currency: {Currency.EUR}/kWh")

        dk_tz = pytz.timezone(parsed_data.get("timezone", "Europe/Copenhagen"))
        prices_by_date = {}

        for ts, price in interval_raw_prices.items():  # Changed from hourly_raw_prices
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(dk_tz)
            date_str = dt.strftime("%Y-%m-%d")
            hour_str = dt.strftime("%H:%M")

            if date_str not in prices_by_date:
                prices_by_date[date_str] = {}

            prices_by_date[date_str][hour_str] = {
                "original": price,
                "converted": converted_prices.get(ts),
            }

        for date, hours in sorted(prices_by_date.items()):
            print(f"\nPrices for {date}:")
            print(f"{'Time':<10} {'DKK/MWh':<15} {'EUR/kWh':<15}")
            print("-" * 40)

            for hour, prices in sorted(hours.items()):
                print(
                    f"{hour:<10} {prices['original']:<15.4f} {prices['converted']:<15.6f}"
                )

        today = datetime.now(dk_tz).strftime("%Y-%m-%d")
        if today in prices_by_date:
            today_prices = prices_by_date[today]
            print(f"\nFound {len(today_prices)} price points for today ({today})")

            # Native 15-minute intervals: expect 96 per day (4 per hour × 24 hours)
            expected_intervals = 96
            if len(today_prices) == expected_intervals:
                print(
                    f"✓ Complete set of {expected_intervals} 15-minute intervals for today"
                )
            elif len(today_prices) >= expected_intervals * 0.9:
                print(
                    f"✓ Nearly complete data: Found {len(today_prices)} 15-minute intervals (expected {expected_intervals})"
                )
            else:
                print(
                    f"⚠ Incomplete data: Found {len(today_prices)} 15-minute intervals for today (expected {expected_intervals})"
                )

                # Show first few missing intervals if any
                all_intervals = set(
                    f"{h:02d}:{m:02d}" for h in range(24) for m in [0, 15, 30, 45]
                )
                found_intervals = set(today_prices.keys())
                missing_intervals = all_intervals - found_intervals
                if missing_intervals:
                    missing_list = sorted(missing_intervals)[:10]  # Show first 10
                    more = (
                        f" (and {len(missing_intervals) - 10} more)"
                        if len(missing_intervals) > 10
                        else ""
                    )
                    print(f"Missing intervals: {', '.join(missing_list)}{more}")
        else:
            print(f"\nWarning: No prices found for today ({today})")

        if today in prices_by_date:
            prices = [
                details["original"] for _, details in prices_by_date[today].items()
            ]
            if prices:
                price_variation = max(prices) - min(prices)
                print(f"\nPrice variation today: {price_variation:.2f} DKK/MWh")
                if price_variation > 0:
                    print("✓ Price variation detected (expected for real market data)")
                else:
                    print(
                        "⚠ No price variation detected - suspicious for real market data"
                    )

        print("\nTest completed successfully!")

    except Exception as e:
        _LOGGER.error(f"Error during test: {e}", exc_info=True)
        print(f"Error during test: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        # Add a delay to allow any pending async operations to complete
        # This helps avoid "Unclosed client session" warnings from aiohttp
        await asyncio.sleep(0.5)

    return 0


if __name__ == "__main__":
    print("Starting Energi Data Service API full chain test...")
    sys.exit(asyncio.run(main()))
