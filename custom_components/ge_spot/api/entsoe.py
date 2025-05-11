"""API handler for ENTSO-E Transparency Platform."""
import logging
import asyncio
from datetime import datetime, timezone, timedelta, time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import httpx # Changed to import httpx
from httpx import AsyncClient, HTTPStatusError, RequestError # Explicitly import exceptions

from .base_api import BaseAPI, PriceData # Corrected import
from .registry import register_adapter
from ..const.api import ENTSOE_AREAS, ENTSOE_SECURITY_TOKEN
from ..const.sources import Source
from ..const.areas import AreaMapping, ALL_ENTSOE_AREAS
from ..const.config import Config
from ..const.display import DisplayUnit
from ..const.network import Network, ContentType
from ..const.time import TimeFormat, SourceTimezone # Added SourceTimezone
from ..const.energy import EnergyUnit
from ..const.currencies import Currency
from .parsers.entsoe_parser import EntsoeParser, EntsoeParsingError # Added EntsoeParsingError
# Removed: from .base.base_price_api import BasePriceAPI
# Removed: from .base_adapter import BaseAPIAdapter, PriceData
from .base.api_client import ApiClient # Added ApiClient import
from .base.error_handler import ErrorHandler
from .base.data_structure import create_standardized_price_data
from .utils import fetch_with_retry
from ..utils.date_range import generate_date_ranges # Added generate_date_ranges
from ..utils.debug_utils import sanitize_sensitive_data # Changed import path
from ..const.time import TimezoneName
from ..timezone.timezone_utils import get_timezone_object

_LOGGER = logging.getLogger(__name__)

