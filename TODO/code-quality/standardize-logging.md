# Standardize Logging

Make logs consistent across all modules.

## Why

Currently mix of formats, hard to parse.

## Files to Check

- All files in `custom_components/ge_spot/`
- Especially `api/*.py` and `coordinator/*.py`

## Changes Needed

1. Create `utils/logging_utils.py` with LogFormat class
2. Add trace IDs for request tracking
3. Update all modules to use consistent format
4. Add performance logging (duration tracking)

## Example

```python
# Before
_LOGGER.debug(f"Fetching {area}")

# After
_LOGGER.debug(LogFormat.area_log(area, "Fetching data", source="nordpool"))
```
