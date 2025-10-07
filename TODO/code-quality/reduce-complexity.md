# Reduce Complexity in UnifiedPriceManager

Break down large methods into smaller ones.

## Why

Easier to understand and maintain.

## Files to Check

- `custom_components/ge_spot/coordinator/unified_price_manager.py`

## Changes Needed

`fetch_data()` method is ~200 lines - split into:
- `_should_fetch()`
- `_return_cached_data()`
- `_fetch_with_fallback()`
