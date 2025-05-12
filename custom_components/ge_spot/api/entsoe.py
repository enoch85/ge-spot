"""API handler for ENTSO-E Transparency Platform."""
import logging
import asyncio
from datetime import datetime, timezone, timedelta, time
from typing import Any, Dict, List, Optional

import aiohttp

from .base_api import BaseAPI, PriceData
from .registry import register_api
from ..const.config import CONF_API_TOKEN, CONF_AREA, CONF_SOURCE_NAME
from ..const.api import ENTSOE_SECURITY_TOKEN 
from ..const.sources import Source
from ..const.areas import AreaMapping, ALL_ENTSOE_AREAS 
from ..const.network import Network, ContentType
from ..const.time import TimeFormat, SourceTimezone
from ..const.currencies import Currency
from .parsers.entsoe_parser import EntsoeParser
from ..utils.date_range import generate_date_ranges
from ..utils.debug_utils import sanitize_sensitive_data
from ..timezone.timezone_utils import get_timezone_object

_LOGGER = logging.getLogger(__name__)

@register_api(
    name=Source.ENTSOE,
    regions=ALL_ENTSOE_AREAS,
    default_priority=70,
)
class EntsoeAPI(BaseAPI):
    """API client for ENTSO-E."""

    BASE_URL = "https://web-api.tp.entsoe.eu/api"

    def __init__(self, config: Dict[str, Any], session: aiohttp.ClientSession):
        """Initialize the ENTSO-E adapter."""
        super().__init__(config, session)
        self.api_key = self.config.get(CONF_API_TOKEN) or self.config.get("entsoe_api_key") or self.config.get(ENTSOE_SECURITY_TOKEN)
        self.market_area = self.config.get(CONF_AREA)
        
        if not hasattr(self, 'source_name') or not self.source_name:
            self.source_name = Source.ENTSOE

        if not self.api_key:
            _LOGGER.warning(f"ENTSO-E API key not found in config for source {self.source_name}. API calls may fail.")
        
        self.parser = EntsoeParser()

    def _get_base_url(self) -> str:
        """Get the base URL for the API."""
        return Network.URLs.ENTSOE

    async def fetch_data(self, target_datetime: datetime) -> PriceData:
        """Fetch and parse data from ENTSO-E, returning a PriceData object."""
        _LOGGER.debug(f"ENTSO-E API: Fetching data for {self.market_area} at {target_datetime.isoformat()}")

        if not self.api_key:
            _LOGGER.error(f"ENTSO-E API key not available for {self.source_name}. Cannot fetch data.")
            return PriceData(hourly_raw=[], timezone="UTC", currency=Currency.EUR.value, source=self.source_name, meta={"error": "API key missing"})

        raw_api_response = await self._fetch_data(area=self.market_area, reference_time=target_datetime)

        if not raw_api_response or raw_api_response.get("error"):
            error_message = raw_api_response.get("error", "Unknown error during fetch") if raw_api_response else "No data from _fetch_data"
            _LOGGER.error(f"ENTSO-E fetch error for {self.market_area}: {error_message}")
            return PriceData(hourly_raw=[], timezone="UTC", currency=Currency.EUR.value, source=self.source_name, meta={"error": str(error_message)})

        parsed_data = self.parser.parse(raw_api_response) 

        hourly_raw_from_parser = parsed_data.get("hourly_raw", {})
        final_hourly_prices = []

        for iso_ts_str, price_mwh in hourly_raw_from_parser.items():
            try:
                start_time_dt = datetime.fromisoformat(iso_ts_str)
                if price_mwh is None: continue
                price_kwh = round(float(price_mwh) / 1000.0, 5)
                final_hourly_prices.append({
                    "start_time": start_time_dt,
                    "price": price_kwh
                })
            except (ValueError, TypeError) as e:
                _LOGGER.warning(f"Could not parse/convert entry for {iso_ts_str} from ENTSO-E: {price_mwh}. Error: {e}")
                continue
        
        final_hourly_prices.sort(key=lambda x: x["start_time"])

        source_currency_str = parsed_data.get("currency", Currency.EUR.value)
        source_currency = Currency(source_currency_str) if isinstance(source_currency_str, str) else Currency.EUR
        
        source_timezone = parsed_data.get("timezone", "UTC") 

        _LOGGER.info(f"Successfully processed {len(final_hourly_prices)} price points from ENTSO-E for {self.market_area}")
        return PriceData(
            hourly_raw=final_hourly_prices,
            timezone=source_timezone, # This is the timezone of the source data interpretation, not necessarily of start_time values
            currency=source_currency.value,
            source=self.source_name,
            meta={
                "api_url": self._get_base_url(),
                "raw_unit": f"{source_currency.value}/MWh",
                "entsoe_area_queried": self.market_area, # Add the original market area queried
                "entsoe_area_used": raw_api_response.get("entsoe_area"), # Actual ENTSO-E area code used
                "document_type": raw_api_response.get("document_type"),
                "parser_metadata": parsed_data.get("metadata"),
                # Preserve raw XML responses
                "raw_xml_responses": raw_api_response.get("xml_responses", [])
            }
        )

    async def _fetch_data(self, area: str, reference_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Fetch data from ENTSO-E API using self.session."""
        if not self.api_key:
            return {"error": "API key missing in _fetch_data", "attempted_sources": [self.source_name]}

        if reference_time is None:
            reference_time = datetime.now(timezone.utc)
        
        entsoe_area = AreaMapping.ENTSOE_MAPPING.get(area, area)
        request_headers = {
            "User-Agent": Network.Defaults.USER_AGENT,
            "Accept": ContentType.XML,
        }
        date_ranges = generate_date_ranges(reference_time, Source.ENTSOE)
        xml_responses: List[str] = []
        found_doc_type: Optional[str] = None
        last_exception: Optional[Exception] = None

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
                _LOGGER.debug(f"ENTSO-E fetch: doc_type={doc_type}, area={area}({entsoe_area}), range={period_start}-{period_end}, params={sanitize_sensitive_data(params)}")
                
                response_text: Optional[str] = None
                try:
                    async with self.session.get(
                        self._get_base_url(),
                        params=params,
                        headers=request_headers,
                        timeout=aiohttp.ClientTimeout(total=Network.Defaults.TIMEOUT)
                    ) as response:
                        response_text = await response.text()
                        if response.status != 200:
                            _LOGGER.error(f"ENTSO-E API error (status {response.status}) for doc_type={doc_type}, area={area}, range={period_start}-{period_end}. Response: {response_text[:200]}")
                            if response.status == 401: # Unauthorized
                                last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"ENTSO-E API authentication failed (401). Check API key. Response: {response_text[:200]}", headers=response.headers)
                                return {"error": str(last_exception), "status_code": response.status, "attempted_sources": [self.source_name]}
                            else:
                                last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"API error {response.status}. Response: {response_text[:200]}", headers=response.headers)
                                continue # Try next doc_type
                        
                        if not response_text:
                            _LOGGER.debug(f"ENTSO-E empty response (status 200) for doc_type={doc_type}, range={period_start}-{period_end}")
                            last_exception = ValueError("Empty response despite 200 status")
                            continue

                        if "Not authorized" in response_text:
                            _LOGGER.error(f"ENTSO-E API authentication failed: 'Not authorized' string found in response. Doc_type={doc_type}, area={area}")
                            last_exception = ValueError("ENTSO-E API authentication failed: 'Not authorized' string found.")
                            return {"error": str(last_exception), "status_code": 401, "attempted_sources": [self.source_name]}
                        elif "No matching data found" in response_text:
                            _LOGGER.debug(f"ENTSO-E 'No matching data found' for doc_type={doc_type}, area={area}, range={period_start}-{period_end}")
                            last_exception = FileNotFoundError(f"No matching data found for doc_type={doc_type}, area={area}")
                            continue
                        elif "Publication_MarketDocument" in response_text:
                            _LOGGER.info(f"Fetched ENTSO-E XML data with doc_type={doc_type} for area {area}, range {period_start}-{period_end}")
                            xml_responses.append(response_text)
                            found_doc_type = doc_type
                            break # Found data for this date range, break from doc_types loop
                        else:
                            _LOGGER.warning(f"Unexpected XML content from ENTSO-E for doc_type={doc_type}, area={area}: {response_text[:200]}...")
                            last_exception = ValueError("Unexpected XML content")
                            continue
                
                except asyncio.TimeoutError:
                    _LOGGER.warning(f"ENTSO-E request timed out for doc_type={doc_type}, area={area}, range={period_start}-{period_end}")
                    last_exception = asyncio.TimeoutError(f"Request timed out for doc_type={doc_type}, area={area}")
                    continue # Try next doc_type or range
                except aiohttp.ClientError as e:
                    _LOGGER.error(f"aiohttp.ClientError during ENTSO-E fetch for doc_type={doc_type}, area={area}: {e}", exc_info=True)
                    last_exception = e
                    if isinstance(e, aiohttp.ClientResponseError) and e.status == 401:
                         return {"error": str(e), "status_code": 401, "attempted_sources": [self.source_name]}
                    continue # Try next doc_type or range
                except ValueError as e:
                    _LOGGER.error(f"ValueError during ENTSO-E fetch processing for doc_type={doc_type}, area={area}: {e}")
                    last_exception = e
                    if "authentication failed" in str(e).lower():
                         return {"error": str(e), "status_code": 401, "attempted_sources": [self.source_name]}
                    continue
                except Exception as e:
                    _LOGGER.error(f"Unexpected error during ENTSO-E fetch for doc_type={doc_type}, area={area}: {e}", exc_info=True)
                    last_exception = e
                    continue # Try next doc_type or range
            
            if xml_responses:
                _LOGGER.info(f"Got valid ENTSO-E response(s) for date range {period_start} to {period_end} (doc_type {found_doc_type}), skipping remaining ranges for this reference_time.")
                break # Break from date_ranges loop

        # Tomorrow's data fetch logic
        now_utc = datetime.now(timezone.utc)
        cet_tz = get_timezone_object("Europe/Paris") # Ensure this util is robust
        now_cet = now_utc.astimezone(cet_tz) if cet_tz else now_utc # Fallback to UTC if tz object fails
        
        release_hour_cet = self.config.get("entsoe_tomorrow_release_hour_cet", 13)

        should_fetch_tomorrow = now_cet.hour >= release_hour_cet and not xml_responses

        if should_fetch_tomorrow:
            _LOGGER.debug(f"Attempting to fetch tomorrow's data for ENTSO-E area {area} (release hour {release_hour_cet} CET passed, current CET hour {now_cet.hour})")
            tomorrow_ref_date = (reference_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).date()
            
            if tomorrow_ref_date > (now_utc + timedelta(days=1)).date():
                _LOGGER.debug(f"Skipping ENTSO-E tomorrow's fetch; target date {tomorrow_ref_date} is too far ahead.")
            else:
                tomorrow_doc_type = "A44"
                tomorrow_period_start_dt = datetime.combine(tomorrow_ref_date, time.min, tzinfo=timezone.utc)
                tomorrow_period_end_dt = datetime.combine(tomorrow_ref_date + timedelta(days=1), time.min, tzinfo=timezone.utc)

                params_tomorrow = {
                    "securityToken": self.api_key,
                    "documentType": tomorrow_doc_type,
                    "in_Domain": entsoe_area,
                    "out_Domain": entsoe_area,
                    "periodStart": tomorrow_period_start_dt.strftime(TimeFormat.ENTSOE_DATE_HOUR),
                    "periodEnd": tomorrow_period_end_dt.strftime(TimeFormat.ENTSOE_DATE_HOUR),
                }
                _LOGGER.debug(f"ENTSO-E fetch tomorrow: area={area}({entsoe_area}), params={sanitize_sensitive_data(params_tomorrow)}")
                try:
                    async with self.session.get(
                        self._get_base_url(), params=params_tomorrow, headers=request_headers, 
                        timeout=aiohttp.ClientTimeout(total=Network.Defaults.TIMEOUT)
                    ) as response:
                        tomorrow_response_text = await response.text()
                        if response.status == 200 and "Publication_MarketDocument" in tomorrow_response_text:
                            _LOGGER.info(f"Fetched ENTSO-E XML data for tomorrow ({tomorrow_ref_date}) for area {area}")
                            xml_responses.append(tomorrow_response_text)
                            if not found_doc_type: found_doc_type = tomorrow_doc_type
                        elif response.status == 200 and "No matching data found" in tomorrow_response_text:
                            _LOGGER.debug(f"ENTSO-E 'No matching data found' for tomorrow's data ({tomorrow_ref_date}), area {area}.")
                        elif response.status != 200:
                             _LOGGER.warning(f"Failed to fetch tomorrow's ENTSO-E data (status {response.status}) for area {area}. Response: {tomorrow_response_text[:200]}")
                        else:
                             _LOGGER.warning(f"Fetched tomorrow's ENTSO-E data for area {area}, but content was unexpected: {tomorrow_response_text[:200]}")
                except asyncio.TimeoutError:
                    _LOGGER.warning(f"ENTSO-E request for tomorrow's data timed out for area {area}")
                except aiohttp.ClientError as e:
                    _LOGGER.warning(f"aiohttp.ClientError for tomorrow's ENTSO-E data fetch, area {area}: {e}", exc_info=True)
                except Exception as e:
                    _LOGGER.warning(f"Unexpected error fetching or processing tomorrow's ENTSO-E data for area {area}: {e}", exc_info=True)

        if not xml_responses:
            error_detail = str(last_exception) if last_exception else f"No valid data found for area {area} after all attempts."
            _LOGGER.error(f"ENTSO-E fetch failed for area {area}: {error_detail}")
            return {"attempted_sources": [self.source_name], "error": error_detail}

        final_result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_timezone": SourceTimezone.API_TIMEZONES.get(Source.ENTSOE, "UTC"),
            "source": self.source_name,
            "area": area,
            "entsoe_area": entsoe_area,
            "xml_responses": xml_responses,
            "document_type": found_doc_type or "A44",
        }
        return final_result

    @property
    def name(self) -> str:
        return f"ENTSO-E ({self.market_area or 'N/A'})"
