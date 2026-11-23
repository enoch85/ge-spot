"""Regression test: Stromligning must send the grid company as ``supplierId``.

The Stromligning prices endpoint selects the grid company with ``supplierId``.
The client previously sent ``supplier=``, which the API ignores, so the
returned prices were for the price area alone and contained no grid tariff.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

from custom_components.ge_spot.api.stromligning import StromligningAPI
from custom_components.ge_spot.const.config import Config


async def test_stromligning_requests_prices_with_supplier_id():
    """_fetch_data must pass the configured supplier ID as supplierId."""
    api = StromligningAPI(config={Config.CONF_STROMLIGNING_SUPPLIER: "radius_c"})
    client = AsyncMock()
    client.fetch = AsyncMock(return_value={"prices": []})
    ref = datetime(2026, 11, 22, 16, 0, tzinfo=timezone.utc)

    await api._fetch_data(client, "DK2", ref)

    client.fetch.assert_awaited_once()
    query = parse_qs(urlparse(client.fetch.await_args.args[0]).query)
    assert query == {"priceArea": ["DK2"], "supplierId": ["radius_c"]}
