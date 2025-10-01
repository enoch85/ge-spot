# 15-Minute Migration Progress Tracker

**Last Updated:** October 1, 2025  
**Status:** 📋 Planning Complete - Ready to Start

---

## 📊 Overall Progress: 0/24 TODOs (0%)

```
████░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 0%
```

---

## Phase 1: Core Constants & Time Handling

**Progress:** 0/2 (0%)

- [ ] **TODO-001:** Implement configuration-driven interval system
  - [ ] Change `TimeInterval.DEFAULT` to `QUARTER_HOURLY`
  - [ ] Add `get_interval_minutes()` method
  - [ ] Add `get_intervals_per_hour()` method
  - [ ] Add `get_intervals_per_day()` method
  - [ ] Add DST calculation methods
  
- [ ] **TODO-002:** Update default update interval
  - [ ] Change `UPDATE_INTERVAL = 30` → `15`

**Files Modified:** 0/2
- [ ] `const/time.py`
- [ ] `const/defaults.py`

**Checkpoint:** ☐ Type checks pass, no import errors

---

## Phase 2: Data Structures

**Progress:** 0/2 (0%)

- [ ] **TODO-003:** Rename HourCalculator → IntervalCalculator
  - [ ] Rename file
  - [ ] Rename class
  - [ ] Rename methods (3 methods)
  - [ ] Update imports in `timezone/service.py`
  - [ ] Update imports in `timezone/__init__.py`

- [ ] **TODO-004:** Update interval calculation logic
  - [ ] Add `_round_to_interval()` method
  - [ ] Update `get_current_interval_key()`
  - [ ] Update `get_next_interval_key()`
  - [ ] Update DST handling
  - [ ] Update all docstrings

**Files Modified:** 0/3
- [ ] `timezone/hour_calculator.py` → `interval_calculator.py`
- [ ] `timezone/service.py`
- [ ] `timezone/__init__.py`

**Checkpoint:** ☐ IntervalCalculator returns correct HH:MM format

---

## Phase 3: API Layer Changes

**Progress:** 0/4 (0%)

- [ ] **TODO-005:** Rename HourlyPrice class
  - [ ] Rename class
  - [ ] Rename field: `hour_key` → `interval_key`
  - [ ] Update docstrings

- [ ] **TODO-006:** Update StandardizedPriceData
  - [ ] Rename 6 fields
  - [ ] Update `to_dict()` method
  - [ ] Update docstrings

- [ ] **TODO-007:** Update base API
  - [ ] Update docstrings
  - [ ] Update variable names

- [ ] **TODO-008:** Create generic expansion utility
  - [ ] Create `expand_to_intervals()` function
  - [ ] Add granularity detection
  - [ ] Document expansion strategy

- [ ] **TODO-009:** Update parser implementations
  - [ ] ENTSO-E parser (prioritize PT15M)
  - [ ] NordPool parser
  - [ ] EPEX parser
  - [ ] OMIE parser
  - [ ] ComEd parser
  - [ ] Stromligning parser
  - [ ] Energi Data parser
  - [ ] Amber parser
  - [ ] AEMO parser

**Files Modified:** 0/13
- [ ] `api/base/data_structure.py`
- [ ] `api/base/base_price_api.py`
- [ ] `api/parsers/entsoe_parser.py`
- [ ] `api/parsers/nordpool_parser.py`
- [ ] `api/parsers/epex_parser.py`
- [ ] `api/parsers/omie_parser.py`
- [ ] `api/parsers/comed_parser.py`
- [ ] `api/parsers/stromligning_parser.py`
- [ ] `api/parsers/energi_data_parser.py`
- [ ] `api/parsers/amber_parser.py`
- [ ] `api/parsers/aemo_parser.py`
- [ ] `api/base/price_parser.py`
- [ ] `api/utils.py`

**Checkpoint:** ☐ Parsers output correct interval_prices format

---

## Phase 4: Coordinator & Data Processing

**Progress:** 0/3 (0%)

- [ ] **TODO-010:** Update data processor
  - [ ] Update variable names
  - [ ] Update processing logic for variable intervals
  - [ ] Update statistics calculations
  - [ ] Update cache key generation

- [ ] **TODO-011:** Update unified price manager
  - [ ] Update method signatures
  - [ ] Update internal variables
  - [ ] Update caching logic

- [ ] **TODO-012:** Update base sensor
  - [ ] Update attribute names
  - [ ] Update property methods
  - [ ] Update state calculations

**Files Modified:** 0/3
- [ ] `coordinator/data_processor.py`
- [ ] `coordinator/unified_price_manager.py`
- [ ] `sensor/base.py`

**Checkpoint:** ☐ Data flows correctly through coordinator

---

## Phase 5: Sensor Layer

**Progress:** 0/3 (0%)

- [ ] **TODO-013:** Update price sensor
  - [ ] Rename `next_hour_price` → `next_interval_price`
  - [ ] Update sensor attributes
  - [ ] Update documentation

- [ ] **TODO-014:** Update electricity sensor
  - [ ] Update entity names
  - [ ] Update descriptions
  - [ ] Verify statistics calculations

