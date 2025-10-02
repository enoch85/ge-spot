# Data Validity Architecture - Proposal

## Problem Statement

Currently, the system tracks whether we have "complete_data" (80%+ of intervals), but this doesn't answer the critical question:

**"How far into the future do we have valid price data?"**

This leads to:
- ❌ Unnecessary fetches when we already have future data
- ❌ Confusing terminology ("complete_data" vs "data_valid_until")
- ❌ Rate limiting issues when data is incomplete but still usable
- ❌ No clear understanding of when the next fetch is actually needed

## Desired Behavior

**Goal: Only fetch 2 times per day**

1. **13:00 daily** - Fetch tomorrow's 96 intervals
   - Data valid until: Tomorrow 23:45 (next day at 00:00)
   - This gives us ~35 hours of future data

2. **Midnight safety fetch (optional)** - Only if we missed yesterday's 13:00 fetch
   - Check if we have data for current day
   - If not, fetch today's data

3. **No other fetches needed** - We always have future data

## New Architecture

### 1. Data Validity Tracking

Instead of `complete_data: bool`, track:

```python
@dataclass
class DataValidity:
    """Track how far into the future we have valid data."""
    
    # The last interval timestamp we have data for
    last_valid_interval: datetime  # e.g., "2025-10-03 23:45:00+02:00"
    
    # When our data coverage runs out
    data_valid_until: datetime  # Same as last_valid_interval
    
    # How many intervals we have
    interval_count: int  # e.g., 192 (today + tomorrow)
    
    # Whether we have enough data for current operations
    has_current_interval: bool  # Do we have data for RIGHT NOW?
    
    # Whether we have the minimum needed data (e.g., rest of today)
    has_minimum_data: bool  # At least current hour to end of day?
```

### 2. Fetch Decision Logic

```python
def should_fetch(
    self,
    now: datetime,
    data_validity: DataValidity,
    safety_buffer_hours: int = 2
) -> Tuple[bool, str]:
    """Decide if we need to fetch based on data validity.
    
    Args:
        now: Current time
        data_validity: Information about data coverage
        safety_buffer_hours: How many hours ahead we want to maintain
        
    Returns:
        (should_fetch, reason)
    """
    
    # CRITICAL: Do we have data for right now?
    if not data_validity.has_current_interval:
        return True, "No data for current interval - URGENT FETCH"
    
    # Calculate when we'll run out of data
    hours_of_data_remaining = (data_validity.data_valid_until - now).total_seconds() / 3600
    
    # Are we within the safety buffer?
    if hours_of_data_remaining < safety_buffer_hours:
        return True, f"Only {hours_of_data_remaining:.1f} hours of data left (safety buffer: {safety_buffer_hours}h)"
    
    # Check if we're in a special fetch window (13:00-14:00)
    if 13 <= now.hour < 14:
        # Only fetch if we DON'T have tomorrow's complete data
        tomorrow = now.date() + timedelta(days=1)
        tomorrow_end = datetime.combine(tomorrow, time(23, 45))
        
        if data_validity.data_valid_until < tomorrow_end:
            return True, "Special fetch window (13:00-14:00) and missing tomorrow's data"
    
    # We have enough data
    return False, f"Data valid until {data_validity.data_valid_until}, {hours_of_data_remaining:.1f} hours remaining"
```

### 3. Storage Changes

Store validity metadata with each cache entry:

```python
def store(self, area: str, source: str, data: Dict[str, Any], timestamp: datetime) -> None:
    """Store data with validity tracking."""
    
    # Calculate validity from the data itself
    validity = self._calculate_data_validity(data, timestamp)
    
    metadata = {
        "area": area,
        "source": source,
        "stored_at": timestamp.isoformat(),
        "data_valid_until": validity.data_valid_until.isoformat(),
        "last_valid_interval": validity.last_valid_interval.isoformat(),
        "interval_count": validity.interval_count,
        "has_current_interval": validity.has_current_interval,
    }
    
    # Store with metadata
    cache_key = self._generate_cache_key(area, source, timestamp.date())
    self._price_cache.set(cache_key, data, metadata=metadata)
```

### 4. Retrieval Changes

When getting data from cache, return validity info:

