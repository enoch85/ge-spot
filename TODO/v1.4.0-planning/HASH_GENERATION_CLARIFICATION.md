# Hash Generation Timing: When Does Config Hash Get Created?

**Date:** October 11, 2025  
**Context:** User question about config hash generation timing in v1.4.0

---

## Your Question

> "So only on the reload we generate a new hash? Do we also generate a new hash when we get new prices?"

---

## Short Answer

**Hash is generated EVERY TIME we save processed data to cache.**

This happens in TWO scenarios:
1. ✅ **After API fetch** - New prices fetched from API → processed → hash calculated → saved to cache
2. ✅ **After config reload** - Cached raw data → reprocessed with new config → **new hash** calculated → saved to cache

**NOT generated:**
- ❌ When retrieving from cache (hash is already there, just compared)
- ❌ During sensor updates (uses cached data, compares hash but doesn't regenerate)

---

## Current Code (v1.3.4) - NO HASH YET

**Currently, there is NO config hash in the code!**

This is what we're **implementing** in v1.4.0.

**Current behavior:**
```python
# unified_price_manager.py (line 673)
self._cache_manager.store(
    data=processed_data,  # ← No hash in here!
    area=self.area,
    source=processed_data.get("data_source", "unknown"),
    timestamp=now
)

# What's stored currently:
{
    "interval_prices": {...},
    "statistics": {...},
    "raw_interval_prices_original": {...},  # Added recently
    "source_timezone": "Europe/Stockholm",
    "source_currency": "SEK"
    # ← NO processing_config_hash!
}
```

**Problem:** Config changes don't trigger reprocessing because we don't know if processed data is stale.

---

## Proposed Code (v1.4.0) - WITH HASH

### When Hash Is Generated

Hash is calculated and stored **every time we process data**, regardless of source:

```python
# data_processor.py (NEW METHOD - to be added)
def _calculate_processing_config_hash(self) -> str:
    """Calculate hash of processing configuration.
    
    Returns:
        MD5 hash of VAT + currency + display_unit + precision
    """
    import hashlib
    
    config_string = (
        f"{self.vat_rate}|"
        f"{self.target_currency}|"
        f"{self.display_unit}|"
        f"{self.precision}"
    )
    
    return hashlib.md5(config_string.encode()).hexdigest()
```

### Scenario 1: Fresh API Fetch (New Prices)

**Flow:**
```
1. API fetch returns raw data
2. Parser extracts interval_raw + timezone + currency
3. DataProcessor.process() normalizes and converts
4. Calculate hash from CURRENT config
5. Add hash to processed_data
6. Store to cache
```

**Code:**
```python
# data_processor.py process() method (MODIFIED - to be added)
async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
    # ... existing normalization and conversion ...
    
    # Build result
    processed_result = {
        "interval_prices": final_today_prices,
        "statistics": stats,
        "raw_interval_prices_original": input_interval_raw,
        "source_timezone": input_source_timezone,
        "source_currency": input_source_currency,
        
        # NEW: Add config hash
        "processing_config_hash": self._calculate_processing_config_hash()  # ← GENERATES HASH
    }
    
    return processed_result

# unified_price_manager.py (line 673) - UNCHANGED
self._cache_manager.store(
    data=processed_data,  # ← Now has hash!
    area=self.area,
    source=processed_data.get("data_source", "unknown"),
    timestamp=now
)
```

**Result in cache:**
```python
{
    "interval_prices": {"00:00": 0.50, "00:15": 0.52, ...},
    "statistics": {...},
    "raw_interval_prices_original": {...},
    "source_timezone": "Europe/Stockholm",
    "source_currency": "SEK",
    "processing_config_hash": "a1b2c3d4"  # ← NEW! Hash of VAT=25%, SEK, decimal, 3
}
```

### Scenario 2: Config Reload (User Changes VAT)

**User action:**
```yaml
# User changes in HA UI:
VAT: 25% → 0%
```

**Flow:**
```
1. Config change triggers reload
2. New coordinator created with VAT=0%
3. New DataProcessor with vat_rate=0.0
4. Sensor update triggered
5. Retrieve cache → detect hash mismatch
6. Reprocess from raw_interval_prices_original
7. Calculate hash from NEW config (VAT=0%)
8. Store updated processed data with NEW hash
```

**Code:**
```python
# cache_manager.py get_data() (MODIFIED - to be added)
def get_data(self, area: str, target_date: date = None) -> Optional[Dict[str, Any]]:
    """Get cached data with config hash validation."""
    data = self._price_cache.get(cache_key)
    
    if data:
        # Check if processed data is stale
        cached_config_hash = data.get("processing_config_hash")
        current_config_hash = self._manager._data_processor._calculate_processing_config_hash()
        
        if cached_config_hash != current_config_hash:
            _LOGGER.info(
                f"Config changed (cached hash: {cached_config_hash}, current: {current_config_hash}). "
                f"Reprocessing from raw data."
            )
            
            # Reprocess from cached raw data
            reprocessed_data = await self._manager._data_processor.process({
                "raw_interval_prices_original": data["raw_interval_prices_original"],
                "source_timezone": data["source_timezone"],
                "source_currency": data["source_currency"],
                "using_cached_data": True,
                "data_source": data.get("source", "unknown")
            })
            
            # NEW HASH calculated here! ↑
            # reprocessed_data["processing_config_hash"] = "def456"  (VAT=0%)
            
            # Update cache with reprocessed data
            self._price_cache.set(cache_key, reprocessed_data)
            
            return reprocessed_data
        
        # Hash matches - use processed data as-is
        return data
```

**Result:**
```python
# BEFORE reprocessing (cached data):
{
    "interval_prices": {"00:00": 0.625, ...},  # With 25% VAT
    "processing_config_hash": "a1b2c3d4"       # VAT=25%
}

# AFTER reprocessing:
{
    "interval_prices": {"00:00": 0.50, ...},   # With 0% VAT (recalculated!)
    "processing_config_hash": "def456"         # VAT=0% (NEW HASH!)
}
```

---

## Timeline Examples

### Example 1: Normal Operation (No Config Changes)

```
13:00 - API fetch
      - process() calculates hash: "abc123" (VAT=25%)
      - Stores to cache with hash
      
13:10 - Sensor update
      - Retrieve cache
      - Compare: cached="abc123" vs current="abc123" ✓ MATCH
      - Use processed data (no hash regeneration)
      
13:20 - Sensor update
      - Retrieve cache
      - Compare: cached="abc123" vs current="abc123" ✓ MATCH
      - Use processed data (no hash regeneration)
      
14:00 - API fetch (new prices)
      - process() calculates hash: "abc123" (VAT still 25%)
      - Stores to cache with hash (SAME hash, NEW prices)
```

**Hash regenerated:** 2 times (once per API fetch)  
**Hash compared:** Every sensor update (~360 times/hour)

### Example 2: Config Change Mid-Cycle

```
13:00 - API fetch
      - process() calculates hash: "abc123" (VAT=25%)
      - Stores to cache
      
13:10 - Sensor update
      - Compare: "abc123" vs "abc123" ✓ MATCH
      - Use processed data
      
13:15 - USER CHANGES VAT TO 0%
      - Config reload
      - New DataProcessor with vat_rate=0.0
      
13:16 - Sensor update (first after reload)
      - Retrieve cache
      - Compare: cached="abc123" vs current="def456" ✗ MISMATCH
      - Reprocess from raw_interval_prices_original
      - process() calculates NEW hash: "def456" (VAT=0%)
      - Update cache with new processed data + new hash
      
13:20 - Sensor update
      - Compare: "def456" vs "def456" ✓ MATCH
      - Use processed data (no reprocessing)
      
14:00 - API fetch (new prices)
      - process() calculates hash: "def456" (VAT still 0%)
      - Stores to cache
```

**Hash regenerated:** 3 times (2× API fetch + 1× reprocessing after config change)  
**Hash compared:** Every sensor update

### Example 3: Multiple Config Changes

```
13:00 - API fetch, hash="abc123" (VAT=25%, SEK, decimal)
13:15 - User changes VAT to 0%
      - Next sensor update: hash="def456" (VAT=0%, SEK, decimal)
      
13:20 - User changes display_unit to cents
      - Next sensor update: hash="xyz789" (VAT=0%, SEK, cents)
      
13:25 - User changes currency to EUR
      - Next sensor update: hash="111222" (VAT=0%, EUR, cents)
      
14:00 - API fetch
      - process() calculates hash="111222" (same config)
      - Stores with current config hash
```

**Hash regenerated:** 5 times (1× initial fetch + 3× config changes + 1× new fetch)

---

## Summary Table

| Event | Hash Generated? | Hash Value | When |
|-------|----------------|------------|------|
| **API fetch (new prices)** | ✅ YES | Current config | During `process()` |
| **Config reload** | ❌ NO* | - | On reload |
| **First sensor update after reload** | ✅ YES** | New config | During reprocessing |
| **Subsequent sensor updates** | ❌ NO | - | Just compared |
| **Cache retrieval** | ❌ NO | - | Just compared |

\* Config reload itself doesn't generate hash  
\** Reprocessing after config change generates new hash

---

## Key Points

1. **Hash is calculated during processing, not during reload**
   - Reload creates new DataProcessor with new config
   - Hash calculation happens when that new processor processes data

2. **Hash is stored WITH processed data**
   - Every cache entry has its own hash
   - Hash represents the config used to create that processed data

3. **Hash comparison happens on EVERY retrieval**
   - Fast operation (string comparison)
   - Triggers reprocessing if mismatch detected

4. **New prices get current config hash**
   - API fetch → process() → calculate hash from current config
   - Even if config didn't change, hash is recalculated (same value)

5. **Reprocessing generates new hash**
   - When config changes detected
   - Reprocess from raw → calculate NEW hash → update cache

---

## Options Flow Integration

### How Config Changes Trigger Hash Regeneration

**File:** `config_flow/options.py`

**Flow:**
```python
# Line 117: User submits options form
if not self._errors:
    # Update entry data with new config
    self.hass.config_entries.async_update_entry(entry, data=updated_data)
    
    # Return creates the options entry
    return self.async_create_entry(title="", data=user_input)
```

**This triggers update_listener:**
```python
# __init__.py (line 104)
async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
    # ↑ Reloads entire integration
```

**What happens on reload:**
```
1. async_unload_entry() - Cleanup old coordinator
2. async_setup_entry() - Create NEW coordinator
   - New UnifiedPriceManager
   - New DataProcessor with NEW config (VAT=0%)
   - New hash calculation method with NEW values
3. First coordinator.async_refresh()
   - Retrieves cache
   - Detects hash mismatch
   - Reprocesses from raw data
   - Calculates NEW hash
   - Updates cache
```

**Result:**
- Config reload creates NEW processor instance
- New processor has NEW config values
- Hash calculation uses NEW values
- First data processing after reload generates NEW hash

---

## Comparison: Current vs Proposed

### Current (v1.3.4)
```python
# NO hash validation
def get_data(self, area: str) -> Optional[Dict[str, Any]]:
    data = self._price_cache.get(cache_key)
    return data  # Returns whatever is cached
```

**Problem:**
```
13:00 - Fetch with VAT=25% → Cache: prices with 25% VAT
13:15 - User changes VAT to 0%
13:16 - Sensor update → Returns CACHED data with 25% VAT ❌ WRONG!
13:20 - Sensor update → Still showing 25% VAT ❌ WRONG!
14:00 - Next fetch → Finally shows 0% VAT ✓ (but 45 minutes of wrong data!)
```

### Proposed (v1.4.0)
```python
# WITH hash validation
def get_data(self, area: str) -> Optional[Dict[str, Any]]:
    data = self._price_cache.get(cache_key)
    
    if data:
        cached_hash = data.get("processing_config_hash")
        current_hash = self._manager._data_processor._calculate_processing_config_hash()
        
        if cached_hash != current_hash:
            # Reprocess from raw data
            reprocessed = await self._manager._data_processor.process(...)
            self._price_cache.set(cache_key, reprocessed)
            return reprocessed
    
    return data
```

**Fixed:**
```
13:00 - Fetch with VAT=25% → Cache: prices + hash="abc123"
13:15 - User changes VAT to 0% → Config reload
13:16 - Sensor update
      - Compare: "abc123" (cached) vs "def456" (current) → MISMATCH
      - Reprocess from raw data with VAT=0%
      - New hash="def456"
      - Update cache
      - Return CORRECT prices with 0% VAT ✓
13:20 - Sensor update → Correct prices (hash matches) ✓
14:00 - Next fetch → Correct prices (hash still matches) ✓
```

---

## Conclusion

**Hash is generated every time we PROCESS data:**
- ✅ After API fetch (new prices)
- ✅ After reprocessing (config change detected)

**Hash is NOT regenerated when:**
- ❌ Just retrieving from cache
- ❌ During sensor updates (unless reprocessing needed)
- ❌ During config reload itself (reload creates NEW processor, hash generated on first use)

**Think of it this way:**
- **Hash = fingerprint of the config used to create processed data**
- Every time we create processed data → new fingerprint
- Every time we retrieve → check if fingerprint still valid
- Fingerprint changed → recreate processed data with new fingerprint