- [ ] **TODO-015:** Update price formatter
  - [ ] Update format strings
  - [ ] Update timestamp logic
  - [ ] Ensure 15-min interval display

**Files Modified:** 0/3
- [ ] `sensor/price.py`
- [ ] `sensor/electricity.py`
- [ ] `price/formatter.py`

**Checkpoint:** ☐ Sensors display correctly in Home Assistant

---

## Phase 6: Price Processing

**Progress:** 0/3 (0%)

- [ ] **TODO-016:** Update price statistics
  - [ ] Update expected interval calculations
  - [ ] Update peak hour detection
  - [ ] Update complete data threshold
  - [ ] Update variable names

- [ ] **TODO-017:** Update timezone handling
  - [ ] Update all IntervalCalculator references
  - [ ] Update imports
  - [ ] Verify DST handling

- [ ] **TODO-018:** Update utility functions
  - [ ] Search for remaining "hour" references
  - [ ] Update to interval concepts

**Files Modified:** 0/10
- [ ] `price/statistics.py`
- [ ] `price/currency_converter.py`
- [ ] `timezone/converter.py`
- [ ] `timezone/dst_handler.py`
- [ ] `timezone/service.py`
- [ ] `timezone/timezone_converter.py`
- [ ] `utils/timezone_converter.py`
- [ ] `utils/data_validator.py`
- [ ] `utils/date_range.py`
- [ ] `utils/validation/data_validator.py`

**Checkpoint:** ☐ All utilities work with variable intervals

---

## Phase 7: Utilities & Config

**Progress:** 0/3 (0%)

- [ ] **TODO-019:** Update translation files
  - [ ] Update "hourly" → "interval"
  - [ ] Update sensor descriptions
  - [ ] Update UI strings

- [ ] **TODO-020:** Update config flow
  - [ ] Update UI text
  - [ ] Update validation logic
  - [ ] Verify config flow works

- [ ] **TODO-021:** Update unit tests
  - [ ] Update expectations: 24 → 96
  - [ ] Update format tests
  - [ ] Add interval rounding tests
  - [ ] Update DST tests

**Files Modified:** 0/5
- [ ] `translations/en.json`
- [ ] `translations/strings.json`
- [ ] `config_flow.py`
- [ ] `config_flow/*.py` files
- [ ] Unit test files

**Checkpoint:** ☐ Config flow works, UI strings correct

---

## Phase 8: Testing - Integration

**Progress:** 0/3 (0%)

- [ ] **TODO-022:** Update integration tests
  - [ ] Update `test_nordpool_live.py`
  - [ ] Update `test_epex_live.py`
  - [ ] Update `test_entsoe_full_chain.py`
  - [ ] Update `test_amber_live.py`
  - [ ] Update `test_energi_data_live.py`
  - [ ] Update other integration tests

- [ ] **TODO-023:** Update manual tests
  - [ ] Update API test scripts
  - [ ] Update full chain tests
  - [ ] Test with real API data

- [ ] **TODO-024:** Update documentation
  - [ ] Update README.md
  - [ ] Update docs/
  - [ ] Add migration notes

**Files Modified:** 0/20+
- [ ] All test files updated

**Checkpoint:** ☐ All tests pass

---

## Final Validation

### Code Quality Checks
- [ ] No "hourly" in variable names (except comments/docs)
- [ ] No "hour_key" in code
- [ ] All "HH:00" format strings changed to "HH:MM"
- [ ] No hardcoded 24, 96, 15, etc. (use TimeInterval methods)
- [ ] All imports updated (HourCalculator → IntervalCalculator)
- [ ] All docstrings updated to be generic

### Functional Tests
- [ ] Can fetch prices from all APIs
- [ ] Sensors display correct data in Home Assistant
- [ ] Statistics calculate correctly
- [ ] DST transitions handled properly
- [ ] Cache works correctly
- [ ] Config flow works
- [ ] No errors in Home Assistant logs

### Configuration Tests
- [ ] Change `TimeInterval.DEFAULT` to `HOURLY` → everything still works
- [ ] Change back to `QUARTER_HOURLY` → switches to 15-min
- [ ] Verify auto-calculation of all derived values

---

## 🎯 Completion Criteria

- [x] All 24 TODOs marked complete
- [ ] All 40+ files modified
- [ ] All 415+ variable occurrences updated
- [ ] All 196+ test assertions updated
- [ ] All tests passing
- [ ] Code is clean and maintainable
- [ ] Documentation updated
- [ ] No backward compatibility breaks (acceptable)

---

## 📝 Notes & Issues

### Blockers
- None currently

### Decisions Made
- Using GENERIC naming (interval, not 15min)
- Using CONFIGURATION-DRIVEN approach
- No backward compatibility needed
- Expansion strategy for hourly-only APIs

### Questions
- None currently

---

## 🏆 Success!

**When complete, you should be able to:**
1. ✅ See 96 data points per day instead of 24
2. ✅ See prices update every 15 minutes
3. ✅ Switch interval duration by changing ONE constant
4. ✅ Have clean, generic, maintainable code
5. ✅ Support any future interval changes easily

---

**Ready to start Phase 1!** 🚀
