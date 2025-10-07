# DST Transition Tests

Test that the system handles daylight saving time correctly (spring forward/fall back).

## Why

March and October time changes affect interval counts (92 or 100 instead of 96).

## Files to Check

- `custom_components/ge_spot/timezone/timezone_converter.py`
- `custom_components/ge_spot/const/time.py` (has DST interval constants)

## What to Create

`tests/pytest/unit/test_dst_transitions.py`

## Key Scenarios

- Spring forward: Verify 92 intervals on transition day
- Fall back: Verify 100 intervals on transition day
- Timezone conversion during transitions
- Cross-source consistency (all APIs produce same interval keys)
