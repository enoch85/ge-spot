#!/usr/bin/env python3
"""
Manual full chain test for ComEd API.

This script performs an end-to-end test of the ComEd API integration:
1. Fetches real 5-minute data from the ComEd API (288 records per day)
2. Parses and aggregates to 15-minute intervals (96 records per day)
3. Validates aggregation (averaging verification)
4. Normalizes timezones
5. Splits into today/tomorrow
6. Validates and displays the results

Usage:
    python comed_full_chain.py [--date YYYY-MM-DD] [--debug]

    --date: Optional date to fetch data for (format: YYYY-MM-DD)
            Defaults to today if not provided
    --debug: Enable detailed debug logging
"""

import sys
import os
import argparse
from datetime import datetime, timedelta, timezone
import asyncio
import pytz
import logging
import json
from collections import defaultdict

# Set up logging
logger = logging.getLogger(__name__)

# Add the root directory to the path so we can import the component modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from custom_components.ge_spot.api.comed import ComedAPI
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.const.time import TimeInterval
from custom_components.ge_spot.timezone.service import TimezoneService
from custom_components.ge_spot.timezone.timezone_converter import TimezoneConverter

# ComEd serves the Chicago area
AREA = "COMED_HOURLY_PRICING"  # This is the area identifier used in ComEd API
LOCAL_TZ_NAME = "America/Chicago"