@register_adapter(
    name=Source.ENTSOE,
    regions=ALL_ENTSOE_AREAS, 
    default_priority=70,
)
class EntsoeAPI(BaseAPI):
    """API client for ENTSO-E."""

    BASE_URL = "https://web-api.tp.entsoe.eu/api"

    def __init__(self, hass, api_key_manager, source_name: str, market_area: str, session, **kwargs):
        """Initialize the ENTSO-E adapter."""
        super().__init__(hass, api_key_manager, source_name, market_area, session, **kwargs)
        self.api_key = self.api_key_manager.get_api_key(self.source_name) 
        if not self.api_key:
             self.api_key = self.api_key_manager.get_api_key("ENTSOE_API_KEY")

        self.parser = EntsoeParser()

    def _get_base_url(self) -> str:
        """Get the base URL for the API."""
        return Network.URLs.ENTSOE

    async def async_fetch_data(self, target_datetime: datetime) -> PriceData:
        """Fetch and parse data from ENTSO-E, returning a PriceData object."""
        _LOGGER.debug(f"ENTSO-E Adapter: Fetching data for {self.market_area} at {target_datetime.isoformat()}")

        if not self.api_key:
            _LOGGER.error(f"ENTSO-E API key not available for {self.source_name}. Cannot fetch data.")
            return PriceData(hourly_raw=[], timezone="UTC", currency=Currency.EUR, source=self.source_name, meta={"error": "API key missing"})

        async with ApiClient(session=self.session) as client:
            raw_api_response = await self._fetch_data(client, area=self.market_area, reference_time=target_datetime)

        if not raw_api_response or raw_api_response.get("error"):
            error_message = raw_api_response.get("error", "Unknown error during fetch") if raw_api_response else "No data from _fetch_data"
            _LOGGER.error(f"ENTSO-E fetch error for {self.market_area}: {error_message}")
            return PriceData(hourly_raw=[], timezone="UTC", currency=Currency.EUR, source=self.source_name, meta={"error": str(error_message)})

        parsed_data = self.parser.parse(raw_api_response)

        hourly_raw_from_parser = parsed_data.get("hourly_raw", {})
        final_hourly_prices = []

        for iso_ts_str, price_mwh in hourly_raw_from_parser.items():
            try:
                start_time_dt = datetime.fromisoformat(iso_ts_str)
                price_kwh = round(float(price_mwh) / 1000.0, 5)
                final_hourly_prices.append({
                    "start_time": start_time_dt, # Changed from API_RESPONSE_START_TIME
                    "price": price_kwh          # Changed from API_RESPONSE_PRICE
                })
            except (ValueError, TypeError) as e:
                _LOGGER.warning(f"Could not parse/convert entry for {iso_ts_str} from ENTSO-E: {price_mwh}. Error: {e}")
                continue
        
        final_hourly_prices.sort(key=lambda x: x["start_time"]) # Changed from API_RESPONSE_START_TIME
        
        source_currency = parsed_data.get("currency", Currency.EUR)
        source_timezone = parsed_data.get("timezone", "UTC")

        _LOGGER.info(f"Successfully processed {len(final_hourly_prices)} price points from ENTSO-E for {self.market_area}")
        return PriceData(
            hourly_raw=final_hourly_prices,
            timezone=source_timezone,
            currency=source_currency,
            source=self.source_name,
            meta={
                "api_url": self._get_base_url(),
                "raw_unit": f"{source_currency}/MWh",
                "entsoe_area": raw_api_response.get("entsoe_area"),
                "document_type": raw_api_response.get("document_type"),
                "parser_metadata": parsed_data.get("metadata")
            }
        )

    async def _fetch_data(self, client: ApiClient, area: str, reference_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Fetch data from ENTSO-E API. (Modified to use self.api_key)"""
        api_key = self.api_key
        if not api_key:
            _LOGGER.debug("No API key available for ENTSO-E, skipping fetch in _fetch_data")
            raise ValueError("No API key provided for ENTSO-E")

        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
        entsoe_area = AreaMapping.ENTSOE_MAPPING.get(area, area)
        headers = {
            "User-Agent": Network.Defaults.USER_AGENT,
            "Accept": ContentType.XML,
            "Content-Type": ContentType.XML
        }
        date_ranges = generate_date_ranges(reference_time, Source.ENTSOE)
        xml_responses = []
        dict_response_found = None
        found_doc_type = None
        last_exception = None

        for start_date, end_date in date_ranges:
            period_start = start_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)
            period_end = end_date.strftime(TimeFormat.ENTSOE_DATE_HOUR)
            doc_types = ["A44", "A65"]
            for doc_type in doc_types:
                params = {
                    "securityToken": self.api_key,
                    "documentType": doc_type,
                    "in_Domain": entsoe_area,
                    "out_Domain": entsoe_area,
                    "periodStart": period_start,
                    "periodEnd": period_end,
                }
                _LOGGER.debug(f"ENTSO-E fetch: doc_type={doc_type}, range={period_start}-{period_end}, params={sanitize_sensitive_data(params)}")
                try:
                    response = await client.fetch(
                        self._get_base_url(),
                        params=params,
                        headers=headers,
                        timeout=Network.Defaults.TIMEOUT
                    )
                    if isinstance(response, dict) and response.get("error"):
                        status_code = response.get("status_code")
                        message = response.get('message', 'Unknown API error')
                        _LOGGER.error(f"ENTSO-E API error (status {status_code}) for doc_type={doc_type}, range={period_start}-{period_end}: {message}")
                        if status_code == 401:
                            raise ValueError(f"ENTSO-E API authentication failed (401 Unauthorized). Check your API key. Message: {message}")
                        else:
                            continue
                    if not response:
                        _LOGGER.debug(f"ENTSO-E empty response for doc_type={doc_type}, range={period_start}-{period_end}")
                        continue
                    if isinstance(response, str):
                        if "Not authorized" in response:
                            _LOGGER.error("ENTSO-E API authentication failed: 'Not authorized' string found.")
                            raise ValueError("ENTSO-E API authentication failed: 'Not authorized' string found.")
                        elif "No matching data found" in response:
                            _LOGGER.debug(f"ENTSO-E 'No matching data found' for doc_type={doc_type}, range={period_start}-{period_end}")
                            continue
                        elif "Publication_MarketDocument" in response:
                            _LOGGER.info(f"Fetched ENTSO-E XML data with doc_type={doc_type} for area {area}")
                            xml_responses.append(response)
                            break 
                        else:
                            _LOGGER.warning(f"Unexpected string response content from ENTSO-E for doc_type={doc_type}: {response[:200]}...")
                            continue
                    elif isinstance(response, dict) and response:
                        _LOGGER.info(f"Fetched ENTSO-E dict data with doc_type={doc_type} for area {area}")
                        if not dict_response_found:
                            dict_response_found = response
                            found_doc_type = doc_type
                        break 
                    else:
                        _LOGGER.warning(f"Unexpected response type from ENTSO-E: {type(response).__name__}")
                        continue
                except asyncio.TimeoutError:
                    _LOGGER.warning(f"ENTSO-E request timed out for doc_type={doc_type}, range={period_start}-{period_end}")
                    continue
                except ValueError as e:
                    _LOGGER.error(f"ValueError during ENTSO-E fetch processing for doc_type={doc_type}: {e}")
                    if "authentication failed" in str(e):
                        raise e 
                    continue
                except Exception as e:
                    _LOGGER.error(f"Unexpected error during ENTSO-E fetch for doc_type={doc_type}: {e}", exc_info=True)
                    continue
            if xml_responses or dict_response_found:
                _LOGGER.info(f"Got valid ENTSO-E response(s) for date range {period_start} to {period_end}, skipping remaining ranges")
                break
        
        tomorrow_xml = None
        now_utc = datetime.now(timezone.utc)
        cet_tz = get_timezone_object("Europe/Paris")
        now_cet = now_utc.astimezone(cet_tz)

        release_hour_cet = 13
        failure_check_hour_cet = 16

        should_fetch_tomorrow = now_cet.hour >= release_hour_cet

        if should_fetch_tomorrow:
            tomorrow = (reference_time + timedelta(days=1))
            period_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).strftime(TimeFormat.ENTSOE_DATE_HOUR)
            period_end = (tomorrow.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).strftime(TimeFormat.ENTSOE_DATE_HOUR)

            params_tomorrow = {
                "securityToken": self.api_key,
                "documentType": "A44", 
                "in_Domain": entsoe_area,
                "out_Domain": entsoe_area,
                "periodStart": period_start,
                "periodEnd": period_end,
            }

            async def fetch_tomorrow():
                return await client.fetch(self._get_base_url(), params=params_tomorrow, headers=headers, timeout=Network.Defaults.TIMEOUT)

            def is_data_available(data):
                return data and isinstance(data, str) and "Publication_MarketDocument" in data

            tomorrow_xml = await fetch_with_retry(
                fetch_tomorrow,
                is_data_available,
                retry_interval=1800,
                end_time=time(23, 50),
                local_tz_name=TimezoneName.EUROPE_PARIS
            )

            if tomorrow_xml:
                xml_responses.append(tomorrow_xml)

            if now_cet.hour >= failure_check_hour_cet and not is_data_available(tomorrow_xml):
                _LOGGER.warning(
                    f"ENTSO-E fetch failed for area {area}: Tomorrow's data expected after {failure_check_hour_cet}:00 CET "
                    f"but was not available or invalid. Triggering fallback."
                )
                last_exception = ValueError(f"Tomorrow's data missing after {failure_check_hour_cet}:00 CET")
                return None

        if not dict_response_found and not xml_responses:
            _LOGGER.error(f"ENTSO-E fetch failed for area {area}: No valid data found for today either.")
            final_error = last_exception if last_exception else ValueError(f"No valid data found for area {area}")
            return {"attempted_sources": [self.source_name], "error": final_error}

        final_result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_timezone": SourceTimezone.API_TIMEZONES[Source.ENTSOE],
            "source": self.source_name,
            "area": area,
            "entsoe_area": entsoe_area,
            "raw_data": {}
        }
        if dict_response_found:
            final_result["dict_response"] = dict_response_found
            final_result["document_type"] = found_doc_type
            final_result["raw_data"]["dict_response"] = dict_response_found
        if xml_responses:
            final_result["xml_responses"] = xml_responses
            final_result["raw_data"]["xml_responses"] = xml_responses
        if not final_result["raw_data"]:
             _LOGGER.error(f"ENTSO-E logic error: No dict_response or xml_responses added to raw_data for area {area}")
             return {"attempted_sources": [self.source_name], "error": ValueError("No raw data populated")}
        return final_result

    @property
    def name(self) -> str:
        return f"ENTSO-E ({self.market_area})"

    async def fetch_data(self, area: str) -> PriceData:
        """Fetch data from ENTSO-E API and convert to standard PriceData format."""
        _LOGGER.debug(f"EntsoeAPI: Fetching data for area {area}")
        now_utc = datetime.now(timezone.utc)
        security_token = self.get_config_value(Config.API_TOKEN_ENTSOE, ENTSOE_SECURITY_TOKEN)
        if not security_token:
            _LOGGER.error("EntsoeAPI: Security token is not configured.")
            return PriceData(source=self.api_name, meta={"error": "Missing security token"})

        area_code = AreaMapping.ENTSOE_MAPPING.get(area, area)
        headers = {
            "User-Agent": Network.Defaults.USER_AGENT,
            "Accept": ContentType.XML,
            "Content-Type": ContentType.XML
        }
        params = {
            "securityToken": security_token,
            "documentType": "A44", 
            "in_Domain": area_code,
            "out_Domain": area_code,
            "periodStart": now_utc.strftime(TimeFormat.ENTSOE_DATE_HOUR),
            "periodEnd": (now_utc + timedelta(days=1)).strftime(TimeFormat.ENTSOE_DATE_HOUR),
        }

        try:
            # Use httpx.AsyncClient directly as in the original code for this specific fetch
            async with httpx.AsyncClient() as client:
                 response = await client.get(self.BASE_URL, params=params, headers=headers, timeout=Network.Defaults.TIMEOUT)
            response.raise_for_status()

            xml_response = response.text
            _LOGGER.debug(f"EntsoeAPI: Raw XML response for {area}: {xml_response[:200]}")

            parsed_prices = self.parser.parse(xml_response) # This should return List[PriceEntry] or similar

            if not parsed_prices: # Assuming parser returns a list, and it could be empty
                _LOGGER.warning(f"EntsoeAPI: No prices extracted for {area} from response: {xml_response[:200]}")
                return PriceData(source=self.api_name, meta={"error": f"No prices extracted for {area}"})

            area_timezone_str = self.parser.extract_timezone(xml_response) or "UTC"
            area_currency_str = self.parser.extract_currency(xml_response) or "EUR"
            
            # Ensure parsed_prices is in the format List[Dict[str, Any]] with 'start_time' and 'price'
            # If self.parser.parse already returns this, no transformation is needed here.
            # If it returns something else, it needs to be transformed.
            # For now, assuming self.parser.parse returns the correct List[PriceEntry]-like structure.

            return PriceData(
                hourly_raw=parsed_prices, 
                timezone=area_timezone_str,
                currency=area_currency_str,
                source=self.api_name,
                meta={
                    "api_response_snippet": xml_response[:200],
                    "fetch_timestamp_utc": now_utc.isoformat(),
                    "document_type": params.get("documentType"),
                    "original_area_code": area_code
                }
            )

        except HTTPStatusError as e: # Changed from httpx.HTTPStatusError
            _LOGGER.error(
                f"EntsoeAPI: HTTP error for {area}: {e.response.status_code} - {e.response.text[:200]}"
            )
            return PriceData(source=self.api_name, meta={"error": f"HTTP {e.response.status_code} for {area}"})
        except RequestError as e: # Changed from httpx.RequestError
            _LOGGER.error(f"EntsoeAPI: Request error for {area}: {e}")
            return PriceData(source=self.api_name, meta={"error": f"Request error for {area}: {e}"})
        except EntsoeParsingError as e:
            _LOGGER.error(f"EntsoeAPI: Parsing error for {area}: {e}. Response: {e.raw_data[:200] if e.raw_data else 'N/A'}")
            return PriceData(source=self.api_name, meta={"error": f"Parsing error for {area}: {e}"})
        except Exception as e:
            _LOGGER.exception(f"EntsoeAPI: Unexpected error fetching data for {area}: {e}")
            return PriceData(source=self.api_name, meta={"error": f"Unexpected error for {area}: {str(e)}"})
