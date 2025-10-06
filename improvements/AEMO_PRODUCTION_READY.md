# AEMO Integration - Production Ready

**Status:** ✅ Complete and tested  
**Date:** October 6, 2025  
**Branch:** parser-improvements

## Summary

The AEMO (Australian Energy Market Operator) integration has been refactored to follow the standard parser/API pattern and now successfully provides 30-minute trading interval forecasts from NEMWEB Pre-dispatch Reports.

## What Changed

### Before (Broken)
- Used AEMO visualization API endpoint
- Returned only 1/96 intervals
- Statistics calculations failed
- Integration was non-functional for Australian users

### After (Working)
- Uses NEMWEB Pre-dispatch Reports
- Returns 52+ trading intervals (30-min granularity)
- Expanded to 104+ 15-min intervals by DataProcessor
- Full 24-hour coverage with 40+ hour forecast horizon
- Follows standard BasePriceParser pattern

## Files

### Production Files
- **API:** `custom_components/ge_spot/api/aemo.py` (243 lines)
- **Parser:** `custom_components/ge_spot/api/parsers/aemo_parser.py` (251 lines)
- **Utilities:** `custom_components/ge_spot/utils/zip_utils.py` (70 lines)

### Tests
- **Unit Tests:** `tests/pytest/unit/test_aemo_parser.py` (11 tests, all passing)
- **Integration Test:** `tests/manual/api/test_aemo_live.py` (live NEMWEB data, passing)

## Technical Details

### Data Source
- **URL:** http://www.nemweb.com.au/Reports/Current/PredispatchIS_Reports/
- **Format:** ZIP (~850KB) containing CSV (~8MB)
- **Update Frequency:** Every 30 minutes
- **Coverage:** ~52 trading intervals (30-min), 40+ hour horizon
- **Regions:** NSW1, QLD1, SA1, TAS1, VIC1

### Data Flow
```
NEMWEB Server
  ↓ (HTML directory listing)
Latest ZIP file discovery
  ↓ (Download ~850KB)
ZIP extraction
  ↓ (Unzip to ~8MB CSV)
AemoParser.parse()
  ↓ (Extract 30-min intervals)
interval_raw (ISO timestamps)
  ↓ (Returned to coordinator)
DataProcessor
  ↓ (interval_expander: 30min → 15min)
104+ 15-minute intervals
  ↓
Sensors updated
```

### Architecture Pattern

Follows the standard pattern used by Nordpool, ENTSO-E, etc.:

**API Client (aemo.py):**
- Extends `BasePriceAPI`
- Fetches raw data from NEMWEB
- Returns structured dict with `csv_content`, `area`, `timezone`, `currency`, `raw_data`

**Parser (aemo_parser.py):**
- Extends `BasePriceParser`
- Parses CSV content to extract 30-min intervals
- Returns dict with `interval_raw` (ISO timestamps), metadata
- Source interval marked as 30 minutes

**DataProcessor:**
- Uses `interval_expander.convert_to_target_intervals()`
- Expands 30-min → 15-min (duplicates each value twice)
- Normalizes to Home Assistant timezone
- Calculates statistics

## Test Results

### Unit Tests
```
11 tests passed:
✓ Parse NSW1 data
✓ Parse QLD1 data  
✓ Invalid region handling
✓ Missing CSV content handling
✓ Missing area handling
✓ Datetime parsing (valid)
✓ Datetime parsing (invalid)
✓ Header extraction
✓ Header not found
✓ CSV parsing directly
✓ Empty result structure
```

### Integration Test (Live NEMWEB)
```
✓ API fetch successful
  - CSV size: 7,945,248 characters
  - Timezone: Australia/Sydney
  - Currency: AUD

✓ Parser successful
  - Intervals parsed: 52
  - Source interval: 30 minutes

✓ Price statistics
  - Minimum: $-12.00/MWh
  - Maximum: $299.99/MWh
  - Average: $92.80/MWh
  - Range: Within AEMO typical bounds

✓ Metadata validation
  - Source: aemo
  - Area: NSW1
  - Timezone: Australia/Sydney
  - Currency: AUD
  - Source unit: MWh
```

## Performance

- **Download size:** ~850KB per fetch
- **CSV size:** ~8MB decompressed (in memory)
- **Parse time:** <1 second
- **Total fetch time:** ~2-3 seconds
- **Recommended cache TTL:** 15 minutes (aligns with data updates)

## Regional Timezone Mapping

```python
NSW1 → Australia/Sydney
QLD1 → Australia/Brisbane
SA1  → Australia/Adelaide
TAS1 → Australia/Hobart
VIC1 → Australia/Melbourne
```

## Production Checklist

- [x] Code follows standard parser/API pattern
- [x] All unit tests passing (11/11)
- [x] Integration test with live data passing
- [x] Error handling implemented
- [x] Logging appropriate
- [x] Documentation updated
- [x] Old backup files removed
- [x] CSV parsing handles AEMO format correctly
- [x] Timezone handling correct for all regions
- [x] Price validation working
- [x] Interval expansion working (30min → 15min)

## Next Steps

1. **Merge to main:** Code is production ready
2. **User testing:** Australian users validate real-world usage
3. **Monitor:** Check logs for any edge cases in production
4. **Future:** Consider caching ZIP file to reduce downloads

## Notes

- AEMO uses 30-minute trading intervals (not 5-minute or hourly)
- Pre-dispatch forecasts are official AEMO dispatch forecasts
- Prices can go negative and spike to $16,600/MWh (market design)
- Files update every 30 minutes with rolling forecast
- Each file contains ~52 intervals spanning 40+ hours

---

**Ready for production deployment** ✅