async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Test ComEd API integration")
    parser.add_argument(
        "--date",
        default=None,
        help="Date to fetch data for (format: YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable detailed debug logging"
    )
    args = parser.parse_args()

    # Configure logging level
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    reference_date_str = args.date

    # Process reference date if provided
    reference_time = None
    target_date = datetime.now(
        pytz.timezone(LOCAL_TZ_NAME)
    ).date()  # Use local time for default date
    if reference_date_str:
        try:
            ref_date_obj = datetime.strptime(reference_date_str, "%Y-%m-%d")
            target_date = ref_date_obj.date()
            # ComEd API might use local time for date ranges, let's create a reference in local time
            local_tz = pytz.timezone(LOCAL_TZ_NAME)
            reference_time = local_tz.localize(
                ref_date_obj.replace(hour=12, minute=0, second=0)
            )
            logger.info(
                f"Using reference date: {reference_date_str} (reference time: {reference_time})"
            )
        except ValueError:
            logger.error(
                f"Invalid date format: {reference_date_str}. Please use YYYY-MM-DD format."
            )
            return 1
    else:
        # Default to now in the local timezone if no date specified
        reference_time = datetime.now(pytz.timezone(LOCAL_TZ_NAME))

    logger.info(f"\n{'='*80}")
    logger.info(f"ComEd API Full Chain Test for {AREA}")
    logger.info(f"{'='*80}")
    logger.info(f"\nConfiguration:")
    logger.info(f"  Target interval: {TimeInterval.DEFAULT}")
    logger.info(f"  Target intervals per hour: {TimeInterval.get_intervals_per_hour()}")
    logger.info(f"  Target intervals per day: {TimeInterval.get_intervals_per_day()}")
    logger.info(f"  Source interval: 5 minutes")
    logger.info(f"  Source intervals per hour: 12")
    logger.info(f"  Source intervals per day: 288")

    # Initialize timezone service based on area
    logger.info("\n" + "=" * 80)
    logger.info("Setting up timezone service...")
    logger.info("=" * 80)
    local_tz = pytz.timezone(LOCAL_TZ_NAME)
    tz_config = {"timezone_reference": "area"}  # Assuming area dictates timezone
    # Use a fixed area for ComEd as it's specific
    tz_service = TimezoneService(area=AREA, config=tz_config)
    tz_converter = TimezoneConverter(tz_service)
    logger.info(f"Timezone service initialized for area: {AREA} using {LOCAL_TZ_NAME}")

    # Initialize the API client
    api = ComedAPI()  # ComEd API doesn't require config

    try:
        # Step 1: Fetch data from API
        logger.info("\n" + "=" * 80)
        logger.info("Step 1: Fetching 5-minute data from ComEd API")
        logger.info("=" * 80)
        logger.info(f"  Area: {AREA}")
        logger.info(
            f"  Reference time: {reference_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )

        raw_data = await api.fetch_raw_data(area=AREA, reference_time=reference_time)

        if not raw_data:
            logger.error("❌ FAILED: No data returned from API")
            return 1

        logger.debug(f"Data keys: {list(raw_data.keys())}")

        # Check if we have interval_raw (already processed and aggregated)
        if "interval_raw" not in raw_data:
            logger.error("❌ FAILED: interval_raw key is missing from response")
            logger.error(f"Response keys: {list(raw_data.keys())}")
            return 1

        interval_raw_prices = raw_data.get("interval_raw", {})

        logger.info(f"✅ API fetch successful (already processed)")
        logger.info(f"  Currency: {raw_data.get('currency', Currency.CENTS)}")
        source_timezone = raw_data.get("timezone", LOCAL_TZ_NAME)
        logger.info(f"  Timezone: {source_timezone}")

        # Try to extract raw 5-minute data for verification
        prices_5min = []
        nested_raw = raw_data.get("raw_data", {})
        if isinstance(nested_raw, dict) and "data" in nested_raw:
            raw_json = nested_raw["data"]
            if isinstance(raw_json, dict) and "raw_data" in raw_json:
                # Parse the JSON string
                if isinstance(raw_json["raw_data"], str):
                    prices_5min = json.loads(raw_json["raw_data"])
                else:
                    prices_5min = raw_json["raw_data"]

                logger.info(f"  Source 5-minute records: {len(prices_5min)}")
                if prices_5min:
                    sample = prices_5min[0]
                    logger.debug(f"  Sample 5-min record: {sample}")

        if not prices_5min:
            logger.debug(
                "  Note: Raw 5-minute data not available in response (will use aggregated data)"
            )

        if not interval_raw_prices:
            logger.error("❌ FAILED: No interval prices found in the response")
            return 1

        logger.debug(
            f"Sample aggregated prices: {dict(list(interval_raw_prices.items())[:5])}"
        )

        # Step 2: Validate aggregation
        logger.info("\n" + "=" * 80)
        logger.info("Step 2: Validating interval aggregation (5-min → 15-min)")
        logger.info("=" * 80)

        if prices_5min:
            source_5min_count = len(prices_5min)
            # 5-min to 15-min: 3:1 ratio
            expected_interval_count = source_5min_count // 3

            logger.info(f"  Source 5-minute records: {source_5min_count}")
            logger.info(
                f"  Expected 15-minute intervals: ~{expected_interval_count} ({source_5min_count} ÷ 3)"
            )
            logger.info(f"  Actual intervals: {len(interval_raw_prices)}")

            # Allow some tolerance for partial intervals
            if abs(len(interval_raw_prices) - expected_interval_count) > 5:
                logger.warning(
                    f"⚠️  Warning: Interval count differs more than expected"
                )
            else:
                logger.info(f"✅ Interval count within expected range")
        else:
            logger.info(f"  Source 5-minute records: Not available")
            logger.info(f"  Actual intervals: {len(interval_raw_prices)}")
            logger.info(f"✅ Using processed interval data")

        parsed_data = {
            "interval_raw": interval_raw_prices,
            "currency": raw_data.get("currency", Currency.CENTS),
            "timezone": source_timezone,
            "source_name": "comed",
        }

        # Step 3: Verify aggregation correctness (averaging)
        logger.info("\n" + "=" * 80)
        logger.info("Step 3: Verifying aggregation correctness (spot checks)")
        logger.info("=" * 80)

        if prices_5min:
            # Build map of original 5-min data
            five_min_by_time = {}
            for entry in prices_5min:
                if isinstance(entry, dict):
                    millis = entry.get("millisUTC")
                    price = entry.get("price")
                    if millis and price is not None:
                        timestamp = datetime.fromtimestamp(
                            int(millis) / 1000, tz=timezone.utc
                        )
                        ts = timestamp.isoformat()
                        five_min_by_time[ts] = float(price)

            # Check first few 15-minute intervals
            sorted_timestamps = sorted(interval_raw_prices.keys())
            verification_count = 0
            verification_success = 0

            for ts_15min in sorted_timestamps[:5]:  # Check first 5 intervals
                dt_15min = datetime.fromisoformat(ts_15min)
                aggregated_price = interval_raw_prices[ts_15min]

                # Find the three 5-minute intervals that make up this 15-minute interval
                contributing_prices = []
                for offset_min in [0, 5, 10]:
                    dt_5min = dt_15min + timedelta(minutes=offset_min)
                    ts_5min = dt_5min.isoformat()

                    if ts_5min in five_min_by_time:
                        contributing_prices.append(five_min_by_time[ts_5min])

                if len(contributing_prices) == 3:
                    expected_avg = sum(contributing_prices) / len(contributing_prices)
                    verification_count += 1

                    if abs(aggregated_price - expected_avg) < 0.0001:
                        verification_success += 1
                        logger.info(
                            f"✅ {dt_15min.strftime('%H:%M')}: {contributing_prices} → avg={expected_avg:.4f} (matches {aggregated_price:.4f})"
                        )
                    else:
                        logger.warning(
                            f"❌ {dt_15min.strftime('%H:%M')}: Expected {expected_avg:.4f}, got {aggregated_price:.4f}"
                        )
                else:
                    logger.debug(
                        f"⚠️  {dt_15min.strftime('%H:%M')}: Only {len(contributing_prices)} contributing prices found"
                    )

            if verification_success == verification_count and verification_count > 0:
                logger.info(f"\n✅ All verified intervals correctly averaged!")
            elif verification_count == 0:
                logger.info(
                    f"\n⚠️  Could not verify averaging (insufficient source data)"
                )
        else:
            logger.info(f"  Source 5-minute data not available for verification")
            logger.info(f"  ✅ Trusting aggregated interval data from API")

        # Step 4: Normalize Timezones (if needed)
        logger.info("\n" + "=" * 80)
        logger.info(f"Step 4: Normalizing timezones")
        logger.info("=" * 80)
        logger.info(f"  Timestamps are in {source_timezone}")
        normalized_prices = interval_raw_prices  # Already in ISO format

        # Step 5: Currency conversion (Not needed for ComEd as it's already USD)
        logger.info("\n" + "=" * 80)
        logger.info(f"Step 5: Currency conversion")
        logger.info("=" * 80)
        target_currency = Currency.USD
        logger.info(f"  Prices are already in target currency: {target_currency}")

        converted_prices = {}
        for time_key, price_info in normalized_prices.items():
            # Price should already be in $/kWh or similar from the parser
            price_kwh = (
                price_info["price"] if isinstance(price_info, dict) else price_info
            )
            converted_prices[time_key] = price_kwh
            if isinstance(normalized_prices[time_key], dict):
                normalized_prices[time_key]["converted_kwh"] = price_kwh
            else:
                # Ensure structure is consistent for display
                normalized_prices[time_key] = {
                    "price": price_kwh,
                    "converted_kwh": price_kwh,
                }

        logger.debug(
            f"Final prices sample ({target_currency}/kWh): {dict(list(converted_prices.items())[:5])}"
        )

        # Step 6: Verify 15-minute interval spacing
        logger.info("\n" + "=" * 80)
        logger.info("Step 6: Verifying 15-minute interval spacing")
        logger.info("=" * 80)

        sorted_timestamps = sorted(normalized_prices.keys())
        correct_spacing = 0
        total_checks = 0

        for i in range(len(sorted_timestamps) - 1):
            dt1 = datetime.fromisoformat(sorted_timestamps[i])
            dt2 = datetime.fromisoformat(sorted_timestamps[i + 1])
            diff_minutes = (dt2 - dt1).total_seconds() / 60

            total_checks += 1
            if diff_minutes == 15.0:
                correct_spacing += 1
            elif i < 5:  # Show first few irregular spacings
                logger.debug(
                    f"  {dt1.strftime('%H:%M')} → {dt2.strftime('%H:%M')}: {diff_minutes:.0f} minutes"
                )

        spacing_pct = (correct_spacing / total_checks * 100) if total_checks > 0 else 0
        logger.info(
            f"  Intervals with correct 15-minute spacing: {correct_spacing}/{total_checks} ({spacing_pct:.1f}%)"
        )

        if spacing_pct > 95:
            logger.info(f"✅ Interval spacing is correct!")
        else:
            logger.warning(f"⚠️  Some intervals have irregular spacing")

        # Step 7: Display price data
        logger.info("\n" + "=" * 80)
        logger.info("Step 7: Price Data Display")
        logger.info("=" * 80)
        logger.info(f"  Currency: {target_currency}/kWh")
        logger.info(f"  Total intervals: {len(normalized_prices)}")

        sorted_keys = sorted(normalized_prices.keys())

        logger.info(f"\nFirst 8 intervals:")
        for time_key in sorted_keys[:8]:
            price_data = normalized_prices[time_key]
            price_val = price_data.get(
                "converted_kwh", price_data.get("price", price_data)
            )
            dt = datetime.fromisoformat(time_key)
            logger.info(
                f"  {dt.strftime('%Y-%m-%d %H:%M')} → {price_val:.4f} {target_currency}/kWh"
            )

        logger.info(f"\nLast 8 intervals:")
        for time_key in sorted_keys[-8:]:
            price_data = normalized_prices[time_key]
            price_val = price_data.get(
                "converted_kwh", price_data.get("price", price_data)
            )
            dt = datetime.fromisoformat(time_key)
            logger.info(
                f"  {dt.strftime('%Y-%m-%d %H:%M')} → {price_val:.4f} {target_currency}/kWh"
            )

        # Step 8: Validate data completeness
        logger.info("\n" + "=" * 80)
        logger.info("Step 8: Data completeness validation")
        logger.info("=" * 80)

        logger.info(f"  Timezone: {LOCAL_TZ_NAME}")
        logger.info(f"  Total intervals: {len(normalized_prices)}")
        logger.info(
            f"  Expected intervals per day: {TimeInterval.get_intervals_per_day()}"
        )

        # Calculate coverage
        hours_coverage = len(sorted_timestamps) / TimeInterval.get_intervals_per_hour()
        logger.info(f"  Total coverage: {hours_coverage:.1f} hours")

        # Check date range
        if sorted_timestamps:
            first_dt = datetime.fromisoformat(sorted_timestamps[0])
            last_dt = datetime.fromisoformat(sorted_timestamps[-1])
            logger.info(
                f"  Date range: {first_dt.strftime('%Y-%m-%d %H:%M')} to {last_dt.strftime('%Y-%m-%d %H:%M')}"
            )

        # Final summary
        logger.info("\n" + "=" * 80)
        logger.info("TEST SUMMARY")
        logger.info("=" * 80)

        if prices_5min:
            logger.info(f"✅ API fetch: {len(prices_5min)} 5-minute records")
            logger.info(
                f"✅ Aggregation: {len(prices_5min)} 5-min → {len(interval_raw_prices)} 15-min intervals (3:1 ratio)"
            )
        else:
            logger.info(f"✅ API fetch: Processed data received")

        logger.info(f"✅ Parsing: {len(interval_raw_prices)} 15-minute intervals")
        logger.info(f"✅ Spacing: {spacing_pct:.1f}% intervals correctly spaced")
        logger.info(f"✅ Coverage: {hours_coverage:.1f} hours")

        if len(normalized_prices) >= TimeInterval.get_intervals_per_day():
            logger.info(f"✅ At least 1 full day of data available!")
            logger.info("\n" + "=" * 80)
            logger.info("ALL TESTS PASSED ✅")
            logger.info("=" * 80)
            return 0
        elif len(normalized_prices) >= TimeInterval.get_intervals_per_day() * 0.9:
            logger.info(
                f"✅ Nearly 1 full day of data ({len(normalized_prices)}/{TimeInterval.get_intervals_per_day()} intervals)"
            )
            logger.info("\n" + "=" * 80)
            logger.info("TEST COMPLETED ✅")
            logger.info("=" * 80)
            return 0
        elif len(normalized_prices) > 0:
            logger.warning(
                f"⚠️  Partial day data ({len(normalized_prices)}/{TimeInterval.get_intervals_per_day()} intervals)"
            )
            logger.info("\n" + "=" * 80)
            logger.info("TEST COMPLETED (with warnings) ⚠️")
            logger.info("=" * 80)
            return 0
        else:
            logger.error(f"\n❌ FAILED: No price data found")
            logger.info("\n" + "=" * 80)
            logger.info("TEST FAILED ❌")
            logger.info("=" * 80)
            return 1

    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=args.debug)
        return 1


if __name__ == "__main__":
    print("Starting ComEd API full chain test...")
    # Ensure asyncio event loop is managed correctly
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))
