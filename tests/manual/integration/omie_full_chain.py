#!/usr/bin/env python3
"""
Manual full chain test for OMIE API (Spain/Portugal).

This script performs an end-to-end test of the OMIE API integration:
1. Fetches real data from the OMIE API
2. Parses the raw data
3. Applies currency conversion
4. Validates and displays the results

Usage:
    python omie_full_chain.py [area]
    
    area: Optional area code (ES, PT)
          Defaults to ES if not provided
"""

import sys
import os
import argparse
from datetime import datetime, timezone, timedelta
import asyncio
import pytz

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from custom_components.ge_spot.api.omie import OmieAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test OMIE API integration')
    parser.add_argument('area', nargs='?', default='ES', 
                        choices=['ES', 'PT'],
                        help='Area code (ES, PT)')
    args = parser.parse_args()
    
    area = args.area
    
    print(f"\n===== OMIE API Full Chain Test for {area} =====\n")
    
    # Initialize the API client
    api = OmieAPI()
    
    try:
        # Step 1: Fetch raw data
        print(f"Fetching OMIE data for area: {area}")
        raw_data = await api.fetch_raw_data(area=area)
        
        if not raw_data:
            print("Error: Failed to fetch data from OMIE API")
            return
            
        # Print a sample of the raw data (truncated for readability)
        if "raw_csv_by_date" in raw_data and isinstance(raw_data["raw_csv_by_date"], dict):
            print(f"Received data for {len(raw_data['raw_csv_by_date'])} date(s)")
            if raw_data["raw_csv_by_date"]:
                # Display first date and sample of the CSV content
                first_date = next(iter(raw_data["raw_csv_by_date"]))
                csv_sample = raw_data["raw_csv_by_date"][first_date][:300] + "..." if len(raw_data["raw_csv_by_date"][first_date]) > 300 else raw_data["raw_csv_by_date"][first_date]
                print(f"Data sample for {first_date}:\n{csv_sample}")
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
        
        # Step 3: Currency conversion (EUR -> GBP)
        target_currency = Currency.GBP
        print(f"\nConverting prices from {parsed_data.get('currency', Currency.EUR)} to {target_currency}...")
        exchange_service = ExchangeRateService()
        await exchange_service.get_rates(force_refresh=True)
        
        # Convert prices from EUR to GBP and from MWh to kWh
        converted_prices = {}
        for ts, price in hourly_prices.items():
            # Convert from EUR to GBP
            price_gbp = await exchange_service.convert(
                price, 
                parsed_data.get("currency", Currency.EUR), 
                target_currency
            )
            # Convert from MWh to kWh
            price_gbp_kwh = price_gbp / 1000
            converted_prices[ts] = price_gbp_kwh
        
        # Step 4: Display results
        print("\nPrice Information:")
        print(f"Original Currency: {parsed_data.get('currency', Currency.EUR)}/MWh")
        print(f"Converted Currency: {target_currency}/kWh")
        
        # Group prices by date
        local_tz_name = 'Europe/Madrid' if area == 'ES' else 'Europe/Lisbon'
        local_tz = pytz.timezone(local_tz_name)
        prices_by_date = {}
        
        for ts, price in hourly_prices.items():
            try:
                # Handle timestamps with and without timezone information
                if 'Z' in ts or '+' in ts:
                    # Parse the timestamp with timezone info
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(local_tz)
                else:
                    # For local timestamps, assume they're in the local timezone
                    dt = pytz.timezone('UTC').localize(datetime.fromisoformat(ts)).astimezone(local_tz)
                
                date_str = dt.strftime('%Y-%m-%d')
                hour_str = dt.strftime('%H:%M')
                
                if date_str not in prices_by_date:
                    prices_by_date[date_str] = {}
                    
                prices_by_date[date_str][hour_str] = {
                    'original': price,
                    'converted': converted_prices.get(ts)
                }
            except (ValueError, TypeError) as e:
                print(f"Warning: Could not parse timestamp {ts}: {e}")
        
        # Print prices grouped by date
        for date, hours in sorted(prices_by_date.items()):
            print(f"\nPrices for {date}:")
            print(f"{'Time':<10} {parsed_data.get('currency', Currency.EUR)}/MWh{'':<5} {target_currency}/kWh{'':<5}")
            print("-" * 40)
            
            for hour, prices in sorted(hours.items()):
                print(f"{hour:<10} {prices['original']:<15.4f} {prices['converted']:<15.6f}")
        
        # Validate that we have data for today and tomorrow
        today = datetime.now(local_tz).strftime('%Y-%m-%d')
        tomorrow = (datetime.now(local_tz) + timedelta(days=1)).strftime('%Y-%m-%d')
        
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
    finally:
        # Ensure the session is closed
        if hasattr(api, 'session') and api.session:
            await api.session.close()

if __name__ == "__main__":
    print("Starting OMIE API full chain test...")
    asyncio.run(main())