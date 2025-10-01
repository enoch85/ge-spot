# Fact Finding: Hour to 15-Minute Interval Migration

## Overview
Complete analysis of all hour-related code that needs to be changed for 15-minute interval support.

**Date:** October 1, 2025
**Branch:** 15min

---

## Statistics

### Code Impact Analysis
- **"hourly" occurrences in Python files:** 389
- **"hour" occurrences in Python files:** 734+
- **"hour_key/hourly_prices/next_hour" occurrences:** 415
- **Files containing hour-related code:** 40+ files
- **Test files with hourly_prices:** 196 occurrences

### Critical Numbers to Change
- **Current data points per day:** 24 (hourly)
- **Target data points per day:** 96 (15-minute intervals)
- **Current format:** "HH:00"
- **Target format:** "HH:MM" (where MM = 00, 15, 30, 45)

---

## Part 1: Constants & Configuration

### 1.1 Time Constants (const/time.py)
**Current State:**
```python
class TimeInterval:
    HOURLY = "PT60M"           # ISO 8601 duration: 60 minutes
    QUARTER_HOURLY = "PT15M"   # ISO 8601 duration: 15 minutes (already exists!)
    DAILY = "P1D"
    DEFAULT = HOURLY           # ❌ Currently defaults to HOURLY
```

**Changes Needed:**
- ✅ `QUARTER_HOURLY = "PT15M"` already exists
- ❌ Change `DEFAULT = HOURLY` → `DEFAULT = QUARTER_HOURLY`
- ➕ Add new constants:
  - `INTERVAL_MINUTES = 15`
  - `INTERVALS_PER_HOUR = 4`
  - `INTERVALS_PER_DAY = 96`
  - `INTERVALS_PER_DAY_DST_SPRING = 92` (lose 4 intervals)
  - `INTERVALS_PER_DAY_DST_FALL = 100` (gain 4 intervals)

**Generic Naming Strategy:**
```python
class TimeInterval:
    """Time interval constants - easily configurable."""
    # ISO 8601 duration formats
    HOURLY = "PT60M"
    QUARTER_HOURLY = "PT15M"
    DAILY = "P1D"
    
    # Active interval (change this one value to switch globally)
    DEFAULT = QUARTER_HOURLY  # ← Single point of configuration
    
    # Derived constants (auto-calculated from DEFAULT)
    @staticmethod
    def get_interval_minutes():
        """Get interval duration in minutes based on DEFAULT."""
        if TimeInterval.DEFAULT == TimeInterval.QUARTER_HOURLY:
            return 15
        elif TimeInterval.DEFAULT == TimeInterval.HOURLY:
            return 60
        return 15  # fallback
    
    @staticmethod
    def get_intervals_per_hour():
        """Get number of intervals per hour."""
        return 60 // TimeInterval.get_interval_minutes()
    
    @staticmethod
    def get_intervals_per_day():
        """Get number of intervals per day."""
        return 24 * TimeInterval.get_intervals_per_hour()
```

### 1.2 Update Interval (const/defaults.py)
**Current State:**
```python
UPDATE_INTERVAL = 30  # minutes
```

**Changes Needed:**
```python
UPDATE_INTERVAL = 15  # minutes (to match 15-minute intervals)
```

### 1.3 Display Constants (const/display.py)
**Current State:**
```python
class UpdateInterval:
    FIFTEEN_MINUTES = 15  # ✅ Already exists!
    THIRTY_MINUTES = 30
    HOUR = 60
```

**Changes Needed:**
- Keep all options, but change default/recommended to `FIFTEEN_MINUTES`

### 1.4 Source Intervals (const/intervals.py)
**Current State:**
```python
INTERVALS = {
    Source.AEMO: 5,             # Every 5 minutes
    Source.ENTSOE: 360,         # Every 6 hours
    Source.NORDPOOL: 1440,      # Every 24 hours
    # ... other sources
}
DEFAULT_INTERVAL = 1440  # 24 hours
```

