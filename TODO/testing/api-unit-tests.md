# Individual API Unit Tests

Each of the 9 APIs needs dedicated unit tests.

## Why

Currently hard to debug which API is failing.

## Files to Check

- `custom_components/ge_spot/api/nordpool.py`
- `custom_components/ge_spot/api/entsoe.py`
- `custom_components/ge_spot/api/energi_data.py`
- `custom_components/ge_spot/api/amber.py`
- `custom_components/ge_spot/api/comed.py`
- `custom_components/ge_spot/api/omie.py`
- `custom_components/ge_spot/api/stromligning.py`
- `custom_components/ge_spot/api/energy_charts.py`
- `custom_components/ge_spot/api/aemo.py`

## What to Create

`tests/pytest/unit/test_<api_name>_api.py` for each API

## Key Scenarios (per API)

- Successful fetch
- Timeout handling
- Invalid area code
- API error (500, 429, etc.)
- Parser integration
