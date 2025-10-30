# Cache Refactor: Compute-on-Demand Metadata Architecture

**Priority**: Medium  
**Effort**: Large (2-3 weeks)  
**Impact**: High (eliminates entire class of bugs)  
**Risk**: Medium (requires careful migration)

---

## Problem Statement

Currently, the cache stores both source data AND derived metadata (statistics, validity, flags). This creates maintenance burden and cache coherency bugs:

- **Issue #44**: Midnight migration forgot to recalculate `data_validity`
- **Scattered calculations**: Same logic in multiple places
- **Sync bugs**: Data changes but metadata doesn't
- **Complexity**: 20+ fields to keep in sync manually
- **Performance**: Recalculating anyway to verify cache is valid

**Current cache structure** (30+ fields):
```python
{
    "today_interval_prices": {...},      # Source data
    "tomorrow_interval_prices": {...},   # Source data
    "data_validity": {...},              # ← Derived (should compute)
    "statistics": {...},                 # ← Derived (should compute)
    "tomorrow_statistics": {...},        # ← Derived (should compute)
    "has_tomorrow_prices": True,         # ← Derived (should compute)
    # ... 20+ more fields
}
```

---

## Proposed Solution

### Core Principle: Single Source of Truth

**Store ONLY immutable source data in cache:**
- Interval prices (today/tomorrow)
- Raw prices (before VAT)
- Source metadata (currency, timezone, timestamps)
- Original API response (for debugging)

**Compute EVERYTHING else on-demand:**
- Data validity → property from interval counts
- Statistics → property from price values
- Current price → lookup at current interval
- Flags → boolean properties

### Benefits

1. **Eliminates cache coherency bugs**: Source data changes → properties auto-update
2. **Simplifies migration**: Only move prices, everything else auto-recalculates
3. **Single code path**: One place to calculate validity, statistics, etc.
4. **Easier testing**: Test calculation once, not cache sync everywhere
5. **Performance**: Compute only what's needed, when needed (lazy evaluation)
6. **Smaller cache**: 70% size reduction (store ~10 fields vs 30+)

---

## Implementation Plan

### Phase 1: Create Data Classes (Week 1)

**Goal**: Encapsulate source data with computed properties

#### 1.1 Create `coordinator/data_models.py`