**Analysis:**
- These are **API fetch intervals**, NOT price data intervals
- **No change needed** - these control how often we fetch from APIs
- Independent of whether prices are hourly or 15-minute

---

## Part 2: Time Format & Key Generation

### 2.1 Hour Calculator → Interval Calculator
**File:** `timezone/hour_calculator.py` → `timezone/interval_calculator.py`

**Current Key Methods:**
```python
class HourCalculator:
    def get_current_hour_key(self) -> str:
        """Get the current hour formatted as HH:00."""
        # Returns: "14:00", "15:00", etc.
    
    def get_next_hour_key(self) -> str:
        """Get the next hour formatted as HH:00."""
        # Returns next hour
    
    def get_hour_key_for_datetime(self, dt: datetime) -> str:
        """Get the hour key for a specific datetime."""
        # Format: HH:00
```

**Generic Naming Strategy:**
```python
class IntervalCalculator:
    """Calculate interval keys - generic implementation."""
    
    def get_current_interval_key(self) -> str:
        """Get the current interval key formatted as HH:MM."""
        now = dt_util.now(self.timezone)
        rounded = self._round_to_interval(now)
        return f"{rounded.hour:02d}:{rounded.minute:02d}"
    
    def get_next_interval_key(self) -> str:
        """Get the next interval key formatted as HH:MM."""
        now = dt_util.now(self.timezone)
        rounded = self._round_to_interval(now)
        next_interval = rounded + timedelta(minutes=TimeInterval.get_interval_minutes())
        return f"{next_interval.hour:02d}:{next_interval.minute:02d}"
    
    def get_interval_key_for_datetime(self, dt: datetime) -> str:
        """Get the interval key for a specific datetime."""
        rounded = self._round_to_interval(dt)
        return f"{rounded.hour:02d}:{rounded.minute:02d}"
    
    def _round_to_interval(self, dt: datetime) -> datetime:
        """Round datetime to nearest interval boundary."""
        interval_minutes = TimeInterval.get_interval_minutes()
        minute = (dt.minute // interval_minutes) * interval_minutes
        return dt.replace(minute=minute, second=0, microsecond=0)
```

**Imports to Update:**
```python
# OLD:
from .hour_calculator import HourCalculator

# NEW:
from .interval_calculator import IntervalCalculator
```

**Files importing HourCalculator:**
1. `timezone/service.py` - Line 18
2. `timezone/__init__.py` - Line 7

---

## Part 3: Data Structures

### 3.1 Data Classes (api/base/data_structure.py)

**Current State:**
```python
@dataclass
class HourlyPrice:
    """Hourly price data."""
    datetime: str
    price: float
    hour_key: str  # Format: HH:00
    currency: str
    timezone: str
    source: str
    vat_included: bool = False

@dataclass
class StandardizedPriceData:
    """Standardized price data format."""
    source: str
    area: str
    currency: str
    fetched_at: str
    reference_time: Optional[str] = None
    hourly_prices: Dict[str, float] = field(default_factory=dict)  # Key: HH:00
    raw_prices: List[HourlyPrice] = field(default_factory=list)
    current_price: Optional[float] = None
    next_hour_price: Optional[float] = None
    api_timezone: Optional[str] = None
    current_hour_key: Optional[str] = None
    next_hour_key: Optional[str] = None
    # ... more fields
```

**Generic Naming Strategy:**
```python
@dataclass
class IntervalPrice:
    """Price data for a single time interval (generic)."""
    datetime: str
    price: float
    interval_key: str  # Format: HH:MM (e.g., "14:00", "14:15", "14:30", "14:45")
    currency: str
    timezone: str
    source: str
    vat_included: bool = False

@dataclass
class StandardizedPriceData:
    """Standardized price data format."""
    source: str
    area: str
    currency: str
    fetched_at: str
    reference_time: Optional[str] = None
    interval_prices: Dict[str, float] = field(default_factory=dict)  # Key: HH:MM
    raw_prices: List[IntervalPrice] = field(default_factory=list)
    current_price: Optional[float] = None
    next_interval_price: Optional[float] = None
    api_timezone: Optional[str] = None
    current_interval_key: Optional[str] = None
    next_interval_key: Optional[str] = None
    # ... more fields
```

