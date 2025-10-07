# Fallback Chain Integration Tests

Test that switching between APIs works when one fails.

## Why

Primary APIs fail sometimes, need to ensure backup APIs kick in.

## Files to Check

- `custom_components/ge_spot/coordinator/fallback_manager.py`
- `custom_components/ge_spot/coordinator/unified_price_manager.py`

## What to Create

`tests/pytest/integration/test_fallback_chain.py`

## Key Scenarios

- Primary fails → secondary succeeds
- All APIs fail → use cache
- Priority order respected
- Error propagation works correctly
