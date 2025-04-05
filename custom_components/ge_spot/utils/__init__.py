"""Utility functions for GE-Spot integration."""

# Currency utilities
from .currency_utils import (
    get_default_currency,
    convert_to_subunit,
    get_subunit_name,
    format_price,
    convert_energy_price,
    async_convert_energy_price,
    REGION_TO_CURRENCY,
    CURRENCY_SUBUNIT_MULTIPLIER,
    CURRENCY_SUBUNIT_NAMES,
    ENERGY_UNIT_CONVERSION,
)

# Timezone utilities
from .timezone_utils import (
    ensure_timezone_aware,
    process_price_data,
    find_current_price,
    find_current_price_period,
    parse_datetime,
    localize_datetime,
    convert_to_local_time,
    get_local_now,
    get_prices_for_day,
    get_raw_prices_for_day,
    get_price_list,
    get_statistics,
    is_tomorrow_valid,
)

# API client and validation
from .api_client import ApiClient, ApiFallbackManager
from .api_validator import ApiValidator

# Debug utilities
from .debug_utils import log_conversion, log_raw_data, log_statistics

# Error handling
from .error_handler import (
    retry_async,
    APIError,
    RateLimitError,
    AuthenticationError,
    DataParsingError,
    handle_api_errors,
)

# Exchange service
from .exchange_service import ExchangeRateService, get_exchange_service

# Form helper
from .form_helper import FormHelper

# Price processing
from .price_processor import PriceProcessor, process_nordpool_data
from .price_utils import find_extrema_with_timestamps, get_price_statistics