**Usage Pattern:**
- All code references `interval_prices` instead of `hourly_prices`
- Keys are always "HH:MM" format
- Works for any interval duration by changing the constant

---

## Part 4: API Layer - Parser Strategy

### 4.1 ENTSO-E Parser (Already Supports 15-min!)
**File:** `api/parsers/entsoe_parser.py`

**Current Code:**
```python
resolution_preference = ["PT60M", "PT30M", "PT15M"]  # ✅ Already handles PT15M!

if res_text == "PT15M":
    # 15-minute resolution handling already exists
    pass
elif res_text != "PT60M":
    # Other resolutions
    pass
```

**Analysis:**
- ✅ ENTSO-E parser ALREADY supports 15-minute data!
- ✅ Has logic for PT15M resolution
- ✅ Can handle both PT60M and PT15M
- Action: Just need to prioritize PT15M over PT60M

### 4.2 Parser Implementation Strategy

**For each parser, we need to:**

1. **Check if API provides 15-minute data:**
   - ENTSO-E: ✅ YES (already in code)
   - Nord Pool: ✅ LIKELY YES (as of Oct 1, 2025)
   - Others: ❓ Need to check

2. **Implement expansion logic for hourly-only APIs:**

```python
def expand_to_intervals(hourly_data: Dict[str, float]) -> Dict[str, float]:
    """
    Expand hourly prices to match configured interval.
    
    Generic implementation - works for any interval duration.
    If API provides hourly data but we need 15-min intervals,
    duplicate the hourly price across all intervals in that hour.
    """
    interval_minutes = TimeInterval.get_interval_minutes()
    intervals_per_hour = TimeInterval.get_intervals_per_hour()
    
    if interval_minutes == 60:
        # Already hourly, no expansion needed
        return hourly_data
    
    expanded = {}
    for hour_key, price in hourly_data.items():
        # Parse hour from key (e.g., "14:00" → 14)
        hour = int(hour_key.split(':')[0])
        
        # Create interval keys for this hour
        for i in range(intervals_per_hour):
            minute = i * interval_minutes
            interval_key = f"{hour:02d}:{minute:02d}"
            expanded[interval_key] = price
    
    return expanded
```

### 4.3 Parsers to Update

**All parser files in `api/parsers/`:**
1. ✅ `entsoe_parser.py` - Already supports PT15M
2. ❓ `nordpool_parser.py` - Check for 15-min support
3. ❓ `epex_parser.py` - Likely hourly only
4. ❓ `omie_parser.py` - Likely hourly only
5. ❓ `amber_parser.py` - May have 5-min data
6. ❓ `aemo_parser.py` - May have 5-min data
7. ❓ `comed_parser.py` - Likely hourly only
8. ❓ `energi_data_parser.py` - Check for 15-min support
9. ❓ `stromligning_parser.py` - Likely hourly only

**Generic Variable Naming in Parsers:**
```python
# OLD:
raw_hourly = parser.parse_response(response)
hourly_prices = normalize_hourly_prices(raw_hourly)
parsed_data["hourly_prices"] = hourly_prices

# NEW (Generic):
raw_intervals = parser.parse_response(response)
interval_prices = normalize_interval_prices(raw_intervals)
parsed_data["interval_prices"] = interval_prices
```

---

## Part 5: Sensors & Display

### 5.1 Sensor Names & Attributes

