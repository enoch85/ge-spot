# Complete Attribute Comparison: Used vs Cached vs Hashed vs Validated

## Quick Reference Table

| Attribute | Type | Used in Processing? | Affects Output? | Stored in Cache? | In Hash? | Validated? | Notes |
|-----------|------|-------------------|-----------------|------------------|----------|------------|-------|
| **target_currency** | Config | ✅ Yes | ✅ Price values | ✅ Yes | ✅ Yes | ✅ Via hash | EUR, SEK, etc. |
| **vat_rate** | Config | ✅ Yes | ✅ Price values | ✅ Yes | ✅ Yes | ✅ Via hash | 0.25 = 25% |
| **include_vat** | Config | ✅ Yes | ✅ Price values | ✅ Yes | ✅ Yes | ✅ Via hash | Boolean |
| **display_unit** | Config | ✅ Yes | ✅ Price values | ✅ Yes | ✅ Yes | ✅ Via hash | kWh/MWh/cents |
| **use_subunit** | Derived | ✅ Yes | ✅ Formatting | ❌ No | ✅ Via display_unit | ✅ Via display_unit | Auto from display_unit |
| **precision** | Config | ✅ Yes | ✅ Decimal places | ❌ Implicit | ✅ Yes | ✅ Via hash | 2 = 2 decimals |
| **target_timezone** | TZ Service | ✅ Yes | ✅ Interval keys | ✅ Yes | ✅ Yes | ✅ Via hash | **FIXED v1.4.0** |
| **area** | Config | ❌ No | ❌ Metadata only | ✅ Yes | ❌ No | ✅ Date check | SE3, DK1, etc. |
| **source** | Runtime | ❌ No | ❌ Metadata only | ✅ Yes | ❌ No | ❌ No | nordpool, entsoe |
| **source_timezone** | API | ✅ Yes | ✅ Normalization | ✅ Yes | ❌ No | ✅ Presence check | Input timezone |
| **source_currency** | API | ✅ Yes | ✅ Conversion | ✅ Yes | ❌ No | ✅ Presence check | Input currency |
| **source_unit** | API | ✅ Yes | ✅ Conversion | ✅ Yes | ❌ No | ❌ No | MWh, kWh |

## Detailed Breakdown

### 1. Configuration Attributes (User-Controlled)

These are set by the user in Home Assistant configuration:

```python
# From config_flow or YAML
config = {
    "vat": 25.0,                    # ✅ In hash
    "include_vat": True,            # ✅ In hash
    "display_unit": "cents",        # ✅ In hash
    "precision": 2,                 # ✅ In hash
}
area = "SE3"                        # ❌ Not in hash (metadata)
target_currency = "SEK"             # ✅ In hash
target_timezone = "Europe/Stockholm" # ✅ In hash (v1.4.0)
```

**Why these are in hash:**
- Changes to any of these require reprocessing price data
- Different values produce different output
- Cache from old config would be incorrect with new config

