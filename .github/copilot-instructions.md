# GitHub Copilot Instructions for GE-Spot

Home Assistant custom integration providing 15-minute electricity spot prices across global markets. **Production code affecting real homes and electricity costs.**

## Core Principles

1. **Read entire files before editing** - Never edit based on grep/partial reads
2. **Configuration-driven, never hardcode** - All values from `const/` modules
3. **Generic naming only** - `interval_prices`, not `hourly_prices` or `15min_data`
4. **No backward compatibility** - Rename directly, update all callers, no aliases
5. **Test after every change** - Clear `__pycache__`, run tests, verify logs
6. **No verbose summaries** - User sees changes in editor, only respond if asked
7. **Keep it simple** - Clean code over complexity, cleanup as you go
8. **Ask before acting** - When uncertain, clarify first
9. **No analysis/summary files in git** - All `*ANALYSIS*.md`, `*SUMMARY*.md` files stay untracked

## Architecture

### Configuration-Driven Design
Single constant controls entire system: `TimeInterval.DEFAULT = "PT15M"` (15 minutes, 96 intervals/day)

```python
# ✅ Correct
from ..const.time import TimeInterval
intervals = TimeInterval.get_intervals_per_day()  # 96

# ❌ Wrong
intervals = 96  # NEVER hardcode
```

### Three-Layer Structure

1. **API Layer** (`api/`): Source-specific clients (Nordpool, ENTSO-E, AEMO, etc.)
   - Clients in `api/*.py`, parsers in `api/parsers/`
   - Base classes in `api/base/` (session, errors, data structures)
   - All return `StandardizedPriceData`

2. **Coordinator Layer** (`coordinator/`): `UnifiedPriceCoordinator` manages lifecycle
   - Source fallback (tries priority order, auto-switches on failure)
   - Caching via `CacheManager` (TTL, persistence, deep copies to prevent mutation)
   - Rate limiting (15min minimum between fetches per area)

3. **Sensor Layer** (`sensor/`): Home Assistant entities
   - Current price, next interval, averages, peaks, tomorrow forecasts
   - Attributes contain 96 interval entries for automations
   - Source-agnostic (entity IDs stable regardless of API source)

**Data Flow:**
```
API Client → Parser → StandardizedPriceData → UnifiedPriceManager → 
CacheManager/DataProcessor → Sensors → Home Assistant
```

**Cross-Cutting:**
- **Timezone** (`timezone/`): Normalizes all timestamps to HA timezone, handles DST (92-100 intervals on transitions)
- **Price** (`price/`): Currency conversion (ECB rates), VAT, unit formatting (EUR/kWh vs cents/kWh)
- **Constants** (`const/`): `Config`, `TimeInterval`, `Source`, `Defaults`

## Critical Rules

### Always Read Full Files
Before editing, use `read_file` for entire file. Understand context, identify all change locations.

### Use Configuration
```python
# ✅ Do this
interval_minutes = TimeInterval.get_interval_minutes()
items_per_cycle = TimeInterval.get_intervals_per_day()

# ❌ Never this
interval_minutes = 15
items_per_cycle = 96
```

### Generic Naming
```python
# ✅ Generic
normalize_interval_prices(), interval_key, IntervalCalculator

# ❌ Specific
normalize_hourly_prices(), hour_key, QuarterHourCalculator
```

### No Backward Compatibility
```python
# ❌ Don't create aliases
def old_name(*args, **kwargs):
    return new_name(*args, **kwargs)

# ✅ Just rename and update ALL callers
def new_name(data, ...):
    # implementation
```

### Verify Your Work
```bash
# Search for old terms
grep -r "old_function_name" custom_components/

# Find hardcoded values
grep -r "= 96" custom_components/

# Test imports
python3 -c "from custom_components.ge_spot.module import NewClass"
```

## Code Standards

**Imports:** Group as stdlib, third-party, local. Relative imports within `custom_components/ge_spot/`.

**Error Handling:** Specific exceptions, log with context, graceful fallback.
```python
try:
    result = api.fetch_data()
except APIError as e:
    _LOGGER.error(f"API fetch failed: {e}")
    return cached_data
```

**Type Hints:** Required on all functions. Use `Optional`, `Union`, `Dict[str, Any]`.

**Async:** Almost everything is async. Use `await`, sessions via `async_get_clientsession(hass)`.

**Docstrings:** Every public function/class. Include types, example for complex functions.

**Comments:** Explain WHY, not WHAT. Update or remove when changing code.

## Testing

**Priority:** Test production code, not test helpers. Mock external APIs/expensive ops, use real calls for integration tests.

