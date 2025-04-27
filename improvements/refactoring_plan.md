# Refactoring Plan for GE-Spot Integration Codebase

## Key Issues in the Current Implementation

- **Duplicated Logic Across APIs:** Each regional API (Nordpool, ENTSO-E, EPEX, etc.) has its own nearly identical code for fetching and processing prices. For example, the Nordpool module defines `fetch_day_ahead_prices`, `_fetch_data`, and `_process_data` routines that mirror those in other API modules ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=async%20def%20fetch_day_ahead_prices,currency%2C%20reference_time%3DNone%2C%20hass%3DNone%2C%20session%3DNone)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=async%20def%20fetch_day_ahead_prices,currency%2C%20reference_time%3DNone%2C%20hass%3DNone%2C%20session%3DNone)) ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=async%20def%20_fetch_data,reference_time)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=async%20def%20_fetch_data,reference_time)). This repetition leads to inconsistent function naming and harder maintenance.  
- **Broken Fallback Handling:** The multi-source fallback system is not working as intended. The code uses a complex `FallbackManager` and adapter mechanism to try alternate sources ([[ge-spot/custom_components/ge_spot/coordinator/today_data_manager.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/coordinator/today_data_manager.py#:~:text=,API%20fetches%20with%20automatic%20fallbacks)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/coordinator/today_data_manager.py#:~:text=,API%20fetches%20with%20automatic%20fallbacks)), but in practice failures in the primary API often do **not** result in using the backup API. The fallback chain logic (e.g. Nordpool -> EDS -> ENTSO-E) defined in the design ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=Each%20region%20has%20a%20defined,chain%20based%20on%20data%20compatibility)](https://github.com/enoch85/ge-spot#:~:text=Each%20region%20has%20a%20defined,chain%20based%20on%20data%20compatibility)) isn’t reliably executed due to scattered logic between the coordinator and data managers.  
- **Non-Functioning Rate Limiter:** Although the integration advertises a minimum 15-minute update interval to respect API limits ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=sources%20fail%20,around%2013%3A00%20CET)](https://github.com/enoch85/ge-spot#:~:text=sources%20fail%20,around%2013%3A00%20CET)), the current scheduling doesn’t properly enforce this. The default update interval is set to 30 minutes ([[ge-spot/custom_components/ge_spot/const/defaults.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/const/defaults.py#:~:text=UPDATE_INTERVAL%20%3D%2030%20)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/const/defaults.py#:~:text=UPDATE_INTERVAL%20%3D%2030%20)), but there’s no active mechanism preventing more frequent calls (especially during fallback retries or manual refreshes). The special logic for “publication times” (around 13:00 CET) is either not implemented or not functioning, leading to potential API overuse.  
- **Timezone Mismatch & Multiple Conversions:** Timezone handling is inconsistent – timestamps are converted multiple times in different places. Each API parser normalizes times to either the area’s timezone or Home Assistant’s timezone using a `TimezoneService` ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=,specific%20timezone)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=,specific%20timezone)) ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=,parse%20hourly%20prices)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=,parse%20hourly%20prices)), but additional conversions or mis-aligned timezone info can occur when merging data from different sources. This can lead to hour offsets or DST errors. The intended design is to normalize once and have consistent hourly alignment ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=1,DST%20transitions%20are%20handled%20automatically)](https://github.com/enoch85/ge-spot#:~:text=1,DST%20transitions%20are%20handled%20automatically)), but the current code sometimes applies timezone shifts more than once or uses the wrong timezone reference (area vs HA).  
- **Currency Conversion Inconsistencies:** The integration is supposed to convert currencies once using fresh ECB exchange rates ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=GE,and%20reliable)](https://github.com/enoch85/ge-spot#:~:text=GE,and%20reliable)), but currently currency/unit conversions happen in each API module separately. For instance, the Nordpool parser converts every hourly price from EUR/MWh to the target currency and unit inside its loop ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=for%20hour_str%2C%20price%20in%20converted_hourly_prices)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=for%20hour_str%2C%20price%20in%20converted_hourly_prices)). If fallback sources provide data in different currencies, the code might convert each source’s data independently, risking double conversion or using slightly different rates. The currency metadata and conversion application are not uniform across sources, causing potential mismatches in final price outputs.  
- **Inconsistent Data Structures and Metadata:** Each API’s result includes slightly different keys/structure. Nordpool adds `raw_prices` and a `raw_values` breakdown for current/next hour ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=current_hour_key%20%3D%20tz_service)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=current_hour_key%20%3D%20tz_service)) ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=result%5B)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=result%5B)), while Stromligning includes detailed tax/tariff breakdowns ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=,total)](https://github.com/enoch85/ge-spot#:~:text=,total)). These inconsistencies make it hard to handle the data uniformly and complicate debugging. The code uses adapters to homogenize data, but the keys (`data_source`, `api_timezone`, etc.) are not standardized cleanly across all paths.  
- **Scattered, Difficult-to-Debug Logic:** The flow for fetching and updating data is split across multiple layers (coordinator, today/tomorrow managers, fallback manager, individual API modules, exchange service, etc.). This fragmentation means the overall process is hard to trace. For example, the coordinator calls a TodayDataManager, which in turn uses `FallbackManager.fetch_with_fallbacks()` and then a DataProcessor, etc., with data passed through several transformations ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=flowchart%20TD%20Config%5BUser%20Configuration%5D%20,Coordinator)](https://github.com/enoch85/ge-spot#:~:text=flowchart%20TD%20Config%5BUser%20Configuration%5D%20,Coordinator)) ([[ge-spot/custom_components/ge_spot/coordinator/today_data_manager.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/coordinator/today_data_manager.py#:~:text=result%20%3D%20await%20fallback_mgr)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/coordinator/today_data_manager.py#:~:text=result%20%3D%20await%20fallback_mgr)). Logging is sparse in some paths, making it challenging to pinpoint where a failure or incorrect transformation occurs.

## Stage 1: Immediate Fixes to Restore Functionality

**Goal:** Address the most critical issues first – fix broken fallback logic and enforce basic rate limiting. These changes will improve reliability and prevent API lockouts, getting the integration back to a working state quickly.

- **Simplify Fallback Execution:** Replace or patch the complex fallback mechanism with a straightforward implementation. For now, implement a sequential try/except loop over the region’s priority sources (as defined in the fallback chain) ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=Each%20region%20has%20a%20defined,chain%20based%20on%20data%20compatibility)](https://github.com/enoch85/ge-spot#:~:text=Each%20region%20has%20a%20defined,chain%20based%20on%20data%20compatibility)). If the primary API call fails or returns no data, move to the next source, and so on. This ensures alternate APIs are actually tried on failure. In code, this can mean calling each source’s `fetch_day_ahead_prices` in order and breaking as soon as one returns valid data. This direct approach will bypass the broken `FallbackManager` logic ([[ge-spot/custom_components/ge_spot/coordinator/today_data_manager.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/coordinator/today_data_manager.py#:~:text=,API%20fetches%20with%20automatic%20fallbacks)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/coordinator/today_data_manager.py#:~:text=,API%20fetches%20with%20automatic%20fallbacks)) until a more robust solution is in place. Log each fallback attempt for clarity (e.g. “Primary source X failed, trying fallback Y”) to aid debugging.  
- **Use Last Known Data if All Sources Fail:** As a temporary measure, if **all** sources in the chain fail, use the cached last successful data (if available) as the result ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=Priority%20,Cache)](https://github.com/enoch85/ge-spot#:~:text=Priority%20,Cache)) ([[ge-spot/custom_components/ge_spot/coordinator/region.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/coordinator/region.py#:~:text=,data%20as%20fallback)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/coordinator/region.py#:~:text=,data%20as%20fallback)). The code already intends to cache data, but ensure that the fallback to cache is executed. This prevents complete outages in case of widespread API issues. Also log a warning when using cached data (`using_cached_data = True`).  
- **Enforce Minimum Update Interval:** Immediately ensure that updates do not occur more often than the recommended limit. Adjust the coordinator’s update trigger to a fixed 15 minute minimum (or the default 30 minutes) and disable any logic that might cause rapid re-fetching. For example, if the integration currently calls updates on Home Assistant startup **and** on config entry load, remove redundant triggers so only the scheduled interval triggers fetches. Confirm that `Defaults.UPDATE_INTERVAL` is respected ([[ge-spot/custom_components/ge_spot/const/defaults.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/const/defaults.py#:~:text=UPDATE_INTERVAL%20%3D%2030%20)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/const/defaults.py#:~:text=UPDATE_INTERVAL%20%3D%2030%20)). If users try to manually refresh or multiple fallbacks happen in quick succession, introduce a short delay or simply let the single scheduled update handle data refresh. This protects against API rate-limit bans.  
- **Quick Patch Timezone/Currency Double Application:** While a full fix will come later, check for any obvious double-conversion happening now. For instance, if the coordinator or sensor code is again converting timestamps or prices after the API module already did, disable one of them. A common quick fix is to ensure each hourly timestamp is marked with timezone info once and not converted again when setting the sensor state. Similarly, ensure VAT or currency isn’t accidentally applied twice (e.g., if Stromligning’s prices include VAT, avoid re-applying VAT). These interim fixes will correct the most glaring data errors until a proper redesign.  
- **Log and Monitor:** Increase logging in this stage to observe the behavior of fallback and rate limiting. For every update cycle, log which source was used and note if fallback was needed (e.g., `attempted_sources` and `fallback_source_used`). This will verify that our immediate fixes are working (e.g., we should see logs when an alternate API is successfully used). Also log the update frequency to ensure the 15 min interval is honored.

## Stage 2: Unify and Clean Up the Data Fetching Structure

**Goal:** Refactor the code to remove duplication and create a uniform pipeline for all sources. This stage focuses on reorganizing the code without changing external behavior (aside from the fixes in Stage 1), making it easier to maintain and extend.

- **Introduce a Common API Interface:** Create a standardized interface (or base class) for all price source adapters. For example, define an abstract class or protocol with methods like `fetch_data(area)`, `parse_data(raw_response)`, and `format_data(parsed, target_currency, tz)`. Each source-specific module can implement this interface, but share as much logic as possible. This allows the coordinator to call all sources in a generic way (e.g., iterate through a list of source adapter instances). It also standardizes function names (eliminating the current mix of `fetch_day_ahead_prices` functions with slightly different internal workings). The result is cleaner code and consistent behavior for each source.  
- **Consolidate Duplicated Code:** Identify common operations in the API modules and move them to shared utilities. For instance, generating date ranges, building the result dictionary structure, and computing summary statistics (average, peak, off-peak prices) are currently repeated in each module. These can be moved into a helper function or a base adapter class method (e.g., a generic `_process_data` that all sources use, perhaps with hooks for source-specific quirks). As evidence, both Nordpool and ENTSO-E modules perform similar steps: fetch raw data, parse to hourly prices, normalize timezone, then calculate current/next hour and stats ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=client%20%3D%20ApiClient)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=client%20%3D%20ApiClient)) ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=)). By refactoring, the core logic (normalizing times, computing current/next hour keys, etc.) will live in one place, reducing errors and inconsistencies.  
- **Standardize Naming and Constants:** During the refactor, establish consistent naming for keys and constants across the integration. For example, use one constant source of truth for the names of data fields like `"hourly_prices"`, `"current_price"`, `"data_source"`, etc., rather than hardcoding them in each module. This could mean introducing a `DATA_KEYS` or using existing config constants for these fields. Likewise, unify function names (all source adapters might have a `fetch()` method) and class names (ensure naming like `NordpoolAdapter`, `EntsoeAdapter` for clarity). Consistent naming will make the code self-explanatory and avoid confusion (e.g., earlier one part of code referred to “source_type” vs another “adapter”).  
- **Uniform Error Handling & Retries:** Along with unified fetch logic, implement a single error-handling strategy. Instead of each API module handling its own exceptions, have the common pipeline catch exceptions and decide retries or fallback. For example, a **single** rate-limit backoff logic can be applied if any fetch raises an HTTP 429 or similar (ensuring we don’t bombard the next fallback API immediately). This ties in with Stage 1 changes, but here we formalize it: the unified fetch function can incorporate exponential backoff or skipping to next source on known failure modes. This makes the fallback system more robust and easier to debug (one place to see how all errors are handled).  
- **Preserve Raw Data for Debugging:** As part of the unified structure, ensure that each adapter returns not only the final processed data but also raw or intermediate data for inspection. For instance, keep the raw API response or parsed values in a structured form (as already done with `raw_prices` in Nordpool’s result ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=))). The unified data format can include a section for `raw_data` or attach original currency and unit before conversion. This preservation is important for verifying correctness and will be used in Stage 3 to ensure conversions happen once.  
- **Simplify Fallback Mechanism:** With all sources following the same interface, the fallback logic can be greatly simplified. We can now maintain a simple ordered list or map of region -> [preferred_source, fallback1, fallback2, …]. The RegionPriceCoordinator (or the new unified manager) simply iterates through this list calling the adapter’s `fetch()` until data is obtained. This replaces the previous intricate `FallbackManager` with straightforward code, which is easier to test and reason about. The outcome should still populate which source succeeded and which were attempted (for transparency in sensor attributes, e.g., list of `attempted_sources`). By the end of Stage 2, the code will be cleaner: one central loop handling all sources, instead of duplicated loops hidden in each module.

