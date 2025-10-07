# Currency Conversion E2E Tests

Test full flow from API response to converted prices.

## Why

Currency conversion touches many components.

## Files to Check

- `custom_components/ge_spot/price/currency_service.py`
- `custom_components/ge_spot/price/currency_converter.py`
- `custom_components/ge_spot/coordinator/data_processor.py`

## What to Create

`tests/pytest/integration/test_currency_e2e.py`

## Key Scenarios

- Full pipeline: API → parser → conversion → sensor
- ECB rate fetch failure (use stale rates)
- Unsupported currency handling
- No double-conversion bugs
