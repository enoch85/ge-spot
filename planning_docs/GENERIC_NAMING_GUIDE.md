# Quick Reference: Generic Naming & Configuration Guide

## 🎯 Single Point of Control

**To change interval duration, modify ONE line:**

```python
# File: custom_components/ge_spot/const/time.py

class TimeInterval:
    HOURLY = "PT60M"
    QUARTER_HOURLY = "PT15M"
    
    # Change ONLY this line to switch interval duration:
    DEFAULT = QUARTER_HOURLY  # ← THIS ONE!
```

Everything else auto-adapts! ✨

---

## 📋 Generic Naming Cheat Sheet

### Classes
| ❌ Old (Hour-specific) | ✅ New (Generic) |
|------------------------|-----------------|
| `HourlyPrice` | `IntervalPrice` |
| `HourCalculator` | `IntervalCalculator` |

### Variables & Fields
| ❌ Old (Hour-specific) | ✅ New (Generic) |
|------------------------|-----------------|
| `hourly_prices` | `interval_prices` |
| `hour_key` | `interval_key` |
| `next_hour_price` | `next_interval_price` |
| `current_hour_key` | `current_interval_key` |
| `next_hour_key` | `next_interval_key` |
| `raw_hourly` | `raw_intervals` |

### Methods
| ❌ Old (Hour-specific) | ✅ New (Generic) |
|------------------------|-----------------|
| `get_current_hour_key()` | `get_current_interval_key()` |
| `get_next_hour_key()` | `get_next_interval_key()` |
| `get_hour_key_for_datetime()` | `get_interval_key_for_datetime()` |
| `normalize_hourly_prices()` | `normalize_interval_prices()` |
| `parse_hourly_prices()` | `parse_interval_prices()` |

### Format Strings
| ❌ Old (Hour-specific) | ✅ New (Generic) |
|------------------------|-----------------|
| `"HH:00"` | `"HH:MM"` |
| `"%H:00"` | `"%H:%M"` |

---

## 🔧 Configuration-Driven Helper Methods

### Use These Instead of Hardcoded Values

```python
# ✅ GOOD - Configuration-driven
interval_minutes = TimeInterval.get_interval_minutes()  # Returns 15 or 60
intervals_per_hour = TimeInterval.get_intervals_per_hour()  # Returns 4 or 1
intervals_per_day = TimeInterval.get_intervals_per_day()  # Returns 96 or 24

# ❌ BAD - Hardcoded
interval_minutes = 15  # Don't do this!
intervals_per_hour = 4  # Don't do this!
intervals_per_day = 96  # Don't do this!
```

### Example: Generating Interval Keys

```python
# ✅ GOOD - Works for any interval
interval_minutes = TimeInterval.get_interval_minutes()
for h in range(24):
    for m in range(0, 60, interval_minutes):
        interval_key = f"{h:02d}:{m:02d}"
        # Process interval_key...

# ❌ BAD - Hardcoded for 15-min
for h in range(24):
    for m in [0, 15, 30, 45]:  # Don't hardcode!
        interval_key = f"{h:02d}:{m:02d}"
```

### Example: Validation

```python
# ✅ GOOD - Dynamic validation
expected_intervals = TimeInterval.get_intervals_per_day()
if len(interval_prices) >= expected_intervals * 0.8:
    data_is_complete = True

# ❌ BAD - Hardcoded expectation
if len(interval_prices) >= 96 * 0.8:  # Don't hardcode!
    data_is_complete = True
```

---

## 📁 File Renaming

| ❌ Old Filename | ✅ New Filename |
|----------------|----------------|
| `hour_calculator.py` | `interval_calculator.py` |

### Import Updates

```python
# ❌ OLD
from .hour_calculator import HourCalculator

# ✅ NEW
from .interval_calculator import IntervalCalculator
```

---

## 🧪 Testing with Different Intervals

To test both hourly and 15-minute modes:

```python
# For 15-minute testing
TimeInterval.DEFAULT = TimeInterval.QUARTER_HOURLY

# For hourly testing (backward compatibility check)
TimeInterval.DEFAULT = TimeInterval.HOURLY
```

---

## 🎨 Code Style Examples

### ✅ GOOD: Generic Implementation

```python
class IntervalCalculator:
    """Calculate interval keys - works for any interval duration."""
    
    def get_current_interval_key(self) -> str:
        """Get the current interval key formatted as HH:MM."""
        now = dt_util.now(self.timezone)
        rounded = self._round_to_interval(now)
        return f"{rounded.hour:02d}:{rounded.minute:02d}"
    
    def _round_to_interval(self, dt: datetime) -> datetime:
        """Round datetime to nearest interval boundary."""
        interval_minutes = TimeInterval.get_interval_minutes()
        minute = (dt.minute // interval_minutes) * interval_minutes
        return dt.replace(minute=minute, second=0, microsecond=0)
```