**Current State:**
```python
# In sensor/price.py
@property
def next_hour_price(self):
    """Next hour price."""
    return self._data.get("next_hour_price")

# Attributes
"today_with_timestamps": {
    "00:00": 10.5,
    "01:00": 11.2,
    # ... 24 entries total
}
```

**Generic Naming Strategy:**
```python
@property
def next_interval_price(self):
    """Next interval price."""
    return self._data.get("next_interval_price")

# Attributes (automatically adapts to interval)
"today_with_timestamps": {
    "00:00": 10.5,
    "00:15": 10.6,
    "00:30": 10.7,
    "00:45": 10.8,
    "01:00": 11.2,
    # ... 96 entries for 15-min intervals
    # ... or 24 entries for hourly (if reverted)
}
```

### 5.2 Sensor Entity IDs

**Current:**
- `sensor.ge_spot_current_price_se3`
- `sensor.ge_spot_next_hour_price_se3`

**Proposal (Keep backward compatible names):**
- `sensor.ge_spot_current_price_se3` (same - represents current interval)
- `sensor.ge_spot_next_interval_price_se3` (renamed for clarity)

**Alternative (Break compatibility for clarity):**
- Keep: `sensor.ge_spot_current_price_se3`
- Keep: `sensor.ge_spot_next_hour_price_se3` (but it actually shows next 15-min)
- Add note in docs: "next_hour_price" now shows next interval

---

## Part 6: Coordinator & Processing

### 6.1 Data Processor (coordinator/data_processor.py)

**Current Comments:**
```python
# "hourly_prices": {"HH:00" or ISO: price, ...},
# This will convert ISO timestamp keys to 'YYYY-MM-DD HH:00' format
# Calculate price statistics from a dictionary of hourly prices (HH:00 keys)
```

**Generic Update:**
```python
# "interval_prices": {"HH:MM" or ISO: price, ...},
# This will convert ISO timestamp keys to 'YYYY-MM-DD HH:MM' format
# Calculate price statistics from a dictionary of interval prices (HH:MM keys)
```

### 6.2 Statistics Calculation

**Current:** Expects 24 data points
**New:** Expects 96 data points (or configurable based on TimeInterval)

**Generic Implementation:**
```python
def calculate_statistics(interval_prices: Dict[str, float]) -> PriceStatistics:
    """Calculate statistics - works with any number of intervals."""
    if not interval_prices:
        return PriceStatistics(complete_data=False)
    
    prices = list(interval_prices.values())
    
    # Expected intervals per day
    expected_intervals = TimeInterval.get_intervals_per_day()
    
    return PriceStatistics(
        min=min(prices),
        max=max(prices),
        average=sum(prices) / len(prices),
        median=sorted(prices)[len(prices) // 2],
        complete_data=(len(prices) >= expected_intervals * 0.8)  # 80% threshold
    )
```

---

## Part 7: Translation Files

### 7.1 Current Translations (translations/en.json & strings.json)

**Current:**
```json
{
  "timezone_reference": "Choose which timezone to use for displaying hourly prices",
  "update_interval": {
    "60": "1 hour"
  }
}
```

**Generic Update:**
```json
{
  "timezone_reference": "Choose which timezone to use for displaying prices",
  "update_interval": {
    "15": "15 minutes",
    "30": "30 minutes", 
    "60": "1 hour"
  }
}
```

---

## Part 8: Testing

### 8.1 Expected Data Point Changes

**Current Test Expectations:**
```python
# tests/manual/integration/stromligning_full_chain.py
if len(today_prices) == 24:
    logger.info("✓ Complete set of 24 hourly prices for today")

all_hours = set(f"{h:02d}:00" for h in range(24))
```

**Generic Update:**
```python
expected_intervals = TimeInterval.get_intervals_per_day()
if len(today_prices) == expected_intervals:
    logger.info(f"✓ Complete set of {expected_intervals} interval prices for today")

# Generate all expected interval keys
interval_minutes = TimeInterval.get_interval_minutes()
all_intervals = set()
for h in range(24):
    for m in range(0, 60, interval_minutes):
        all_intervals.add(f"{h:02d}:{m:02d}")
```

