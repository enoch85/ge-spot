# Cache Manager Tests

Test caching prevents data mutation and handles staleness.

## Why

Cache uses deep copy to avoid bugs - needs verification.

## Files to Check

- `custom_components/ge_spot/coordinator/cache_manager.py`

## What to Create

`tests/pytest/unit/test_cache_manager.py`

## Key Scenarios

- Deep copy prevents mutation
- TTL expiration works
- Stale data detected
- Per-area isolation