**Why area is NOT in hash:**
- Area doesn't affect HOW data is processed, only WHAT data to fetch
- Same raw data processed with same config = same output regardless of area
- Area validated indirectly via date check (today's intervals for this area)

### 2. Runtime Attributes (API-Provided)

These come from the API response:

```python
# From API response
api_data = {
    "source_timezone": "Europe/Oslo",   # ❌ Not in hash (input, not config)
    "source_currency": "NOK",           # ❌ Not in hash (input, not config)
    "source_unit": "MWh",              # ❌ Not in hash (input, not config)
}
```

**Why these are NOT in hash:**
- These are INPUT attributes, not CONFIGURATION attributes
- Hash is for "did user change their preferences"
- These change based on which API succeeded, not user choice
- Validated by presence check instead

### 3. Derived Attributes

These are calculated from other attributes:

```python
# Derived in __init__
self.use_subunit = self.display_unit == DisplayUnit.CENTS  # ✅ Covered by display_unit
```

**Why derived attributes are NOT explicitly in hash:**
- They're deterministic from other attributes already in hash
- Including them would be redundant
- Changes to parent attribute automatically invalidate hash

## Processing Pipeline Attribute Usage

### Step 1: Timezone Normalization
```python
# Uses:
- source_timezone      # From API (input)
- target_timezone      # From config (✅ IN HASH)

# Output:
- Interval keys in HH:MM format in target timezone
```

### Step 2: Currency Conversion
```python
# Uses:
- source_currency      # From API (input)
- target_currency      # From config (✅ IN HASH)
- vat_rate            # From config (✅ IN HASH)
- include_vat         # From config (✅ IN HASH)

# Output:
- Prices in target currency with/without VAT
```

### Step 3: Unit Conversion
```python
# Uses:
- source_unit          # From API (input)
- display_unit         # From config (✅ IN HASH)
- use_subunit         # Derived from display_unit (✅ IN HASH)

# Output:
- Prices in kWh/MWh/cents as configured
```

### Step 4: Precision/Rounding
```python
# Uses:
- precision           # From config (✅ IN HASH)

# Output:
- Rounded to specified decimal places
```

## Cache Validation Logic

### Level 1: Format Check
```python
# Checks:
- interval_prices exists and non-empty ✅
- Keys are HH:MM format (not ISO) ✅
- statistics exists ✅
- target_timezone exists ✅
```

### Level 2: Config Hash Check
```python
# Compares:
current_hash = f"{currency}_{vat_rate}_{include_vat}_{display_unit}_{precision}_{timezone}"
cached_hash = data.get("processing_config_hash")

if current_hash != cached_hash:
    return False  # Config changed, must reprocess ✅
```

### Level 3: Raw Data Check
```python
# Verifies we can reprocess if needed:
- raw_interval_prices_original exists ✅
- source_timezone exists ✅
- source_currency exists ✅
```

### Level 4: Freshness Check
```python
# Verifies data is current:
- interval_prices contains today's intervals ✅
- At least 80% of expected intervals present ✅
```

## Hash Component Justification

Each component in the hash affects output:

| Hash Component | Example Values | Why It's Needed |
|----------------|---------------|-----------------|
| `target_currency` | SEK, EUR, NOK | Different currency = different price values |
| `vat_rate` | 0.25, 0.20, 0.0 | Different VAT = different price values |
| `include_vat` | True, False | With/without VAT = different price values |
| `display_unit` | kWh, MWh, cents | Different unit = different price values |
| `precision` | 2, 3, 4 | Different rounding = different price values |
| `target_timezone` | Europe/Stockholm, Europe/Oslo | Different timezone = different interval keys |

## Example: Why Timezone Matters

### Scenario: User Changes Timezone

**Before timezone in hash (BUG):**
```python
# Cache created with Europe/Stockholm
cache = {
    "interval_prices": {
        "13:00": 100.0,  # 13:00 Stockholm time
        "14:00": 150.0   # 14:00 Stockholm time
    },
    "processing_config_hash": "abc123"  # WITHOUT timezone
}

# User changes HA to Europe/Oslo (+1 hour)
# Hash calculation: "abc123" (SAME! timezone not included)
# Validation: PASSES (hash matches) ❌ BUG!
# Result: Uses cache with wrong timezone
# Impact: interval_prices keys are 1 hour off
```

**After timezone in hash (FIXED):**
```python
# Cache created with Europe/Stockholm
cache = {
    "interval_prices": {
        "13:00": 100.0,
        "14:00": 150.0
    },
    "processing_config_hash": "abc123_Europe/Stockholm"
}

# User changes HA to Europe/Oslo
# Hash calculation: "def456_Europe/Oslo" (DIFFERENT!)
# Validation: FAILS (hash mismatch) ✅ CORRECT!
# Result: Reprocesses from raw data with new timezone
# Impact: interval_prices get correct keys for new timezone
```

## Testing Coverage

### Hash Change Tests (9 total)
1. ✅ test_hash_changes_with_currency
2. ✅ test_hash_changes_with_vat_rate
3. ✅ test_hash_changes_with_include_vat
4. ✅ test_hash_changes_with_display_unit
5. ✅ test_hash_changes_with_precision
6. ✅ test_hash_changes_with_timezone (NEW v1.4.0)
7. ✅ test_hash_is_deterministic
8. ✅ test_hash_length
9. ✅ test_hash_is_hexadecimal

### Validation Tests (13 total)
1. ✅ test_valid_processed_data
2. ✅ test_invalid_hash_mismatch
3. ✅ test_invalid_missing_interval_prices
4. ✅ test_invalid_missing_statistics
5. ✅ test_invalid_missing_target_timezone
6. ✅ test_invalid_raw_format_iso_timestamps
7. ✅ test_invalid_empty_interval_prices
8. ✅ test_invalid_missing_hash
9. ✅ test_invalid_missing_raw_data (NEW v1.4.0)
10. ✅ test_invalid_missing_source_timezone (NEW v1.4.0)
11. ✅ test_invalid_missing_source_currency (NEW v1.4.0)
12. ✅ test_invalid_stale_data_from_yesterday (NEW v1.4.0)
13. ✅ test_invalid_incomplete_today_data (NEW v1.4.0)

### Fast-Path Tests (5 total)
1. ✅ test_updates_current_and_next_prices
2. ✅ test_updates_interval_keys
3. ✅ test_sets_using_cached_data_flag
4. ✅ test_updates_last_update_timestamp
5. ✅ test_fallback_to_tomorrow_prices

### Collision Tests (2 total)
1. ✅ test_hash_space_is_large_enough
2. ✅ test_different_configs_produce_different_hashes

**Total: 29 tests, all passing ✅**

## Conclusion

The hash now includes **exactly** what it should:
- ✅ All user configuration that affects processing
- ✅ All derived values are covered by their source
- ✅ All processing steps validated
- ❌ No redundant or unnecessary attributes

Cache validation is **comprehensive**:
- ✅ Format correctness
- ✅ Configuration match (via hash)
- ✅ Raw data availability
- ✅ Data freshness
- ✅ Data completeness

**The system is now robust against all known edge cases.**
