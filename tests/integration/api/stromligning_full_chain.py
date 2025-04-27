#!/usr/bin/env python3
"""
Manual full chain test for Strømlikning API (Norway).

This script performs an end-to-end test of the Strømlikning API integration:
1. Fetches real data from the Strømlikning API
2. Parses the raw data
3. Applies currency conversion
4. Validates and displays the results

Usage:
    python stromligning_full_chain.py [area]
    
    area: Optional area code (NO1, NO2, NO3, NO4, NO5)
          Defaults to NO1 if not provided
"""

import sys
import os
import argparse
from datetime import datetime, timezone, timedelta
import asyncio
import pytz

# Add the root directory to the path so we can import the component modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from custom_components.ge_spot.api.stromligning import StromligninkAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService

# Norwegian price areas
NORWEGIAN_AREAS = ['NO1', 'NO2', 'NO3', 'NO4', 'NO5']

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test Strømlikning API integration')
    parser.add_argument('area', nargs='?', default='NO1', 
                        choices=NORWEGIAN_AREAS,
                        help='Area code (NO1, NO2, NO3, NO4, NO5)')
    args = parser.parse_args()
    
    area = args.area
    
    print(f"\n===== Strømlikning API Full Chain Test for {area} =====\n")
    
    # Initialize the API client
    api = StromligninkAPI()
    
    try:
        # Step 1: Fetch raw data
        print(f"Fetching Strømlikning data for area: {area}")
        raw_data = await api.fetch_raw_data(area=area)
        
        if not raw_data:
            print("Error: Failed to fetch data from Strømlikning API")
            return
            
        # Print a sample of the raw data (truncated for readability)
        if isinstance(raw_data, list):
            print(f"Received {len(raw_data)} data points")
            if raw_data:
                print(f"First data point sample: {raw_data[0]}")
        else:
            print(f"Raw data type: {type(raw_data)}")
            raw_data_str = str(raw_data)
            print(f"Raw data sample (truncated): {raw_data_str[:300]}...")
        
        # Step 2: Parse raw data
        print("\nParsing raw data...")
        parsed_data = await api.parse_raw_data(raw_data)
        
        print(f"Parsed data keys: {list(parsed_data.keys())}")
        print(f"Source: {parsed_data.get('source')}")
        print(f"Area: {parsed_data.get('area')}")
        print(f"Currency: {parsed_data.get('currency')}")
        print(f"API Timezone: {parsed_data.get('api_timezone')}")
        
        # Check if hourly prices are available
        hourly_prices = parsed_data.get("hourly_prices", {})
        if not hourly_prices:
            print("Warning: No hourly prices found in the parsed data")
            return
            
        print(f"Found {len(hourly_prices)} hourly prices")
        
        # Step 3: Currency conversion (NOK -> EUR)
        print(f"\nConverting prices from {parsed_data.get('currency', Currency.NOK)} to {Currency.EUR}...")
        exchange_service = ExchangeRateService()
        await exchange_service.get_rates(force_refresh=True)
        
        # Convert prices from NOK to EUR and from MWh to kWh
        converted_prices = {}
        for ts, price in hourly_prices.items():
            # Convert from NOK to EUR
            price_eur = await exchange_service.convert(
                price, 
                parsed_data.get("currency", Currency.NOK), 
                Currency.EUR
            )
            # Convert from MWh to kWh
            price_eur_kwh = price_eur / 1000
            converted_prices[ts] = price_eur_kwh
        
        # Step 4: Display results
        print("\nPrice Information:")
        print(f"Original Currency: {parsed_data.get('currency', Currency.NOK)}/MWh")
        print(f"Converted Currency: {Currency.EUR}/kWh")
        
        # Group prices by date
        no_tz = pytz.timezone('Europe/Oslo')
        prices_by_date = {}
        
        for ts, price in hourly_prices.items():
            # Parse the timestamp and convert to local timezone
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(no_tz)
            date_str = dt.strftime('%Y-%m-%d')
            hour_str = dt.strftime('%H:%M')
            
            if date_str not in prices_by_date:
                prices_by_date[date_str] = {}
                
            prices_by_date[date_str][hour_str] = {
                'original': price,
                'converted': converted_prices.get(ts)
            }
        
        # Print prices grouped by date
        for date, hours in sorted(prices_by_date.items()):
            print(f"\nPrices for {date}:")
            print(f"{'Time':<10} {f'{parsed_data.get(\"currency\", Currency.NOK)}/MWh':<15} {f'{Currency.EUR}/kWh':<15}")
            print("-" * 40)
            
            for hour, prices in sorted(hours.items()):
                print(f"{hour:<10} {prices['original']:<15.4f} {prices['converted']:<15.6f}")
        
        # Validate that we have data for today and tomorrow
        today = datetime.now(no_tz).strftime('%Y-%m-%d')
        tomorrow = (datetime.now(no_tz) + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Check today's data
        if today in prices_by_date:
            today_prices = prices_by_date[today]
            print(f"\nFound {len(today_prices)} price points for today ({today})")
            
            if len(today_prices) == 24:
                print("✓ Complete set of 24 hourly prices for today")
            else:
                print(f"⚠ Incomplete data: Found {len(today_prices)} hourly prices for today (expected 24)")
        else:
            print(f"\nWarning: No prices found for today ({today})")
        
        # Check tomorrow's data
        if tomorrow in prices_by_date:
            tomorrow_prices = prices_by_date[tomorrow]
            print(f"\nFound {len(tomorrow_prices)} price points for tomorrow ({tomorrow})")
            
            if len(tomorrow_prices) == 24:
                print("✓ Complete set of 24 hourly prices for tomorrow")
            else:
                print(f"⚠ Incomplete data: Found {len(tomorrow_prices)} hourly prices for tomorrow (expected 24)")
        else:
            print(f"\nWarning: No prices found for tomorrow ({tomorrow})")
        
        print("\nTest completed successfully!")
        
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Starting Strømlikning API full chain test...")
    asyncio.run(main())