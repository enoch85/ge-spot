"""
Manual test for Nordpool API.

This script tests the full chain of the Nordpool API:
1. Connecting to the API
2. Fetching raw data
3. Parsing the data into a standardized format
4. Displaying the results

Usage:
    python -m tests.manual.api.nordpool_test [area_code]

Example:
    python -m tests.manual.api.nordpool_test SE3
"""

import asyncio
import os
import sys
from datetime import datetime
import logging
import aiohttp

# Add the project root to the path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
)

from custom_components.ge_spot.api.nordpool import NordpoolAPI
from custom_components.ge_spot.timezone.service import TimezoneService
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def main():
    # Get area code from command line or use default
    area_code = sys.argv[1] if len(sys.argv) > 1 else "SE3"

    logger.info(f"Testing Nordpool API for area: {area_code}")

    # Initialize timezone service
    timezone_service = TimezoneService(area=area_code)

    # Create separate sessions for API and exchange service
    api_session = aiohttp.ClientSession()
    exchange_session = aiohttp.ClientSession()

    try:
        # Initialize API with timezone service
        api = NordpoolAPI(timezone_service=timezone_service, session=api_session)

        # Initialize exchange service
        exchange_service = ExchangeRateService(session=exchange_session)

        # Test connection
        logger.info("Testing API connection...")

        # Fetch raw data
        logger.info("Fetching data from Nordpool API...")

        # Call the fetch_raw_data method with the area code
        raw_data_response = await api.fetch_raw_data(
            area_code
        )  # Renamed variable for clarity

        # Debug: Print raw data keys
        logger.info(
            f"Raw data keys: {list(raw_data_response.keys()) if raw_data_response else 'None'}"
        )

        if not raw_data_response or "raw_data" not in raw_data_response:
            logger.error("Failed to fetch valid raw data structure from Nordpool API")
            result = 1
        else:
            # Check for pre-processed interval data first
            interval_prices = raw_data_response.get("interval_raw", {})

            # If interval_raw is empty, try to extract from the nested raw_data
            if not interval_prices and "raw_data" in raw_data_response:
                logger.info(
                    "`interval_raw` not found or empty, attempting to parse from `raw_data` directly."
                )
                nested_raw_data = raw_data_response["raw_data"]
                temp_interval_prices = {}

                # Check if nested_raw_data is valid
                if nested_raw_data:
                    # Process today's data if available
                    if (
                        "today" in nested_raw_data
                        and nested_raw_data.get("today")
                        and "multiAreaEntries" in nested_raw_data["today"]
                    ):
                        logger.info("Extracting today's prices from nested raw_data.")
                        for entry in nested_raw_data["today"]["multiAreaEntries"]:
                            timestamp_utc = entry["deliveryStart"]
                            price = entry["entryPerArea"].get(area_code)
                            if price is not None:
                                # Store with timestamp as key, price as value (or dict if needed later)
                                temp_interval_prices[timestamp_utc] = {"price": price}

                    # Process tomorrow's data if available
                    tomorrow_data = nested_raw_data.get("tomorrow")
                    if tomorrow_data and "multiAreaEntries" in tomorrow_data:
                        logger.info(
                            "Extracting tomorrow's prices from nested raw_data."
                        )
                        for entry in tomorrow_data["multiAreaEntries"]:
                            timestamp_utc = entry["deliveryStart"]
                            price = entry["entryPerArea"].get(area_code)
                            if price is not None:
                                temp_interval_prices[timestamp_utc] = {"price": price}

                # Assign the extracted prices (even if empty)
                interval_prices = temp_interval_prices

            # Now check if we have any interval prices, either from interval_raw or extracted
            if not interval_prices:
                logger.error(
                    "Could not find or extract any interval prices from the Nordpool response."
                )
                # Optionally print more details about the raw_data_response here for debugging
                logger.info("\nRaw data sample (first 500 chars):")
                logger.info(str(raw_data_response)[:500] + "...")
                result = 1
            else:
                logger.info(
                    f"Successfully obtained {len(interval_prices)} interval price points for processing."
                )

                # --- Rest of the processing logic remains the same ---

                logger.info("Processing raw data...")

                # Convert prices from EUR to SEK
                logger.info("Converting prices from EUR to SEK...")
                await exchange_service.get_rates(force_refresh=True)

                # Format data for display
                formatted_prices = {}
                for timestamp_utc, price_data in interval_prices.items():
                    # Convert UTC timestamp to local time (Europe/Stockholm for SE areas)
                    # Ensure timestamp is parsed correctly, handling potential 'Z' for UTC
                    if timestamp_utc.endswith("Z"):
                        timestamp_utc = timestamp_utc[:-1] + "+00:00"

                    try:
                        # Use fromisoformat which handles timezone info
                        utc_dt = datetime.fromisoformat(timestamp_utc)
                    except ValueError:
                        logger.error(f"Could not parse timestamp: {timestamp_utc}")
                        continue  # Skip this entry if timestamp is invalid

                    local_dt = utc_dt.astimezone(timezone_service.area_timezone)
                    local_time_str = local_dt.strftime("%Y-%m-%d %H:%M")

                    # Handle price data being a dict or just a number
                    if isinstance(price_data, dict):
                        price_eur = price_data.get("price")  # Get price from dict
                    else:
                        price_eur = price_data  # Assume it's the price directly

                    if price_eur is None:
                        logger.warning(
                            f"Missing price for timestamp {timestamp_utc}, skipping."
                        )
                        continue

                    # Convert EUR/MWh to SEK/kWh
                    price_sek = await exchange_service.convert(price_eur, "EUR", "SEK")
                    price_sek_kwh = price_sek / 1000  # Convert from MWh to kWh

                    formatted_prices[local_time_str] = {
                        "price_eur_mwh": price_eur,
                        "price_sek_mwh": price_sek,
                        "price_sek_kwh": price_sek_kwh,
                        "price_ore_kwh": price_sek_kwh
                        * 100,  # Convert to öre/kWh (1 SEK = 100 öre)
                    }

                num_interval_prices = len(formatted_prices)
                if num_interval_prices == 0 and len(interval_prices) > 0:
                    logger.error("Extracted interval prices but failed to format them.")
                    result = 1
                elif num_interval_prices == 0:
                    logger.error("No interval prices could be formatted.")
                    result = 1  # Should have been caught earlier, but double-check
                else:
                    logger.info(
                        f"Successfully processed {num_interval_prices} interval prices."
                    )

                    # Group by date
                    prices_by_date = {}
                    for timestamp, price_info in formatted_prices.items():
                        date = timestamp.split(" ")[0]
                        if date not in prices_by_date:
                            prices_by_date[date] = {}
                        hour = timestamp.split(" ")[1]
                        prices_by_date[date][hour] = price_info

                    # Display results
                    logger.info("\nParsed Data:")
                    logger.info(f"Source: nordpool")
                    logger.info(f"Area: {area_code}")
                    logger.info(f"Currency: EUR (original), SEK (converted)")
                    logger.info(
                        f"API Timezone: {raw_data_response.get('timezone', 'Unknown')}"
                    )
                    logger.info(f"Local Timezone: {timezone_service.area_timezone}")

                    # Format interval prices into a table
                    logger.info("\nInterval Prices:")
                    logger.info(
                        f"{'Timestamp':<20} | {'EUR/MWh':<10} | {'SEK/kWh':<10} | {'öre/kWh':<10}"
                    )
                    logger.info("-" * 60)

                    # Format for display with date as header and hours below
                    for date in sorted(prices_by_date.keys()):
                        logger.info(f"\nDate: {date}")
                        for hour in sorted(prices_by_date[date].keys()):
                            price_info = prices_by_date[date][hour]
                            logger.info(
                                f"{hour:<20} | {price_info['price_eur_mwh']:<10.2f} | {price_info['price_sek_kwh']:<10.5f} | {price_info['price_ore_kwh']:<10.2f}"
                            )

                    logger.info("\nTest completed successfully")
                    result = 0

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        import traceback

        logger.error(traceback.format_exc())
        result = 1

    finally:
        # Close sessions
        await api_session.close()
        await exchange_session.close()

    return result


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