```python
"""Data models for price data with computed properties."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from ..api.base.data_structure import PriceStatistics
from .data_validity import DataValidity, calculate_data_validity
from ..timezone.service import TimezoneService


@dataclass
class IntervalPriceData:
    """Source data for interval prices with computed properties.
    
    This class stores ONLY source data. All metadata is computed on-demand
    as properties, ensuring cache coherency and eliminating sync bugs.
    """
    
    # ========== SOURCE DATA (stored in cache) ==========
    
    # Price data
    today_interval_prices: Dict[str, float] = field(default_factory=dict)
    tomorrow_interval_prices: Dict[str, float] = field(default_factory=dict)
    today_raw_prices: Dict[str, float] = field(default_factory=dict)
    tomorrow_raw_prices: Dict[str, float] = field(default_factory=dict)
    
    # Source metadata
    source: str = ""
    area: str = ""
    source_currency: str = "EUR"
    target_currency: str = "SEK"
    source_timezone: str = "UTC"
    target_timezone: str = "UTC"
    
    # Conversion data
    ecb_rate: Optional[float] = None
    ecb_updated: Optional[str] = None
    
    # Display configuration
    vat_rate: float = 0.0
    vat_included: bool = False
    display_unit: str = "EUR/kWh"
    
    # Timestamps
    fetched_at: Optional[str] = None
    last_updated: Optional[str] = None
    
    # Migration tracking
    migrated_from_tomorrow: bool = False
    original_cache_date: Optional[str] = None
    
    # Raw API data (for debugging)
    raw_data: Optional[dict] = None
    
    # Timezone service (not serialized)
    _tz_service: Optional[TimezoneService] = field(default=None, repr=False)
    
    # ========== COMPUTED PROPERTIES (NOT stored) ==========
    
    @property
    def data_validity(self) -> DataValidity:
        """Calculate data validity from interval prices.
        
        Always computed fresh from source data, ensuring accuracy.
        """
        if not self._tz_service:
            return DataValidity()  # Empty validity if no timezone service
        
        from homeassistant.util import dt as dt_util
        now = dt_util.now()
        current_interval_key = self._tz_service.get_current_interval_key()
        
        return calculate_data_validity(
            interval_prices=self.today_interval_prices,
            tomorrow_interval_prices=self.tomorrow_interval_prices,
            now=now,
            current_interval_key=current_interval_key,
            target_timezone=self.target_timezone,
        )
    
    @property
    def statistics(self) -> PriceStatistics:
        """Calculate statistics from today's prices."""
        if not self.today_interval_prices:
            return PriceStatistics()
        
        prices = list(self.today_interval_prices.values())
        return PriceStatistics(
            avg=sum(prices) / len(prices),
            min=min(prices),
            max=max(prices),
            # TODO: Add min/max timestamps
        )
    
    @property
    def tomorrow_statistics(self) -> PriceStatistics:
        """Calculate statistics from tomorrow's prices."""
        if not self.tomorrow_interval_prices:
            return PriceStatistics()
        
        prices = list(self.tomorrow_interval_prices.values())
        return PriceStatistics(
            avg=sum(prices) / len(prices),
            min=min(prices),
            max=max(prices),
        )
    
    @property
    def has_tomorrow_prices(self) -> bool:
        """Check if tomorrow prices exist."""
        return bool(self.tomorrow_interval_prices)
    
    @property
    def current_price(self) -> Optional[float]:
        """Get current interval price."""
        if not self._tz_service:
            return None
        
        current_key = self._tz_service.get_current_interval_key()
        return self.today_interval_prices.get(current_key)
    
    @property
    def next_interval_price(self) -> Optional[float]:
        """Get next interval price."""
        if not self._tz_service:
            return None
        
        # TODO: Implement next interval logic
        return None
    
    # ========== METHODS ==========
    
    def migrate_to_new_day(self) -> None:
        """Migrate tomorrow's data to today after midnight.
        
        This is the ONLY place migration logic exists.
        All properties automatically update after this.
        """
        # Move tomorrow → today
        self.today_interval_prices = self.tomorrow_interval_prices
        self.today_raw_prices = self.tomorrow_raw_prices
        
        # Clear tomorrow
        self.tomorrow_interval_prices = {}
        self.tomorrow_raw_prices = {}
        
        # Mark as migrated
        self.migrated_from_tomorrow = True
        
        # That's it! All properties (data_validity, statistics, etc.)
        # automatically recalculate from the new source data.
    
    def to_cache_dict(self) -> dict:
        """Convert to dictionary for cache storage.
        
        Returns ONLY source data, not computed properties.
        """
        return {
            # Price data
            "today_interval_prices": self.today_interval_prices,
            "tomorrow_interval_prices": self.tomorrow_interval_prices,
            "today_raw_prices": self.today_raw_prices,
            "tomorrow_raw_prices": self.tomorrow_raw_prices,
            
            # Source metadata
            "source": self.source,
            "area": self.area,
            "source_currency": self.source_currency,
            "target_currency": self.target_currency,
            "source_timezone": self.source_timezone,
            "target_timezone": self.target_timezone,
            
            # Conversion data
            "ecb_rate": self.ecb_rate,
            "ecb_updated": self.ecb_updated,
            
            # Display
            "vat_rate": self.vat_rate,
            "vat_included": self.vat_included,
            "display_unit": self.display_unit,
            
            # Timestamps
            "fetched_at": self.fetched_at,
            "last_updated": self.last_updated,
            
            # Migration tracking
            "migrated_from_tomorrow": self.migrated_from_tomorrow,
            "original_cache_date": self.original_cache_date,
            
            # Raw data
            "raw_data": self.raw_data,
        }
    
    @classmethod
    def from_cache_dict(cls, data: dict, tz_service: Optional[TimezoneService] = None):
        """Create from cache dictionary.
        
        Args:
            data: Dictionary from cache (source data only)
            tz_service: Timezone service for computing properties
        """
        return cls(
            today_interval_prices=data.get("today_interval_prices", {}),
            tomorrow_interval_prices=data.get("tomorrow_interval_prices", {}),
            today_raw_prices=data.get("today_raw_prices", {}),
            tomorrow_raw_prices=data.get("tomorrow_raw_prices", {}),
            source=data.get("source", ""),
            area=data.get("area", ""),
            source_currency=data.get("source_currency", "EUR"),
            target_currency=data.get("target_currency", "SEK"),
            source_timezone=data.get("source_timezone", "UTC"),
            target_timezone=data.get("target_timezone", "UTC"),
            ecb_rate=data.get("ecb_rate"),
            ecb_updated=data.get("ecb_updated"),
            vat_rate=data.get("vat_rate", 0.0),
            vat_included=data.get("vat_included", False),
            display_unit=data.get("display_unit", "EUR/kWh"),
            fetched_at=data.get("fetched_at"),
            last_updated=data.get("last_updated"),
            migrated_from_tomorrow=data.get("migrated_from_tomorrow", False),
            original_cache_date=data.get("original_cache_date"),
            raw_data=data.get("raw_data"),
            _tz_service=tz_service,
        )
    
    def to_processed_result(self) -> dict:
        """Convert to processed result format for backward compatibility.
        
        This generates the OLD format with all computed fields.
        Used during migration period for compatibility.
        """
        return {
            # Source data
            **self.to_cache_dict(),
            
            # Computed properties (for backward compatibility)
            "data_validity": self.data_validity.to_dict(),
            "statistics": self.statistics.to_dict(),
            "tomorrow_statistics": self.tomorrow_statistics.to_dict(),
            "has_tomorrow_prices": self.has_tomorrow_prices,
            "current_price": self.current_price,
            "next_interval_price": self.next_interval_price,
            "current_interval_key": self._tz_service.get_current_interval_key() if self._tz_service else None,
            # ... other computed fields
        }
```