```python
def get_data_with_validity(
    self, 
    area: str, 
    now: datetime
) -> Tuple[Optional[Dict], Optional[DataValidity]]:
    """Get data and its validity information.
    
    Returns:
        (data_dict, validity_info) or (None, None) if no valid data
    """
    
    # Look for cache entries that cover the current time
    entries = self._find_entries_covering(area, now)
    
    if not entries:
        return None, None
    
    # Get most recent entry
    entry = entries[0]
    data = entry["data"]
    metadata = entry["metadata"]
    
    # Reconstruct validity from metadata
    validity = DataValidity(
        last_valid_interval=dt_util.parse_datetime(metadata["last_valid_interval"]),
        data_valid_until=dt_util.parse_datetime(metadata["data_valid_until"]),
        interval_count=metadata["interval_count"],
        has_current_interval=metadata["has_current_interval"],
        has_minimum_data=True  # If we found it, it has minimum data
    )
    
    return data, validity
```

## Migration Path

### Phase 1: Add Parallel Tracking (No Breaking Changes)
1. Add `DataValidity` class
2. Calculate validity alongside existing `complete_data`
3. Log both values for comparison
4. Keep existing logic working

### Phase 2: Switch Fetch Decision
1. Update `FetchDecisionMaker` to use `DataValidity`
2. Keep `complete_data` calculation for backward compatibility
3. Test thoroughly

### Phase 3: Remove Old Logic
1. Remove `complete_data` boolean
2. Remove 80% threshold logic
3. Update all references

## Expected Outcomes

### Before (Current State)
```
13:00 - Fetch (complete_data=False, need data)
13:15 - Skip (complete_data=True, have 80%)
14:00 - Skip (complete_data=True)
15:00 - Skip (complete_data=True)
...
00:00 - Fetch (complete_data=False, midnight transition)
01:00 - Skip (complete_data=True)
```
Result: 2 fetches per day ✅ BUT with confusing logic

### After (New Architecture)
```
13:00 - Fetch (data_valid_until=2025-10-03 23:45, need tomorrow)
13:15 - Skip (data valid for 34.5 hours)
14:00 - Skip (data valid for 33.5 hours)
...
23:00 - Skip (data valid for 11.0 hours)
00:00 - Skip (data valid for 23.75 hours) ✅ No midnight fetch needed!
01:00 - Skip (data valid for 22.75 hours)
...
11:00 - Skip (data valid for 2.75 hours)
12:00 - Skip (data valid for 1.75 hours)
13:00 - Fetch (data valid for 0.75 hours, within 2h safety buffer)
```
Result: 1 fetch per day ✅ with clear, understandable logic

## Benefits

1. ✅ **Clear terminology**: "data_valid_until" is self-explanatory
2. ✅ **Fewer fetches**: No unnecessary midnight fetches
3. ✅ **Graceful degradation**: Can use partial data when rate limited
4. ✅ **Safety buffer**: Configurable advance warning before running out
5. ✅ **Easy monitoring**: Can show "X hours of data remaining" to users
6. ✅ **DST handling**: Works naturally with DST transitions

## Implementation Priority

**HIGH PRIORITY:**
- [ ] Create `DataValidity` dataclass
- [ ] Add `_calculate_data_validity()` method
- [ ] Update cache storage to include validity metadata
- [ ] Update fetch decision to use validity checks

**MEDIUM PRIORITY:**
- [ ] Add logging of validity information
- [ ] Add sensor attribute showing "data_valid_until"
- [ ] Update tests

**LOW PRIORITY:**
- [ ] Remove old `complete_data` logic
- [ ] Update documentation

## Questions to Address

1. **What safety buffer?** 
   - Proposed: 2 hours (fetch when < 2 hours remaining)
   - This ensures we fetch around 13:00 when we have ~1.75 hours left

2. **Handle missed fetches?**
   - If 13:00 fetch fails, try again at 14:00, 15:00, etc.
   - Add flag: `fetch_overdue` when past special window but still need data

3. **Rate limiting with validity?**
   - When rate limited, use ANY cached data that covers current time
   - Don't require "complete" or "valid until tomorrow"
   - Graceful degradation!

4. **Midnight transition?**
   - With new logic, NO midnight fetch needed (we have tomorrow's data from 13:00)
   - Migration logic can stay for edge cases

## Example Log Output

### With New Architecture
```
2025-10-02 13:00:15 - INFO - Data validity check: valid until 2025-10-02 14:45 (1.75h remaining)
2025-10-02 13:00:15 - INFO - Safety buffer (2h) triggered - fetching new data
2025-10-02 13:01:30 - INFO - Fetched 192 intervals from Nordpool
2025-10-02 13:01:31 - INFO - Data validity updated: valid until 2025-10-03 23:45 (34.7h remaining)
2025-10-02 13:15:00 - DEBUG - Data validity: valid until 2025-10-03 23:45 (34.5h remaining) - no fetch needed
```

Much clearer than:
```
2025-10-02 13:00:15 - INFO - Complete data: False, fetching
2025-10-02 13:01:31 - INFO - Complete data: True
```
