# Parser and API Updates

## API Standardization (v2.0)

### Overview
All API handlers have been standardized to follow the `BasePriceAPI` abstract class structure. This ensures consistent behavior, error handling, and data formatting across all price sources.

### Updates
- **Stromligning API**: Refactored to inherit from `BasePriceAPI` with standardized methods for fetching and parsing data.
- **ENTSO-E API**: Follows the `BasePriceAPI` structure for consistent implementation.
- **Legacy Support**: Maintained backward compatibility with previous API versions.

### Benefits
- Consistent error handling across all price sources
- Standardized data format for all integrations
- Improved maintainability and extensibility
- Centralized validation logic

### Implementation Details
Each API now implements the following required methods:
- `_get_source_type()`: Returns the source identifier
- `_get_base_url()`: Returns the base URL for API requests
- `fetch_raw_data()`: Fetches raw price data from the source
- `parse_raw_data()`: Converts raw data to standardized format
- `get_timezone_for_area()`: Returns the timezone for a specific area
- `get_parser_for_area()`: Returns the appropriate parser for an area

## Deprecated Components
The `data_fetcher.py` utility has been deprecated in favor of the new standardized approach in `api/base/data_fetch.py`. 