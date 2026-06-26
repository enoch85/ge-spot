"""Regression test: ENTSO-E must resolve mixed-case area codes.

ENTSOE_MAPPING contains mixed-case keys for the Italian bidding zones
("IT-North", "IT-Centre-South", ...). The client previously looked them up
with ``ENTSOE_MAPPING.get(area.upper())``, so e.g. "IT-North".upper() ==
"IT-NORTH" never matched and those areas raised "not supported for ENTSO-E",
even though their EIC codes are present. This pins the resolution.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from custom_components.ge_spot.api.entsoe import EntsoeAPI


@pytest.mark.parametrize(
    "area,expected_eic",
    [
        ("IT-North", "10Y1001A1001A71M"),
        ("IT-Centre-South", "10Y1001A1001A788"),
        ("IT-South", "10Y1001A1001A885"),
        ("IT-Sardinia", "10Y1001A1001A73I"),
        ("IT-Sicily", "10Y1001A1001A74G"),
        ("it-north", "10Y1001A1001A71M"),  # case-variant input still resolves
        ("GB", "10Y1001A1001A59C"),  # all-upper key keeps working
    ],
)
async def test_entsoe_resolves_mixed_case_area(area, expected_eic):
    """_fetch_data must map the area to its EIC and never reject mixed-case zones."""
    api = EntsoeAPI(config={"api_key": "dummy"})
    client = AsyncMock()
    client.fetch = AsyncMock(
        return_value="<Publication_MarketDocument></Publication_MarketDocument>"
    )
    ref = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)

    try:
        await api._fetch_data(client, area, ref)
    except ValueError as e:  # pragma: no cover - must not be the "not supported" path
        assert "not supported" not in str(e), f"area {area!r} wrongly rejected: {e}"

    assert client.fetch.await_count > 0, "no ENTSO-E request was issued"
    for call in client.fetch.await_args_list:
        params = call.kwargs.get("params", {})
        assert params.get("in_Domain") == expected_eic
        assert params.get("out_Domain") == expected_eic