### ❌ BAD: Hardcoded Implementation

```python
class HourCalculator:  # Don't use "Hour" in name!
    """Calculate hour keys - hourly only."""  # Not generic!
    
    def get_current_hour_key(self) -> str:  # Don't use "hour" in name!
        """Get the current hour formatted as HH:00."""  # Assumes :00!
        now = dt_util.now(self.timezone)
        return f"{now.hour:02d}:00"  # Hardcoded :00!
```

---

## 📊 Data Structure Examples

### ✅ GOOD: Generic Data Structure

```python
@dataclass
class IntervalPrice:
    """Price data for a single time interval."""
    datetime: str
    price: float
    interval_key: str  # Format: HH:MM
    currency: str
    # ...

@dataclass
class StandardizedPriceData:
    """Standardized price data format."""
    interval_prices: Dict[str, float]  # Key: HH:MM, Value: price
    next_interval_price: Optional[float]
    current_interval_key: Optional[str]
    # ...
```

### ❌ BAD: Hour-specific Data Structure

```python
@dataclass
class HourlyPrice:  # Don't use "Hourly"!
    """Hourly price data."""  # Not generic!
    hour_key: str  # Format: HH:00  # Assumes hourly!
    # ...

@dataclass
class StandardizedPriceData:
    hourly_prices: Dict[str, float]  # Don't use "hourly"!
    next_hour_price: Optional[float]  # Don't use "hour"!
    # ...
```

---

## 🔄 API Parser Examples

### ✅ GOOD: Generic Expansion Function

```python
def expand_to_intervals(hourly_data: Dict[str, float]) -> Dict[str, float]:
    """
    Expand hourly prices to match configured interval.
    
    Generic implementation - works for any interval duration.
    Uses TimeInterval.get_interval_minutes() to determine expansion.
    """
    interval_minutes = TimeInterval.get_interval_minutes()
    
    if interval_minutes == 60:
        return hourly_data  # No expansion needed
    
    intervals_per_hour = TimeInterval.get_intervals_per_hour()
    expanded = {}
    
    for hour_key, price in hourly_data.items():
        hour = int(hour_key.split(':')[0])
        for i in range(intervals_per_hour):
            minute = i * interval_minutes
            interval_key = f"{hour:02d}:{minute:02d}"
            expanded[interval_key] = price
    
    return expanded
```

### ❌ BAD: Hardcoded Expansion Function

```python
def expand_hourly_to_15min(hourly_data: Dict[str, float]) -> Dict[str, float]:
    """Expand hourly prices to 15-minute intervals."""  # Not generic!
    expanded = {}
    
    for hour_key, price in hourly_data.items():
        hour = int(hour_key.split(':')[0])
        for minute in [0, 15, 30, 45]:  # Hardcoded minutes!
            interval_key = f"{hour:02d}:{minute:02d}"
            expanded[interval_key] = price
    
    return expanded
```

---

## 📝 Documentation Strings

### ✅ GOOD: Generic Docstrings

```python
def normalize_interval_prices(prices: Dict) -> Dict[str, float]:
    """
    Normalize prices to interval format.
    
    Works with any interval duration configured in TimeInterval.DEFAULT.
    Returns dictionary with HH:MM keys and float values.
    """
```

### ❌ BAD: Specific Docstrings

```python
def normalize_hourly_prices(prices: Dict) -> Dict[str, float]:
    """
    Normalize prices to hourly format with HH:00 keys.
    Returns 24 prices per day.
    """  # Too specific!
```

---

## 🎯 Remember

1. **Never hardcode interval duration** - Use `TimeInterval.get_interval_minutes()`
2. **Never hardcode interval counts** - Use `TimeInterval.get_intervals_per_*()` 
3. **Never use "hourly" or "15min" in names** - Use "interval"
4. **Never assume ":00" format** - Use "HH:MM"
5. **Always make code configuration-driven** - Check `TimeInterval.DEFAULT`

---

## 🚀 Quick Start

When implementing, follow this pattern:

1. ✅ Import the helper methods
2. ✅ Use generic variable names (`interval_*` not `hourly_*`)
3. ✅ Call `TimeInterval.get_*()` methods instead of hardcoding
4. ✅ Use "HH:MM" format for keys
5. ✅ Write generic docstrings

**Remember:** The goal is to make it easy to change the interval duration in the future by changing ONE constant!
