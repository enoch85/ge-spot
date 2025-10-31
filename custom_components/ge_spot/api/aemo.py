"""API handler for AEMO (Australian Energy Market Operator) - NEMWEB Pre-dispatch."""

import logging
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import aiohttp

from .base.api_client import ApiClient
from .base.base_price_api import BasePriceAPI
from ..const.sources import Source
from ..const.api import Aemo
from ..const.currencies import Currency
from ..const.network import Network
from ..utils.zip_utils import unzip_single_file

_LOGGER = logging.getLogger(__name__)


class AemoAPI(BasePriceAPI):
    """API client for AEMO NEMWEB Pre-dispatch Reports.

    AEMO (Australian Energy Market Operator) provides 30-minute trading interval
    forecasts through NEMWEB Pre-dispatch Reports. Files are updated every 30 minutes
    and contain ~55 trading intervals (40+ hour forecast horizon).

    Data source: http://www.nemweb.com.au/Reports/Current/PredispatchIS_Reports/

    Regions supported:
    - NSW1 - New South Wales
    - QLD1 - Queensland
    - SA1  - South Australia
    - TAS1 - Tasmania
    - VIC1 - Victoria
    """

    SOURCE_TYPE = Source.AEMO

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        session: Optional[aiohttp.ClientSession] = None,
        timezone_service=None,
    ):
        """Initialize the API client.

        Args:
            config: Configuration dictionary
            session: aiohttp client session
            timezone_service: Timezone service instance
        """
        super().__init__(config, session, timezone_service)

    def _get_base_url(self) -> str:
        """Get the base URL for the API."""
        return Aemo.NEMWEB_PREDISPATCH_URL

    async def fetch_raw_data(
        self, area: str, session=None, **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Fetch raw price data from NEMWEB Pre-dispatch.

        Args:
            area: Area code (e.g. NSW1, QLD1, SA1, TAS1, VIC1)
            session: Optional session for API requests
            **kwargs: Additional parameters

        Returns:
            Dictionary with csv_content, area, timezone, currency, and raw_data metadata.
            This structure is expected by AemoParser.parse()
        """
        # Validate area code
        if area not in Aemo.REGIONS:
            _LOGGER.error(f"Invalid AEMO region: {area}. Must be one of {Aemo.REGIONS}")
            raise ValueError(f"Invalid AEMO region: {area}")

        client = ApiClient(session=session or self.session)
        now_utc = datetime.now(timezone.utc)

        try:
            # Step 1: Get latest pre-dispatch file URL
            _LOGGER.debug("Fetching NEMWEB pre-dispatch directory listing")
            file_url = await self._get_latest_predispatch_file(client)

            if not file_url:
                _LOGGER.error("Could not find latest pre-dispatch file")
                return None

            _LOGGER.info(f"Downloading pre-dispatch file: {file_url}")

            # Step 2: Download ZIP file
            zip_data = await self._download_binary_file(client, file_url)

            if not zip_data:
                _LOGGER.error("Failed to download pre-dispatch file")
                return None

            # Step 3: Extract CSV from ZIP
            _LOGGER.debug(f"Extracting CSV from ZIP ({len(zip_data):,} bytes)")
            csv_content = unzip_single_file(zip_data, expected_extension=".csv")

            _LOGGER.info(
                f"Extracted CSV ({len(csv_content):,} characters) for region {area}"
            )

            # Return data structure expected by parser
            return {
                "csv_content": csv_content,
                "area": area,
                "timezone": self.get_timezone_for_area(area),
                "currency": Currency.AUD,
                "raw_data": {
                    "file_url": file_url,
                    "file_size_bytes": len(zip_data),
                    "csv_size_chars": len(csv_content),
                    "fetched_at": now_utc.isoformat(),
                },
            }

        except Exception as e:
            _LOGGER.error(
                f"Error fetching NEMWEB pre-dispatch data: {e}", exc_info=True
            )
            return None

        finally:
            if session is None and client:
                await client.close()

    async def _get_latest_predispatch_file(self, client: ApiClient) -> Optional[str]:
        """Get URL of the latest pre-dispatch file.

        Fetches the HTML directory listing and extracts the latest file using regex.

        Args:
            client: ApiClient instance for HTTP requests

        Returns:
            Full URL to latest pre-dispatch ZIP file, or None if not found
        """
        try:
            # Fetch directory HTML
            html = await client.fetch(
                Aemo.NEMWEB_PREDISPATCH_URL,
                timeout=Network.Defaults.HTTP_TIMEOUT,
                response_format="text",
            )

            if not html:
                _LOGGER.error("Failed to fetch NEMWEB directory listing")
                return None

            # Extract all pre-dispatch file timestamps
            # Pattern: PUBLIC_PREDISPATCHIS_YYYYMMDDTTHHMM_*.zip
            pattern = Aemo.PREDISPATCH_FILE_PATTERN
            matches = re.findall(pattern, html)

            if not matches:
                _LOGGER.error("No pre-dispatch files found in directory listing")
                return None

            # Sort by timestamp and get latest
            matches.sort()
            latest_timestamp = matches[-1]

            # Find the full filename in HTML (need the second timestamp too)
            full_pattern = f"PUBLIC_PREDISPATCHIS_{latest_timestamp}_\\d{{14}}\\.zip"
            full_match = re.search(full_pattern, html)

            if not full_match:
                _LOGGER.error(
                    f"Could not find full filename for timestamp {latest_timestamp}"
                )
                return None

            filename = full_match.group(0)
            file_url = f"{Aemo.NEMWEB_PREDISPATCH_URL}{filename}"

            _LOGGER.debug(f"Latest pre-dispatch file: {filename}")
            return file_url

        except Exception as e:
            _LOGGER.error(f"Error finding latest pre-dispatch file: {e}", exc_info=True)
            return None

    async def _download_binary_file(
        self, client: ApiClient, url: str
    ) -> Optional[bytes]:
        """Download a binary file (ZIP) from URL.

        Uses aiohttp directly since ApiClient doesn't support binary response format.

        Args:
            client: ApiClient instance
            url: URL to download from

        Returns:
            Binary file content, or None if download fails
        """
        try:
            timeout_obj = aiohttp.ClientTimeout(total=Network.Defaults.HTTP_TIMEOUT * 2)

            if client.session:
                # Use existing session
                async with client.session.get(url, timeout=timeout_obj) as response:
                    if response.status != 200:
                        _LOGGER.error(
                            f"Failed to download {url}: HTTP {response.status}"
                        )
                        return None
                    return await response.read()
            else:
                # Create temporary session
                async with aiohttp.ClientSession() as temp_session:
                    async with temp_session.get(url, timeout=timeout_obj) as response:
                        if response.status != 200:
                            _LOGGER.error(
                                f"Failed to download {url}: HTTP {response.status}"
                            )
                            return None
                        return await response.read()

        except Exception as e:
            _LOGGER.error(
                f"Error downloading binary file from {url}: {e}", exc_info=True
            )
            return None

    def get_timezone_for_area(self, area: str) -> str:
        """Get timezone for the given AEMO area.

        All AEMO regions operate in Australian Eastern Time, but we map each
        region to its capital city timezone for accuracy.

        Args:
            area: Area code (NSW1, QLD1, etc.)

        Returns:
            Timezone string (e.g. "Australia/Sydney")
        """
        timezone_map = {
            "NSW1": "Australia/Sydney",  # New South Wales
            "QLD1": "Australia/Brisbane",  # Queensland
            "SA1": "Australia/Adelaide",  # South Australia
            "TAS1": "Australia/Hobart",  # Tasmania
            "VIC1": "Australia/Melbourne",  # Victoria
        }

        return timezone_map.get(area, "Australia/Sydney")

    def get_parser_for_area(self, area: str):
        """Get parser for the given area.

        Args:
            area: Area code

        Returns:
            AemoParser instance
        """
        from .parsers.aemo_parser import AemoParser

        return AemoParser(timezone_service=self.timezone_service)