#### 1.2 Add Unit Tests

`tests/pytest/unit/test_data_models.py`:
- Test property calculations
- Test migration logic
- Test serialization/deserialization
- Test backward compatibility

#### 1.3 Deliverables

- [ ] `coordinator/data_models.py` created
- [ ] All properties compute correctly
- [ ] `migrate_to_new_day()` works
- [ ] Serialization works
- [ ] 100% test coverage

---

### Phase 2: Refactor Cache Manager (Week 2)

**Goal**: Use new data model in cache operations

#### 2.1 Update `cache_manager.py`

```python
from .data_models import IntervalPriceData

class CacheManager:
    def __init__(self, hass, config):
        self.hass = hass
        self.config = config
        self._timezone_service = None
        self._price_cache = AdvancedCache(hass, config)
    
    def store(self, area: str, source: str, data: IntervalPriceData, ...):
        """Store price data.
        
        Args:
            data: IntervalPriceData instance (NOT dict)
        """
        # Convert to cache dict (source data only)
        cache_dict = data.to_cache_dict()
        
        # Store in cache
        cache_key = self._generate_cache_key(area, source, target_date)
        self._price_cache.set(cache_key, cache_dict, metadata={...})
    
    def get_data(self, area: str, ...) -> Optional[IntervalPriceData]:
        """Get price data.
        
        Returns:
            IntervalPriceData instance with computed properties
        """
        # Get raw dict from cache
        cache_dict = self._price_cache.get(cache_key)
        if not cache_dict:
            return None
        
        # Convert to data model
        return IntervalPriceData.from_cache_dict(
            cache_dict, 
            tz_service=self._timezone_service
        )
    
    def _migrate_midnight_transition(self, data: IntervalPriceData) -> IntervalPriceData:
        """Migrate data at midnight.
        
        Now trivial - just call the method!
        """
        data.migrate_to_new_day()
        return data
```

#### 2.2 Backward Compatibility Layer

During transition, support both formats:

```python
def get_data(self, area: str, ...) -> Optional[IntervalPriceData]:
    cache_dict = self._price_cache.get(cache_key)
    if not cache_dict:
        return None
    
    # Check cache version
    if "data_validity" in cache_dict:
        # OLD FORMAT: Has computed fields in cache
        # Convert to new format (drop computed fields)
        cache_dict = self._convert_old_format(cache_dict)
    
    # Return new format
    return IntervalPriceData.from_cache_dict(cache_dict, self._timezone_service)

def _convert_old_format(self, old_cache: dict) -> dict:
    """Convert old cache format to new.
    
    Drops all computed fields, keeps only source data.
    """
    return {
        k: v for k, v in old_cache.items()
        if k not in ["data_validity", "statistics", "tomorrow_statistics", ...]
    }
```

#### 2.3 Deliverables

- [ ] `cache_manager.py` uses `IntervalPriceData`
- [ ] Midnight migration uses `migrate_to_new_day()`
- [ ] Backward compatibility for old cache
- [ ] Tests pass
- [ ] Old cache gradually replaced

---

### Phase 3: Update Consumers (Week 3)

**Goal**: Update all code that uses cached data

#### 3.1 Update `unified_price_manager.py`

```python
async def _fetch_and_process_data(self, ...):
    # Get from cache
    cached_data = self._cache_manager.get_data(area, today_date)
    
    if cached_data:
        # It's already an IntervalPriceData instance!
        # Properties compute on-demand
        validity = cached_data.data_validity  # Computed property
        
        if validity.has_minimum_data:
            return cached_data.to_processed_result()  # Convert to old format
    
    # Fetch fresh
    raw_data = await self._fetch_from_api(...)
    
    # Create data model
    price_data = IntervalPriceData(
        today_interval_prices=processed_today,
        tomorrow_interval_prices=processed_tomorrow,
        source=source,
        area=area,
        fetched_at=dt_util.now().isoformat(),
        _tz_service=self._tz_service,
    )
    
    # Store (only source data cached)
    self._cache_manager.store(area, source, price_data, ...)
    
    # Return old format for sensors
    return price_data.to_processed_result()
```

#### 3.2 Update `data_processor.py`