*Outcome of Stage 2:* The integration code will have a cleaner architecture with minimal duplication. All APIs are accessed through a uniform mechanism, which lays the groundwork for tackling the remaining issues (timezone and currency handling) in a consistent way.

## Stage 3: Centralize Timezone and Currency Conversion Logic

**Goal:** Perform time normalization and currency/unit conversion in one place for each data update, rather than scattered across modules. This ensures consistency and that these transformations happen only **once** per data set.

- **Single Timezone Normalization Step:** Move timezone conversion out of individual API parsers into the coordinator (or a dedicated Timezone handler). In the new flow, each source adapter should return timestamps in a known format (ideally with timezone info from the source, or naive UTC). The coordinator can then take the chosen source’s data and normalize all timestamps to the target timezone (Home Assistant’s local zone or the area’s local zone, per user setting) in one batch. This would use the existing `TimezoneService` logic but apply it globally. For example, instead of each parser calling `tz_service.normalize_hourly_prices()` separately ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=,parse%20hourly%20prices)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=,parse%20hourly%20prices)), the coordinator would call it once on the final combined hourly list. This guarantees that DST and hour alignment is handled uniformly for all sources, fulfilling the design goal that “the price for 14:00 is the same regardless of which API provided it” ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=1,DST%20transitions%20are%20handled%20automatically)](https://github.com/enoch85/ge-spot#:~:text=1,DST%20transitions%20are%20handled%20automatically)).  
- **One-Time Currency Conversion:** Similarly, refactor so that currency conversion is done only once per update. The idea is to gather prices in a base currency/unit, then convert to the desired currency **after** selecting/combining the data. For example, always parse source data in its native currency (EUR for Nordpool/ENTSO-E, DKK for Stromligning, etc.) and in a base unit (e.g. EUR/MWh or local currency/MWh). Tag this in the data (like `result["currency"]= "EUR"` as already done ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=if%20result%3A)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=if%20result%3A))). Once the final price list is ready in consistent units, call a central conversion function *one time* to convert all values to the user’s chosen currency and kWh (or subunit) scale. This could produce a new list/dict of converted prices and apply VAT if needed. By doing it in one shot, we ensure all hours use the same exchange rate snapshot and avoid repetitive calls. It also prevents scenarios of double conversion. For instance, if Stromligning is in DKK and the user wants EUR, currently the Stromligning parser likely converts to EUR internally and then perhaps the coordinator might treat it as if it were base and convert again – the new approach will avoid that by clarifying what is base vs target currency at each step.  
- **Use Real-time ECB Rates Correctly:** Ensure the exchange rate service is integrated so that the conversion step uses the cached real ECB rate only **once** per update. The `ExchangeService` can fetch and cache rates (already set up to update every 6 hours) ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=,cents%2FkWh%2C%20%C3%B6re%2FkWh)](https://github.com/enoch85/ge-spot#:~:text=,cents%2FkWh%2C%20%C3%B6re%2FkWh)). The coordinator should retrieve the needed rate (e.g., EUR->SEK) from it and apply to all prices in the batch conversion. Remove any ad-hoc currency conversion code from individual adapters (e.g., the calls to `async_convert_energy_price` inside each loop ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=for%20hour_str%2C%20price%20in%20converted_hourly_prices)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=for%20hour_str%2C%20price%20in%20converted_hourly_prices)) can be dropped in favor of one call that handles a list or vectorized conversion). By centralizing this, we also avoid each source needlessly instantiating HTTP sessions to contact the ECB – one service handles it with proper caching and fallback to last known rates ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=,cents%2FkWh%2C%20%C3%B6re%2FkWh)](https://github.com/enoch85/ge-spot#:~:text=,cents%2FkWh%2C%20%C3%B6re%2FkWh)).  
- **Preserve Raw Prices and Metadata:** Even after moving conversion out, continue to store the raw prices and original currency for reference. For example, the result structure can include `raw_prices` (in original currency) and `converted_prices` (in target currency). This was partly in place (Nordpool’s `raw_values` stores original vs final for current/next hour ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=result%5B)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=result%5B)) ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=result%5B)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=result%5B))). We will extend that approach uniformly: every price point could carry `{original_value, original_unit, converted_value, final_unit}` in the attributes. This makes validation easier – we can always check the conversion against the raw data.  
- **Handle Complex Tariffs Consistently:** For sources like Stromligning that provide breakdown of components (energy, grid, taxes) ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=,total)](https://github.com/enoch85/ge-spot#:~:text=,total)), decide on a consistent strategy. The refactoring should clarify whether we only take the raw energy price to match others (as is done now for DK1/DK2) or if we also want to present full price. In either case, isolate that logic in the Stromligning adapter’s parse step (to choose what raw price to output), then let the general conversion routine handle it like any other price. By standardizing output (just a price per hour, regardless of components), the subsequent timezone and currency steps remain uniform. We can still attach the full breakdown in attributes for transparency, but the conversion of each component should happen only once as well (e.g., convert total price and/or each component once and store).  
- **Verify Hour Alignment and Correctness:** After implementing centralized time and currency conversion, rigorously test that the hours line up and values match expectations. For example, verify that for a given known dataset (say Nordpool vs ENTSO-E for the same area/day), the final `hourly_prices` dictionary has the same timestamps and that if the raw data was identical, the converted results are identical too. This will prove that no extra shifts or conversions are creeping in. Also test DST transition days to ensure the normalization covers 25h/23h days properly (the TimezoneService should handle it, but now we can test it in one place).  

By the end of Stage 3, the system will use a **single pass** for timezone normalization and currency conversion, improving consistency. The data flow will be: fetch raw -> parse to standard format (with original tz/currency) -> normalize times -> convert currency/units -> output. This eliminates the previous multiple conversion points and fixes timezone mismatches.

## Stage 4: Improve Testing, Logging, and Validation

**Goal:** Now that the code is reorganized and cleaned up, strengthen the integration’s reliability with better tests and debugging tools. This stage ensures the refactored system works as intended and remains stable.

- **Unit Tests for Each Source Adapter:** Develop unit tests for each API adapter’s parsing logic. Using saved sample responses (from Nordpool, ENTSO-E, Stromligning, etc.), test that the adapter returns the expected structured output (raw hourly prices, with correct times and values before conversion). Also test edge cases, like missing data or API errors (simulate an empty or error response and ensure the adapter raises an exception or returns None appropriately). These tests will catch any parsing inconsistencies early, and protect against future regressions when APIs change format.  
- **Integration Tests for Fallback Logic:** Write tests for the fallback chain using a dummy set of adapters. For example, create fake adapter classes for “PrimaryAPI” and “FallbackAPI” where the primary fails and fallback returns data. Test that the RegionPriceCoordinator correctly picks up fallback data and labels it accordingly (e.g., result’s `source` field is “FallbackAPI” and `fallback_sources` includes “PrimaryAPI”). Also test the scenario where primary succeeds and fallback is not called (to ensure no unnecessary actions happen). If possible, simulate the cache usage: have all sources fail and verify cached data is returned with `using_cached_data` flagged. These tests will confirm that the Stage 1 and Stage 2 logic for fallbacks is solid.  
- **Validate Timezone Alignment:** Create a test for timezone handling: Feed the system two sets of data for the same hours, one in UTC and one in a different timezone (say CET), and ensure that after normalization they align to the same Home Assistant local time hours. For example, if one source provides 13:00 UTC and another 14:00 CET for the same actual hour, after normalization to HA time both should map to the same hour key. This could be done by injecting known timezone info and checking the coordinator’s merged output. This validates the Stage 3 implementation.  
- **Cross-Verify Currency Conversion:** Write a test that forces a known exchange rate (perhaps by monkeypatching the ExchangeService to return a fixed rate) and then check that converting a known price yields the expected result. For instance, if rate EUR->SEK is set to 10.0 and VAT 0%, then an input of 0.05 EUR/kWh should convert to 0.50 SEK/kWh. This can test the conversion pipeline end-to-end. Also ensure that if user’s desired currency equals source currency, the conversion leaves the value unchanged (aside from unit conversion MWh->kWh and VAT). This prevents scenarios where conversion logic might erroneously apply a rate of 1 or apply VAT twice.  
- **End-to-End Integration Test:** In a Home Assistant test environment (if available), load the integration with a specific region known for having multiple sources (e.g., Denmark, which can use Nordpool, EDS, Stromligning). Simulate a full update cycle and verify the state and attributes of the created sensors. The attributes should include `source` (showing which API was ultimately used), `attempted_sources`, `fallback_sources` (if any) ([[ge-spot/custom_components/ge_spot/coordinator/region.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/coordinator/region.py#:~:text=)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/coordinator/region.py#:~:text=)) ([[ge-spot/custom_components/ge_spot/coordinator/region.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/coordinator/region.py#:~:text=,available)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/coordinator/region.py#:~:text=,available)), and the pricing information. Check that the current price, next hour price, average, etc., are all populated correctly and correspond to the raw data from the chosen source. This high-level test ensures the entire refactored integration works in concert.  
- **Enhanced Logging and Documentation:** Finally, improve the logging messages and developer documentation to aid future debugging. Ensure that whenever a fallback happens or a conversion is done, a log entry notes it (without flooding normal operation logs excessively). Document the new architecture in the README “For Developers” section, explaining the data flow and where each piece (timezone normalization, conversion, caching) occurs. This helps new contributors or maintainers understand the now-cleaner logic.  

By executing Stage 4, we will have high confidence in the refactored integration. The combination of unit and integration tests will catch errors, and the clearer logs will make any future issue easier to diagnose. With these stages completed, GE-Spot’s energy price data integration will be far more maintainable and reliable, providing accurate hourly prices with robust fallback and consistent conversions as originally intended. 

**Sources:**

- GE-Spot README – *Features and Technical Details (Fallbacks, Rate Limiting, Timezone, Currency)* ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=sources%20fail%20,around%2013%3A00%20CET)](https://github.com/enoch85/ge-spot#:~:text=sources%20fail%20,around%2013%3A00%20CET)) ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=GE,and%20reliable)](https://github.com/enoch85/ge-spot#:~:text=GE,and%20reliable))  
- GE-Spot Code Snippets – *Nordpool API implementation and data processing* ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=async%20def%20fetch_day_ahead_prices,currency%2C%20reference_time%3DNone%2C%20hass%3DNone%2C%20session%3DNone)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=async%20def%20fetch_day_ahead_prices,currency%2C%20reference_time%3DNone%2C%20hass%3DNone%2C%20session%3DNone)) ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=for%20hour_str%2C%20price%20in%20converted_hourly_prices)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=for%20hour_str%2C%20price%20in%20converted_hourly_prices)); *Fallback manager usage* ([[ge-spot/custom_components/ge_spot/coordinator/today_data_manager.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/coordinator/today_data_manager.py#:~:text=,API%20fetches%20with%20automatic%20fallbacks)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/coordinator/today_data_manager.py#:~:text=,API%20fetches%20with%20automatic%20fallbacks)); *Timezone normalization logic* ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=1,DST%20transitions%20are%20handled%20automatically)](https://github.com/enoch85/ge-spot#:~:text=1,DST%20transitions%20are%20handled%20automatically)) ([[ge-spot/custom_components/ge_spot/api/nordpool.py at main · enoch85/ge-spot · GitHub](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=,parse%20hourly%20prices)](https://github.com/enoch85/ge-spot/blob/main/custom_components/ge_spot/api/nordpool.py#:~:text=,parse%20hourly%20prices)); *Example of Stromligning data structure* ([[GitHub - enoch85/ge-spot: Global Energy Spotprices](https://github.com/enoch85/ge-spot#:~:text=,total)](https://github.com/enoch85/ge-spot#:~:text=,total)).



2025-04-27:

🔄 Revised Stage 2: Dynamic Adapter Registration
1. Adapter Self-Registration via Decorator

Each API adapter lives in its own module and decorates itself with the metadata the system needs (its name, supported regions, default priority in the fallback chain).

# custom_components/ge_spot/api/nordpool.py

from ..core import register_adapter
from .base import BaseAPIAdapter

@register_adapter(
    name="nordpool",
    regions=["SE1","SE2","DK1","DK2"],
    default_priority=10
)
class NordpoolAdapter(BaseAPIAdapter):
    ...

    register_adapter is a tiny decorator (≈ 20 lines) that simply records the class in a global registry dict under the hood.

    No more manual import lists—just dropping a new *.py adapter in the package automatically makes it available.

2. Config-Driven Fallback Chains

Rather than hard-coding the full chain in code, each region’s fallback order lives in its own small YAML/JSON under config/regions/SE1.yaml, for example:

# config/regions/SE1.yaml
fallback_chain:
  - nordpool
  - entsoe
  - epex

    A ~5-line loader reads config/regions/{region}.yaml to get the ordered list of adapter names.

    The fallback loop simply does:

    adapters = [registry[name] for name in chain]
    for adapter in adapters:
        try: return adapter.fetch_data(...)
        except: continue

3. Tiny Central Registry Module

Your core registry file now looks like:

# custom_components/ge_spot/api/registry.py
import pkgutil, importlib, yaml
from pathlib import Path

ADAPTERS = {}

def register_adapter(name, regions, default_priority):
    def deco(cls):
        ADAPTERS[name] = cls
        cls._regions = regions
        cls._priority = default_priority
        return cls
    return deco

def get_chain_for_region(region: str) -> list[str]:
    cfg = yaml.safe_load(Path(__file__).parent.parent.parent / f"config/regions/{region}.yaml")
    return cfg["fallback_chain"]

    Size: ~30 lines, independent of how many adapters you have.

    Extensible: New adapters = new modules + a line in config; no central file bloat.

4. Benefits Over the Monolith

    Modularity: Each adapter is self-contained; removing or adding one never touches a central registry list.

    Clarity: Fallback priority is explicit in small per-region files, not buried in thousands of lines.

    Testability: You can unit-test each adapter and separately test the loader that builds the chain from YAML.

    Performance: Dynamic discovery at startup is negligible; the runtime fallback loop is just iterating a small list.

▶️ Next Steps

    Implement the register_adapter decorator and move all existing adapters to use it.

    Extract fallback chains into per-region YAML under config/regions/.

    Replace any hard-coded source maps in your UnifiedPriceManager with calls to registry.get_chain_for_region().

    Remove any massive, monolithic registry file you drafted earlier.

    Add lightweight unit tests for:

        Decorator registration

        Config loader correctness

        Fallback loop behavior with mocks

        (Remaining adapter and conversion tests, as before)

This way, the “registry” grows automatically with your code, yet stays tiny, readable, and fully under your control. Let me know if you’d like snippets to kick-start the decorator and the YAML loader!

# How to implement

1. Create the Registry and Decorator

File: custom_components/ge_spot/api/registry.py
Purpose: Collects adapters via decorator, loads per-region fallback chains from YAML, and builds adapter instances on demand.

# custom_components/ge_spot/api/registry.py

import yaml
from pathlib import Path
from typing import Type, List

# Global mapping: adapter_name -> Adapter class
ADAPTERS: dict[str, Type["BaseAPIAdapter"]] = {}


def register_adapter(
    name: str,
    regions: List[str],
    default_priority: int = 0
):
    """
    Decorator to register an adapter class under a given name,
    and annotate which regions it supports.
    """
    def decorator(cls: Type["BaseAPIAdapter"]) -> Type["BaseAPIAdapter"]:
        cls.adapter_name = name
        cls.supported_regions = regions
        cls.default_priority = default_priority
        ADAPTERS[name] = cls
        return cls
    return decorator


def get_chain_for_region(region: str) -> List[str]:
    """
    Load the fallback_chain for a region from
    custom_components/ge_spot/config/regions/{region}.yaml
    """
    cfg_path = Path(__file__).parent.parent.parent / "config" / "regions" / f"{region}.yaml"
    data = yaml.safe_load(cfg_path.read_text())
    return data.get("fallback_chain", [])


def create_adapters_for_region(
    region: str,
    **adapter_kwargs,
) -> List["BaseAPIAdapter"]:
    """
    Instantiates adapters in the order defined by the region's YAML.
    Unrecognized adapter names are skipped.
    """
    chain = get_chain_for_region(region)
    instances: List["BaseAPIAdapter"] = []
    for name in chain:
        AdapterCls = ADAPTERS.get(name)
        if AdapterCls:
            instances.append(AdapterCls(**adapter_kwargs))
    return instances

2. Define Your Base Adapter

If you don’t already have it, add:

File: custom_components/ge_spot/api/base_adapter.py

# custom_components/ge_spot/api/base_adapter.py

from abc import ABC, abstractmethod

class BaseAPIAdapter(ABC):
    @abstractmethod
    def fetch_data(self, area: str) -> dict:
        """
        Must return raw API data in a standard dict format:
        {
          "hourly_raw":    { "2025-04-27T00:00:00+02:00": 10.5, ... },
          "timezone":      "Europe/Stockholm",
          "currency":      "EUR",
          "source_name":   "nordpool",
          ...
        }
        """
        pass

3. Turn Each Adapter into a Self-Registering Class

For every adapter module under custom_components/ge_spot/api/, wrap its class with @register_adapter. Keep the existing logic intact.
Example: nordpool.py

# custom_components/ge_spot/api/nordpool.py

from .base_adapter import BaseAPIAdapter
from .registry import register_adapter
import httpx
from datetime import datetime, timedelta
from ..utils import parse_nordpool_response  # your existing parser

@register_adapter(
    name="nordpool",
    regions=["SE1","SE2","NO1","DK1","DK2"],
    default_priority=10
)
class NordpoolAdapter(BaseAPIAdapter):
    def __init__(self, session: httpx.AsyncClient):
        self.session = session

    async def fetch_data(self, area: str) -> dict:
        # (keep all your existing HTTP calls + parsing logic)
        resp = await self.session.get(f"https://api.nordpoolgroup.com/.../{area}")
        data = parse_nordpool_response(resp.json())
        return {
            "hourly_raw": data["prices"],
            "timezone": data["tz"],
            "currency": data["currency"],
            "source_name": "nordpool",
        }

Example: entsoe.py

# custom_components/ge_spot/api/entsoe.py

from .base_adapter import BaseAPIAdapter
from .registry import register_adapter
import httpx
from .parsers import parse_entsoe

@register_adapter(
    name="entsoe",
    regions=["DE","FR","PL","CZ"],
    default_priority=20
)
class EntsoeAdapter(BaseAPIAdapter):
    def __init__(self, session: httpx.AsyncClient, api_key: str):
        self.session = session
        self.api_key = api_key

    async def fetch_data(self, area: str) -> dict:
        # (existing logic to build URL, call entsoe, parse)
        url = f"https://api.entsoe.eu/...?area={area}&token={self.api_key}"
        resp = await self.session.get(url)
        data = parse_entsoe(resp.text)
        return {
            "hourly_raw": data["prices"],
            "timezone": data["tz"],
            "currency": data["currency"],
            "source_name": "entsoe",
        }

    You will repeat this pattern in every adapter module:

        Import register_adapter and BaseAPIAdapter.

        Apply the decorator with your adapter’s name, supported regions & priority.

        Leave your existing fetch_data logic untouched.

4. Add Per-Region Fallback Config

Create a small YAML file for each region under:

ge-spot/
├── custom_components/ge_spot/config/regions/SE1.yaml
├── custom_components/ge_spot/config/regions/SE2.yaml
└── ...

Example: SE1.yaml

fallback_chain:
  - nordpool
  - entsoe
  - epex

You only list the adapter names exactly as used in the @register_adapter(name=…).
5. Wire It Up in Your Coordinator

In your UnifiedPriceManager (or wherever you fetch per region), replace manual maps with:

# custom_components/ge_spot/coordinator/unified_price_manager.py

from ..api.registry import create_adapters_for_region
from ..utils.cache import CacheManager
from ..utils.rate_limiter import RateLimiter
from ..coordinator.data_processor import DataProcessor

class UnifiedPriceManager:
    def __init__(self, session, config):
        self.session = session
        self.config = config
        self.cache = CacheManager()
        self.data_processor = DataProcessor(...)
        self._last_fetch = {}

    async def fetch_data(self, region: str) -> dict:
        # 1. Rate-limit guard
        if not RateLimiter.allow(region, self._last_fetch.get(region)):
            return self.cache.get(region)

        # 2. Build adapters in fallback order
        adapters = create_adapters_for_region(
            region,
            session=self.session,
            api_key=self.config.get("entsoe_api_key", ""),
        )

        # 3. Try each in turn
        raw_result = None
        attempted = []
        for adapter in adapters:
            attempted.append(adapter.adapter_name)
            try:
                raw_result = await adapter.fetch_data(region)
                break
            except Exception as e:
                # log and continue
                continue

        # 4. Fallback to cache if all failed
        if raw_result is None:
            return self.cache.get(region)

        # 5. Process, cache & return
        final = self.data_processor.process(raw_result, region)
        self.cache.set(region, final)
        self._last_fetch[region] = RateLimiter.current_time()
        final["attempted_sources"] = attempted
        final["data_source"] = raw_result["source_name"]
        return final

6. Clean Up Old Code

    Delete any “manual map” of source_type→class you had in UnifiedPriceManager.

    Remove the old monolithic registry file (if you created one).

    Prune unused helpers under utils/fallback or utils/rate_limiter once you’ve standardized on your chosen approach.

✅ Summary of Changes

    api/registry.py – ~30 lines, dynamic decorator + YAML loader.

    api/base_adapter.py – abstract base for all adapters.

    Adapter Modules (nordpool.py, entsoe.py, etc.) – add @register_adapter(...) at the top.

    Region Configs (config/regions/*.yaml) – tiny lists of adapter names per region.

    Coordinator – create_adapters_for_region(), sequential try/except, rate-limiter & cache fallback.

    Cleanup – remove any leftover monoliths or duplicated code.

This delivers the full implementation in small, maintainable pieces, auto-growing as you add more adapters, without any thousand-line files. Let me know if you’d like clarification on any particular snippet!