### 8.2 Test Files to Update

**Integration Tests (tests/pytest/integration/):**
- `test_nordpool_live.py` - 16 references to hourly_prices
- `test_epex_live.py` - 11 references
- `test_entsoe_full_chain.py` - 14 references
- `test_amber_live.py` - 10 references
- `test_energi_data_live.py` - 11 references

**Manual Tests (tests/manual/integration/):**
- All `*_full_chain.py` files need updates

---

## Part 9: Generic Naming Recommendations

### 9.1 Terminology Mapping

| Old (Hour-specific) | New (Generic) | Notes |
|---------------------|---------------|-------|
| `hourly_prices` | `interval_prices` | Generic for any interval |
| `HourlyPrice` | `IntervalPrice` | Class name |
| `hour_key` | `interval_key` | Key format: HH:MM |
| `next_hour_price` | `next_interval_price` | Next interval's price |
| `current_hour_key` | `current_interval_key` | Current interval identifier |
| `HourCalculator` | `IntervalCalculator` | Calculator class |
| `get_current_hour_key()` | `get_current_interval_key()` | Method name |
| `normalize_hourly_prices()` | `normalize_interval_prices()` | Function name |
| `"HH:00"` format | `"HH:MM"` format | Time format |

### 9.2 Configuration-Driven Architecture

**Single Point of Control:**
```python
# const/time.py
class TimeInterval:
    DEFAULT = QUARTER_HOURLY  # ← Change ONLY this to switch interval duration
    
    # Everything else auto-calculates:
    @staticmethod
    def get_interval_minutes() -> int:
        """Get interval duration in minutes."""
        # Returns 15 for QUARTER_HOURLY, 60 for HOURLY
    
    @staticmethod
    def get_intervals_per_day() -> int:
        """Get total intervals per day."""
        # Returns 96 for QUARTER_HOURLY, 24 for HOURLY
```

**Benefits:**
1. ✅ Change ONE constant to switch between 15-min, hourly, or even 5-min
2. ✅ All calculations auto-adjust
3. ✅ Test both modes by changing one value
4. ✅ Future-proof for any interval duration

---

## Part 10: DST Handling

### 10.1 Current DST Logic

**Spring Forward (lose 1 hour):**
- Current: 23 hours in day
- New: 92 intervals in day (23 × 4)

**Fall Back (gain 1 hour):**
- Current: 25 hours in day
- New: 100 intervals in day (25 × 4)

### 10.2 Generic DST Handling

```python
def get_expected_intervals_for_day(date: datetime) -> int:
    """Get expected number of intervals for a specific day."""
    base_intervals = TimeInterval.get_intervals_per_day()
    intervals_per_hour = TimeInterval.get_intervals_per_hour()
    
    if dst_handler.is_spring_forward(date):
        return base_intervals - intervals_per_hour  # Lose one hour's worth
    elif dst_handler.is_fall_back(date):
        return base_intervals + intervals_per_hour  # Gain one hour's worth
    else:
        return base_intervals  # Normal day
```

---

## Part 11: Files Requiring Changes

### Complete File List (40+ files)

#### Core Time & Constants (Priority 1)
1. ✅ `const/time.py` - Add interval constants, change DEFAULT
2. ✅ `const/defaults.py` - Update UPDATE_INTERVAL
3. ✅ `const/display.py` - Already has 15-min option
4. ⚠️ `const/intervals.py` - No change needed (API fetch intervals)

#### Time Calculation (Priority 1)
5. ✅ `timezone/hour_calculator.py` → `interval_calculator.py` (rename file)
6. ✅ `timezone/service.py` - Update imports and method calls
7. ✅ `timezone/__init__.py` - Update imports
8. ✅ `timezone/dst_handler.py` - Update interval count logic
9. ✅ `timezone/converter.py` - Update format strings
10. ✅ `timezone/timezone_converter.py` - Update format strings