```python
async def process_data(self, data: dict) -> dict:
    # Process API data as before
    processed = {...}
    
    # Create data model
    price_data = IntervalPriceData(
        today_interval_prices=final_today_prices,
        tomorrow_interval_prices=final_tomorrow_prices,
        # ... other source fields
        _tz_service=self._tz_service,
    )
    
    # Return old format (properties computed on-demand)
    return price_data.to_processed_result()
```

#### 3.3 Update Sensors

Sensors can either:
1. **Keep using old format**: Call `to_processed_result()` (no sensor changes)
2. **Use data model directly**: Access properties (cleaner, future-proof)

```python
# Option 1: No sensor changes (backward compatible)
processed_data = price_data.to_processed_result()
self._attr_native_value = processed_data["current_price"]

# Option 2: Use properties directly (cleaner)
self._attr_native_value = price_data.current_price
self._attr_extra_state_attributes = {
    "validity": price_data.data_validity.to_dict(),
    "statistics": price_data.statistics.to_dict(),
}
```

#### 3.4 Deliverables

- [ ] `unified_price_manager.py` updated
- [ ] `data_processor.py` updated
- [ ] Sensors work (either option)
- [ ] All tests pass
- [ ] Integration tests pass

---

### Phase 4: Performance Optimization (Optional)

**Goal**: Add caching for expensive computations

#### 4.1 Add Property Caching

```python
from functools import cached_property

class IntervalPriceData:
    @cached_property
    def data_validity(self) -> DataValidity:
        """Cached until object changes."""
        return calculate_data_validity(...)
    
    @cached_property
    def statistics(self) -> PriceStatistics:
        """Cached until object changes."""
        return self._calculate_statistics(self.today_interval_prices)
```

**Note**: Use `cached_property` only if profiling shows benefit. Start without it.

#### 4.2 Profiling

Measure before/after:
- Memory usage (cache size)
- CPU usage (recalculation overhead)
- Response time (sensor updates)

Expected improvements:
- 70% smaller cache (10 fields vs 30)
- Same or better CPU (fewer cache syncs)
- Same response time (lazy evaluation)

---

## Migration Strategy

### Gradual Rollout

1. **v1.7.0**: Add `IntervalPriceData`, use internally, output old format
2. **v1.7.1**: Update cache manager, backward compatible with old cache
3. **v1.7.2**: Update coordinator and processor
4. **v1.8.0**: (Optional) Sensors use properties directly
5. **v2.0.0**: (Future) Remove old format entirely

### Rollback Plan

Each version must support old cache format:
- v1.7.x can read old v1.6.x cache
- If issues, revert to previous version
- Old cache still works

### Testing Strategy

1. **Unit tests**: Each property calculates correctly
2. **Integration tests**: Full fetch→cache→retrieve→display cycle
3. **Migration tests**: Old cache converts to new format
4. **Performance tests**: Measure memory/CPU impact
5. **Manual tests**: Real Home Assistant instance

---

## Success Criteria

- [ ] Migration is 3 lines: `data.migrate_to_new_day()`
- [ ] No cache coherency bugs possible (source of truth)
- [ ] Cache size reduced by 70%
- [ ] All tests pass
- [ ] Backward compatible with v1.6.x cache
- [ ] No performance regression
- [ ] Documentation updated

---

## Risks & Mitigations

### Risk 1: Breaking Changes
**Mitigation**: Maintain backward compatibility for 2-3 versions

### Risk 2: Performance Regression
**Mitigation**: Profile before/after, add `cached_property` if needed

### Risk 3: Complex Migration
**Mitigation**: Gradual rollout over multiple versions

### Risk 4: Bugs in Property Logic
**Mitigation**: 100% test coverage on properties

### Risk 5: User Confusion
**Mitigation**: No visible changes to sensors, transparent migration

---

## Future Enhancements

After this refactor, easier to add:

1. **Different time intervals**: Just change interval dict keys
2. **Multiple price components**: Add more price dicts as source data
3. **Advanced statistics**: Just add properties
4. **Real-time updates**: Properties always fresh
5. **A/B testing**: Easy to compare calculation methods

---

## Estimated Effort

- **Development**: 2-3 weeks (1 developer)
- **Testing**: 1 week
- **Review & iteration**: 1 week
- **Documentation**: 2-3 days

**Total**: ~4-5 weeks for complete rollout

---

## Dependencies

- None (self-contained refactor)
- But should do AFTER current Issue #44 fix is merged

---

## References

- **Design Pattern**: Repository Pattern + Computed Properties
- **Similar projects**: 
  - SQLAlchemy (computed columns)
  - Django ORM (property decorators)
  - Pydantic (validators and computed fields)

---

## Next Steps

1. Review this plan with team
2. Get approval for Phase 1
3. Create feature branch `refactor/computed-properties`
4. Implement Phase 1 (Week 1)
5. Review & iterate
6. Continue to Phase 2
