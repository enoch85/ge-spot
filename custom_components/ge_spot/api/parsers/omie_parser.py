"""Parser for OMIE API responses."""

import logging
from io import StringIO
from datetime import datetime, timezone
from typing import Dict, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ...const.sources import Source
from ...const.currencies import Currency
from ..base.price_parser import BasePriceParser
from ..interval_expander import convert_to_target_intervals

_LOGGER = logging.getLogger(__name__)


class OmieParser(BasePriceParser):
    """Parser for OMIE API responses."""

    def __init__(self, source: str = Source.OMIE, timezone_service=None):
        """Initialize the parser.

        Args:
            source: Source identifier (defaults to Source.OMIE)
            timezone_service: Optional timezone service
        """
        super().__init__(source, timezone_service)

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse OMIE API response dictionary containing raw text data for today and tomorrow.

        Args:
            data: Dictionary from OmieAPI._fetch_data containing:
                  'raw_data': Dict like {"today": str|None, "tomorrow": str|None}
                  'timezone': The timezone name string (e.g. 'Europe/Madrid').
                  'area': The area code ('ES' or 'PT').
                  'currency': Currency code (e.g. 'EUR').
                  'source': The source identifier (e.g. 'omie').
                  'fetched_at': ISO timestamp of fetch.

        Returns:
            Parsed data dictionary: {'interval_raw': {...}, 'currency': 'EUR', 'timezone': 'Europe/Madrid', 'source': 'omie'}
        """
        # Extract info from the input dictionary
        raw_data_payload = data.get("raw_data")
        source_timezone = data.get("timezone", "Europe/Madrid")
        area = data.get("area", "ES")
        _LOGGER.debug(
            f"[OmieParser] Received data for Area: {area}, Timezone: {source_timezone}"
        )

        result = {
            "interval_raw": {},
            "currency": data.get(
                "currency", Currency.EUR
            ),  # Use provided currency or default
            "source": data.get("source", Source.OMIE),
            "timezone": source_timezone,
            "metadata": {"fetched_at": data.get("fetched_at"), "area": area},
        }

        if not raw_data_payload or not isinstance(raw_data_payload, dict):
            _LOGGER.warning(
                "[OmieParser] No valid 'raw_data' dictionary found in input."
            )
            return result

        # --- Parsing Logic for Yesterday, Today and Tomorrow ---
        # Process yesterday (for timezone offset), today and tomorrow data
        days_to_parse = ["yesterday", "today", "tomorrow"]

        for day_key in days_to_parse:
            raw_text = raw_data_payload.get(day_key)
            if raw_text and isinstance(raw_text, str):
                _LOGGER.debug(f"[OmieParser] Parsing data for '{day_key}'.")
                try:
                    # Pass the raw text and let the sub-parser handle it
                    if raw_text.strip().startswith("{") and raw_text.strip().endswith(
                        "}"
                    ):
                        _LOGGER.debug(
                            f"[OmieParser] Attempting to parse '{day_key}' data as JSON."
                        )
                        self._parse_json(raw_text, result, source_timezone)
                    else:
                        _LOGGER.debug(
                            f"[OmieParser] Attempting to parse '{day_key}' data as CSV."
                        )
                        self._parse_csv(raw_text, result, source_timezone)

                except Exception as e:
                    _LOGGER.error(
                        f"[OmieParser] Failed during parsing of '{day_key}' data: {e}",
                        exc_info=True,
                    )
            elif raw_text is not None:
                _LOGGER.warning(
                    f"[OmieParser] Expected string data for '{day_key}', but got {type(raw_text)}. Skipping."
                )

        _LOGGER.debug(
            f"[OmieParser] Found {len(result['interval_raw'])} total interval prices after parsing available days."
        )
        if not result["interval_raw"]:
            _LOGGER.warning(
                "[OmieParser] Parsing completed, but no interval prices were extracted from any provided data."
            )
        else:
            # OMIE provides hourly data (60-minute intervals)
            # Expand to target interval (typically 15 minutes) by replicating hourly values
            _LOGGER.debug(
                f"[OmieParser] Expanding {len(result['interval_raw'])} hourly prices to 15-minute intervals"
            )
            result["interval_raw"] = convert_to_target_intervals(
                source_prices=result["interval_raw"],
                source_interval_minutes=60,  # OMIE provides hourly data
            )
            _LOGGER.debug(
                f"[OmieParser] After expansion: {len(result['interval_raw'])} interval prices"
            )

        return result

    def _parse_json(
        self, json_data: str, result: Dict[str, Any], timezone_name: str
    ) -> None:
        """Parse JSON data (less common for OMIE files, might be ESIOS format)."""
        interval_prices = {}
        try:
            local_tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            _LOGGER.error(
                f"[OmieParser/_parse_json] Timezone '{timezone_name}' not found. Falling back to UTC."
            )
            local_tz = timezone.utc

        try:
            data = json.loads(json_data)
            if "PVPC" in data and isinstance(data["PVPC"], list):
                _LOGGER.debug(
                    "[OmieParser/_parse_json] Parsing ESIOS PVPC JSON structure."
                )
                for entry in data["PVPC"]:
                    try:
                        day_str = entry.get("Dia")
                        hour_str = entry.get("Hora")  # HH-HH+1
                        price_str = None
                        for field in ["PCB", "CYM", "GEN", "price"]:
                            if field in entry and entry[field]:
                                price_str = entry[field]
                                break
                        if not day_str or not hour_str or price_str is None:
                            continue

                        price = float(str(price_str).replace(",", "."))
                        start_hour = int(hour_str.split("-")[0])

                        # Correct indentation for date parsing
                        if "/" in day_str:
                            day, month, year = map(int, day_str.split("/"))
                        else:
                            year, month, day = map(int, day_str.split("-"))

                        # Correct indentation for datetime creation and conversion
                        dt_naive = datetime(year, month, day, start_hour)
                        dt_local = dt_naive.replace(tzinfo=local_tz)
                        dt_utc = dt_local.astimezone(timezone.utc)
                        timestamp = dt_utc.isoformat()
                        interval_prices[timestamp] = price
                    except (ValueError, KeyError, IndexError, TypeError) as e:
                        _LOGGER.warning(
                            f"[OmieParser/_parse_json] Error parsing PVPC entry: {entry}. Error: {e}"
                        )
                        continue  # Correct indentation for continue
            else:
                _LOGGER.warning(
                    "[OmieParser/_parse_json] JSON data found, but not in expected PVPC format."
                )

            result["interval_raw"].update(interval_prices)
            _LOGGER.debug(
                f"[OmieParser/_parse_json] Parsed {len(interval_prices)} prices from JSON."
            )

        except json.JSONDecodeError as e:
            _LOGGER.error(f"[OmieParser/_parse_json] Invalid JSON: {e}")
        except Exception as e:
            _LOGGER.error(
                f"[OmieParser/_parse_json] Error during JSON parsing: {e}",
                exc_info=True,
            )

    def _parse_csv(
        self, csv_data: str, result: Dict[str, Any], timezone_name: str
    ) -> None:
        """Parse CSV-like text data from OMIE files (Updated Logic)."""
        interval_prices = {}
        area = result.get("metadata", {}).get("area", "ES")
        target_date_str = None
        price_line = None

        try:
            local_tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            _LOGGER.error(
                f"[OmieParser/_parse_csv] Timezone '{timezone_name}' not found. Falling back to UTC."
            )
            local_tz = timezone.utc

        try:
            csv_file = StringIO(csv_data)
            lines = csv_file.readlines()

            # 1. Find the date from the first few lines
            for i, line in enumerate(lines[:5]):  # Check first 5 lines for date
                parts = line.strip().split(";")
                if (
                    len(parts) > 3 and parts[3].count("/") == 2
                ):  # Look for DD/MM/YYYY in 4th column
                    try:
                        # Validate it looks like a date
                        datetime.strptime(parts[3], "%d/%m/%Y")
                        target_date_str = parts[3]
                        _LOGGER.debug(
                            f"[OmieParser/_parse_csv] Found target date: {target_date_str} in line {i+1}"
                        )
                        break
                    except ValueError:
                        continue  # Not a valid date in this format
            if not target_date_str:
                _LOGGER.error(
                    "[OmieParser/_parse_csv] Could not find target date (DD/MM/YYYY) in header lines."
                )
                return

            # 2. Find the relevant price line based on area
            price_line_prefix_es = "Precio marginal en el sistema español"
            price_line_prefix_pt = "Precio marginal en el sistema portugués"
            target_prefix = (
                price_line_prefix_pt if area.upper() == "PT" else price_line_prefix_es
            )
            fallback_prefix = (
                price_line_prefix_es if area.upper() == "PT" else price_line_prefix_pt
            )

            for i, line in enumerate(lines):
                stripped_line = line.strip()
                if stripped_line.startswith(target_prefix):
                    price_line = stripped_line
                    _LOGGER.debug(
                        f"[OmieParser/_parse_csv] Found target price line for {area}: '{price_line[:100]}...'"
                    )
                    break

            # Fallback if primary area line not found (e.g. PT requested but only ES exists)
            if not price_line:
                _LOGGER.warning(
                    f"[OmieParser/_parse_csv] Target price line for {area} not found, trying fallback."
                )
                for i, line in enumerate(lines):
                    stripped_line = line.strip()
                    if stripped_line.startswith(fallback_prefix):
                        price_line = stripped_line
                        _LOGGER.debug(
                            f"[OmieParser/_parse_csv] Found fallback price line: '{price_line[:100]}...'"
                        )
                        break

            if not price_line:
                _LOGGER.error(
                    f"[OmieParser/_parse_csv] Could not find any price line starting with '{target_prefix}' or '{fallback_prefix}'."
                )
                return

            # 3. Parse the date
            try:
                day, month, year = map(int, target_date_str.split("/"))
                target_date = datetime(year, month, day).date()
            except ValueError:
                _LOGGER.error(
                    f"[OmieParser/_parse_csv] Failed to parse found date string: {target_date_str}"
                )
                return

            # 4. Extract prices from the found line
            price_parts = price_line.split(";")
            if len(price_parts) < 25:  # Need prefix + 24 prices
                _LOGGER.error(
                    f"[OmieParser/_parse_csv] Price line does not contain enough columns (expected >= 25): {price_line}"
                )
                return

            raw_prices = [
                p.strip() for p in price_parts[1:25]
            ]  # Prices are in columns 1 to 24 (0-indexed)
            _LOGGER.debug(
                f"[OmieParser/_parse_csv] Extracted {len(raw_prices)} raw price strings: {raw_prices}"
            )

            # 5. Combine date, hour (1-24), and prices
            for hour_1_24, price_str in enumerate(raw_prices, 1):
                try:
                    if not price_str:
                        _LOGGER.warning(
                            f"[OmieParser/_parse_csv] Missing price for hour {hour_1_24}. Skipping."
                        )
                        continue

                    # Clean and parse price (allow comma, digits, minus)
                    cleaned_price_str = "".join(
                        c for c in price_str if c.isdigit() or c == "," or c == "-"
                    )
                    if not cleaned_price_str or cleaned_price_str == "-":
                        _LOGGER.warning(
                            f"[OmieParser/_parse_csv] Invalid price string for hour {hour_1_24}: '{price_str}' -> '{cleaned_price_str}'. Skipping."
                        )
                        continue
                    price = float(cleaned_price_str.replace(",", "."))

                    # Create timestamp
                    hour_0_23 = hour_1_24 - 1
                    dt_naive = datetime.combine(
                        target_date, datetime.min.time().replace(hour=hour_0_23)
                    )
                    dt_local = dt_naive.replace(tzinfo=local_tz)
                    dt_utc = dt_local.astimezone(timezone.utc)
                    timestamp = dt_utc.isoformat()

                    interval_prices[timestamp] = price
                    _LOGGER.debug(
                        f"[OmieParser/_parse_csv] Hour {hour_1_24}: Price={price}, Timestamp={timestamp}"
                    )

                except (ValueError, IndexError) as e:
                    _LOGGER.warning(
                        f"[OmieParser/_parse_csv] Error processing hour {hour_1_24} with price '{price_str}'. Error: {e}"
                    )
                    continue

            result["interval_raw"].update(interval_prices)
            _LOGGER.debug(
                f"[OmieParser/_parse_csv] Successfully parsed {len(interval_prices)} prices from OMIE file."
            )

        except Exception as e:
            _LOGGER.error(
                f"[OmieParser/_parse_csv] Error during CSV processing: {e}",
                exc_info=True,
            )