#### Data Structures (Priority 1)
11. ✅ `api/base/data_structure.py` - Rename classes and fields
12. ✅ `api/base/base_price_api.py` - Update variable names
13. ✅ `api/base/price_parser.py` - Update parsing logic

#### Parsers (Priority 2)
14. ✅ `api/parsers/entsoe_parser.py` - Prioritize PT15M
15. ✅ `api/parsers/nordpool_parser.py` - Check 15-min support
16. ✅ `api/parsers/epex_parser.py` - Add expansion logic
17. ✅ `api/parsers/omie_parser.py` - Add expansion logic
18. ✅ `api/parsers/amber_parser.py` - Check interval support
19. ✅ `api/parsers/aemo_parser.py` - Check interval support
20. ✅ `api/parsers/comed_parser.py` - Add expansion logic
21. ✅ `api/parsers/energi_data_parser.py` - Check 15-min support
22. ✅ `api/parsers/stromligning_parser.py` - Add expansion logic

#### API Implementations (Priority 2)
23. ✅ `api/aemo.py` - Update variable names
24. ✅ `api/amber.py` - Update variable names
25. ✅ `api/comed.py` - Update variable names
26. ✅ `api/entsoe.py` - Update variable names
27. ✅ `api/epex.py` - Update variable names
28. ✅ `api/utils.py` - Update helper functions

#### Coordinator (Priority 2)
29. ✅ `coordinator/data_processor.py` - Update processing logic
30. ✅ `coordinator/unified_price_manager.py` - Update variable names
31. ✅ `coordinator/cache_manager.py` - Update cache keys
32. ✅ `coordinator/fetch_decision.py` - Update logic

#### Sensors (Priority 3)
33. ✅ `sensor/base.py` - Update attributes
34. ✅ `sensor/price.py` - Rename properties
35. ✅ `sensor/electricity.py` - Update calculations

#### Price Processing (Priority 3)
36. ✅ `price/statistics.py` - Update statistics calculation
37. ✅ `price/currency_converter.py` - Update variable names
38. ✅ `price/formatter.py` - Update formatting

#### Utils (Priority 3)
39. ✅ `utils/data_validator.py` - Update validation logic
40. ✅ `utils/timezone_converter.py` - Update format strings

#### Translations (Priority 4)
41. ✅ `translations/en.json` - Update strings
42. ✅ `translations/strings.json` - Update strings

#### Tests (Priority 4)
43-100. All test files - Update expectations

---

## Summary of Changes

### Quantitative Impact
- **Files to modify:** 40+ Python files
- **Classes to rename:** 2 (HourlyPrice, HourCalculator)
- **Methods to rename:** 6+ (get_*_hour_* methods)
- **Variables to rename:** 415+ occurrences
- **Tests to update:** 196+ test assertions
- **Expected data points:** 24 → 96 (4x increase)

### Configuration Strategy
**Single point of control:** Change `TimeInterval.DEFAULT` in `const/time.py`

**All calculations derive from this:**
- Interval duration (15 minutes)
- Intervals per hour (4)
- Intervals per day (96)
- DST adjustments (92/100 intervals)
- Format strings ("HH:MM")

### Generic Naming Benefits
1. ✅ **Future-proof:** Easy to change to any interval (5-min, 30-min, etc.)
2. ✅ **Clean code:** No hardcoded "hourly" assumptions
3. ✅ **Testable:** Can test both hourly and 15-min by changing one constant
4. ✅ **Maintainable:** Clear separation between configuration and implementation

---

## Next Steps

1. ✅ Review this fact-finding document
2. ✅ Update implementation plan with generic naming strategy
3. ☐ Get approval for approach
4. ☐ Begin Phase 1 implementation
