# Type Hint Coverage

Add type hints where missing.

## Why

Better IDE support and error catching.

## Files to Check

Run `mypy custom_components/ge_spot --strict` to find gaps

## Changes Needed

- Add return type hints to functions
- Replace `Dict[str, Any]` with TypedDict where possible
- Add parameter type hints