```python
# ✅ Test production
def test_api_fetch_real_data():
    api = ProductionAPI(api_key="test_key")
    result = api.fetch_data(region="TEST")
    assert result is not None
    assert len(result["data"]) > 0

# ❌ Test mocks
def test_mock_returns_structure():
    mock_data = create_mock_data()
    assert mock_data["field"] == "expected"
```

**When to Mock:** External APIs with rate limits/costs, authentication, slow operations, non-deterministic behavior

**When Real Calls:** Integration tests, parser validation, configuration testing, smoke tests

**Run Tests:**
- Unit: `./scripts/run_pytest.sh` or `pytest tests/pytest/unit/ -v`
- Integration: `./scripts/run_pytest.sh --with-integration`
- Manual: `./scripts/run_manual_tests.sh`

## Common Tasks

### Adding API Source
1. Create `api/new_source.py` extending `BasePriceAPI`
2. Implement `fetch_raw_data()` returning list of dicts
3. Create parser in `api/parsers/new_source.py` returning `StandardizedPriceData`
4. Register in `coordinator/unified_price_manager.py` `_source_api_map`
5. Add to `const/sources.py` and `const/areas.py`

### Debugging Prices
1. Check logs: "Normalized N timestamps", "Split prices into today (X) tomorrow (Y)"
2. Verify X and Y = `TimeInterval.get_intervals_per_day()` (usually 96)
3. Check `get_day_hours()` in `timezone_provider.py` generates correct count
4. Test API response: `curl` endpoint, verify interval count
5. Verify `IntervalCalculator` generates HH:MM keys with correct spacing

### Cache Issues
- Location: `.storage/` (configurable via `Config.CACHE_DIR`)
- Clear: Delete cache files, restart Home Assistant
- Uses deep copies to prevent mutation (`cache_manager.py`)

## Key Files
- Entry: `custom_components/ge_spot/__init__.py`
- Coordinator: `coordinator/unified_price_manager.py`
- Time config: `const/time.py` (defines `TimeInterval.DEFAULT`)
- Interval calc: `utils/interval_calculator.py`
- Timezone: `timezone/timezone_converter.py`
- API registry: `coordinator/unified_price_manager.py` (`_source_api_map`)

## Refactoring

### Phase Order
```
Foundation → Data → Logic → Presentation → Support
Constants → Structures → Processors → Sensors → Tests
Base classes → APIs → Coordinators → Config → Utils
```

### Before Claiming Phase Complete
- [ ] All files updated (including base classes, validators, tests)
- [ ] All names changed (variables, functions, classes)
- [ ] All docs updated (docstrings, comments, type hints)
- [ ] All imports/callers updated
- [ ] Tests pass, no syntax errors
- [ ] Grep shows no old terms (except explanatory comments)
- [ ] No duplicates or dead code

### Commit After Each Phase
```bash
git commit -m "Phase N: Description
- Change 1
- Change 2
Tests: passing"
```

## Common Mistakes

❌ **Editing without full context** - Read entire file, not grep results
❌ **Hardcoding values** - Use `TimeInterval.get_intervals_per_day()`, not `96`
❌ **Incomplete refactoring** - Search ALL occurrences, update ALL (including tests)
❌ **Mixed terminology** - Complete one layer at a time
❌ **Forgetting base classes** - Update base classes first, they affect everything
❌ **Outdated documentation** - Update docstrings, comments, type hints with code

## Code Quality

**Remove dead code immediately:**
```python
# ❌ Don't leave
UNUSED_VAR = True  # Never used

# ✅ Delete it
```

**Fix duplicates:**
```python
# ❌ Same file
MAX = 100  # Line 18
MAX = 10   # Line 26 (overwrites!)

# ✅ One definition
MAX = 1000  # Single value
```

**Document calculations:**
```python
# ✅ Show math
# 3 days × 24 hours × 4 intervals/hour × 10 areas × 1.2 buffer
# = 3,456 → round to 3,500
CACHE_MAX = 3500
```

**Prefer content checks:**
```python
# ❌ Time-based
if time.time() - cached_time < MAX_AGE:
    return cached_data

# ✅ Content-based
if cached_data.get("statistics", {}).get("data_complete"):
    return cached_data
```

## Project Context

**Branch:** `15min` - Migration from hourly to 15-minute intervals

**Known Issues:** See `TODO/`

**Integration:** Home Assistant `DataUpdateCoordinator` pattern, config flow in `config_flow/`, HACS compatible

Quality and correctness over speed. When uncertain, ask before implementing.
