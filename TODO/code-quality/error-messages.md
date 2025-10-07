# Error Message Improvements

Make error messages more actionable.

## Why

Help users troubleshoot issues.

## Files to Check

- `custom_components/ge_spot/api/base/error_handler.py`
- All API modules

## Changes Needed

- Add troubleshooting hints to errors
- Include context (what was being attempted)
- Suggest fixes when possible

## Example

```python
# Before
raise APIError("Failed to fetch data")

# After
raise APIError(
    f"Failed to fetch data for area {area} from {source}. "
    f"Check if area code is valid and API key is configured. "
    f"See logs for details."
)
```
