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
from datetime import datetime, timezone, timedelta
import asyncio
import pytz
import logging
import json

# Add the root directory to the path so we can import the component modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from custom_components.ge_spot.api.energi_data import EnergiDataAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService
from custom_components.ge_spot.api.parsers.energi_data_parser import EnergiDataParser

# Danish price areas
DANISH_AREAS = ['DK1', 'DK2']

# Setup basic logging
logging.basicConfig(level=logging.DEBUG)
_LOGGER = logging.getLogger(__name__)

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test Energi Data Service API integration')
    parser.add_argument('area', nargs='?', default='DK1',
                        choices=DANISH_AREAS,
                        help='Area code (DK1, DK2)')
    args = parser.parse_args()
    area = args.area

    print(f"\n===== Energi Data Service API Full Chain Test for {area} =====\n")

    # Initialize the API client
    api = EnergiDataAPI()

    try:
        # Step 1: Fetch raw data
        _LOGGER.info(f"Fetching Energi Data Service data for area: {area}")
        raw_data_wrapper = await api.fetch_raw_data(area=area)
        _LOGGER.debug(f"[EnergiDataService RAW DATA - {area}] Full raw_data object: {json.dumps(raw_data_wrapper, indent=2)}")

        if not raw_data_wrapper or not raw_data_wrapper.get("raw_data"):
            _LOGGER.error("Error: Failed to fetch raw data or raw_data key is missing/empty.")
            print("Error: Failed to fetch data from Energi Data Service API")
            return 1

        # Extract the actual API responses for today and tomorrow
        api_response_today = raw_data_wrapper.get("raw_data", {}).get("today")
        api_response_tomorrow = raw_data_wrapper.get("raw_data", {}).get("tomorrow")

        if not api_response_today:
            _LOGGER.warning("Warning: No raw data found for today.")

        # Print a sample of the raw data
        print(f"Raw data wrapper type: {type(raw_data_wrapper)}")
        if api_response_today:
            print(f"Today's raw data sample (truncated): {str(api_response_today)[:300]}...")
            if isinstance(api_response_today, dict) and 'records' in api_response_today:
                print(f"Number of records today: {len(api_response_today['records'])}")
                if api_response_today['records']:
                    print(f"First record sample today: {api_response_today['records'][0]}")
        if api_response_tomorrow:
            print(f"Tomorrow's raw data sample (truncated): {str(api_response_tomorrow)[:300]}...")
            if isinstance(api_response_tomorrow, dict) and 'records' in api_response_tomorrow:
                print(f"Number of records tomorrow: {len(api_response_tomorrow['records'])}")

        # Step 2: Parse raw data using the specific parser
        print("\nParsing raw data...")
        parser = EnergiDataParser()

        # Combine records from today and tomorrow if available
        all_records = []
        if api_response_today and isinstance(api_response_today.get("records"), list):
            all_records.extend(api_response_today["records"])
        if api_response_tomorrow and isinstance(api_response_tomorrow.get("records"), list):
            all_records.extend(api_response_tomorrow["records"])

        if not all_records:
            _LOGGER.error("Error: No records found in today's or tomorrow's data to parse.")
            return 1

        data_to_parse = {"records": all_records}
        parsed_data = parser.parse(data_to_parse)

        # Add metadata back from the wrapper if needed
        parsed_data["area"] = raw_data_wrapper.get("area", area)
        parsed_data["source"] = raw_data_wrapper.get("source", Source.ENERGI_DATA_SERVICE)
        parsed_data["currency"] = raw_data_wrapper.get("currency", Currency.DKK)
        parsed_data["timezone"] = raw_data_wrapper.get("timezone", "Europe/Copenhagen")

        print(f"Parsed data keys: {list(parsed_data.keys())}")
        interval_raw_prices = parsed_data.get("interval_raw", {})  # Changed from hourly_raw
        if not interval_raw_prices:
            print("Warning: No interval prices (interval_raw) found in the parsed data")
            print(f"Available keys: {list(parsed_data.keys())}")
            return 1

        print(f"Found {len(interval_raw_prices)} interval prices (raw)")

        # Step 3: Currency conversion (DKK -> EUR)
        print("\nConverting prices from DKK to EUR...")
        exchange_service = ExchangeRateService()
        await exchange_service.get_rates(force_refresh=True)

        converted_prices = {}
        for ts, price in interval_raw_prices.items():  # Changed from hourly_raw_prices
            price_eur = await exchange_service.convert(
                price,
                parsed_data.get("currency", Currency.DKK),
                Currency.EUR
            )
            price_eur_kwh = price_eur / 1000
            converted_prices[ts] = price_eur_kwh

        # Step 4: Display results
        print("\nPrice Information:")
        print(f"Original Currency: {parsed_data.get('currency', Currency.DKK)}/MWh")
        print(f"Converted Currency: {Currency.EUR}/kWh")

        dk_tz = pytz.timezone(parsed_data.get('timezone', 'Europe/Copenhagen'))
        prices_by_date = {}

        for ts, price in interval_raw_prices.items():  # Changed from hourly_raw_prices
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(dk_tz)
            date_str = dt.strftime('%Y-%m-%d')
            hour_str = dt.strftime('%H:%M')

            if date_str not in prices_by_date:
                prices_by_date[date_str] = {}

            prices_by_date[date_str][hour_str] = {
                'original': price,
                'converted': converted_prices.get(ts)
            }

        for date, hours in sorted(prices_by_date.items()):
            print(f"\nPrices for {date}:")
            print(f"{'Time':<10} {'DKK/MWh':<15} {'EUR/kWh':<15}")
            print("-" * 40)

            for hour, prices in sorted(hours.items()):
                print(f"{hour:<10} {prices['original']:<15.4f} {prices['converted']:<15.6f}")

        today = datetime.now(dk_tz).strftime('%Y-%m-%d')
        if today in prices_by_date:
            today_prices = prices_by_date[today]
            print(f"\nFound {len(today_prices)} price points for today ({today})")

            if len(today_prices) == 24:
                print("✓ Complete set of 24 hourly prices for today")
            else:
                print(f"⚠ Incomplete data: Found {len(today_prices)} hourly prices for today (expected 24)")

                all_hours = set(f"{h:02d}:00" for h in range(24))
                found_hours = set(today_prices.keys())
                missing_hours = all_hours - found_hours
                if missing_hours:
                    print(f"Missing hours: {', '.join(sorted(missing_hours))}")
        else:
            print(f"\nWarning: No prices found for today ({today})")

        if today in prices_by_date:
            prices = [details['original'] for _, details in prices_by_date[today].items()]
            if prices:
                price_variation = max(prices) - min(prices)
                print(f"\nPrice variation today: {price_variation:.2f} DKK/MWh")
                if price_variation > 0:
                    print("✓ Price variation detected (expected for real market data)")
                else:
                    print("⚠ No price variation detected - suspicious for real market data")

        print("\nTest completed successfully!")

    except Exception as e:
        _LOGGER.error(f"Error during test: {e}", exc_info=True)
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    print("Starting Energi Data Service API full chain test...")
    sys.exit(asyncio.run(main()))
