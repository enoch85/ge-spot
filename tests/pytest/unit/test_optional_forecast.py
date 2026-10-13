"""Unavailable forecasts must not delay or discard usable current prices."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from custom_components.ge_spot.api.energi_data import EnergiDataAPI
from custom_components.ge_spot.api.entsoe import EntsoeAPI
from custom_components.ge_spot.api.nordpool import NordpoolAPI


@pytest.mark.parametrize("api_class", [NordpoolAPI, EntsoeAPI, EnergiDataAPI])
@freeze_time("2026-10-13T15:00:00Z")
async def test_unpublished_forecast_preserves_today_without_waiting(api_class):
    async def response(url, *, params, **kwargs):
        if api_class is NordpoolAPI:
            return (
                {"multiAreaEntries": [{"deliveryArea": "SE4"}]}
                if params["date"] == "2026-10-13"
                else {"status": 204}
            )
        if api_class is EntsoeAPI:
            return (
                "<Publication_MarketDocument>today</Publication_MarketDocument>"
                if params["periodStart"].startswith("20261013")
                else {"status": 204}
            )
        return (
            {"records": [{"TimeUTC": "2026-10-13T14:00:00", "SpotPriceDKK": 100}]}
            if params["start"].startswith("2026-10-13")
            else {"records": []}
        )

    client = MagicMock()
    client.fetch = AsyncMock(side_effect=response)
    api = api_class(config={"api_key": "test-key"})
    api.needs_extended_date_range = MagicMock(
        return_value={"need_yesterday": False, "need_tomorrow": True}
    )
    with patch(f"{api_class.__module__}.ApiClient", return_value=client), patch(
        "asyncio.sleep",
        side_effect=AssertionError("Optional forecast request must not wait"),
    ):
        data = await api.fetch_raw_data(
            "DK1" if api_class is EnergiDataAPI else "SE4",
            session=MagicMock(),
            reference_time=datetime.now(timezone.utc),
        )

    assert data and data["raw_data"]
    assert client.fetch.await_count == 2
    if api_class is not EntsoeAPI:
        assert data["raw_data"]["tomorrow"] is None


@pytest.mark.parametrize(
    "instant,delivery_date",
    [
        ("2026-10-13T22:08:00Z", "2026-10-14"),
        ("2026-01-13T23:08:00Z", "2026-01-14"),
        ("2026-10-13T10:08:00Z", "2026-10-13"),
    ],
)
@pytest.mark.parametrize("api_class", [NordpoolAPI, EnergiDataAPI])
async def test_current_delivery_date_at_local_midnight(
    instant, delivery_date, api_class
):
    client = MagicMock(
        fetch=AsyncMock(
            return_value={
                "multiAreaEntries": [{"deliveryArea": "SE4"}],
                "records": [{"SpotPriceDKK": 100}],
            }
        )
    )
    api = api_class()
    with freeze_time(instant), patch(
        f"{api_class.__module__}.ApiClient", return_value=client
    ):
        result = await api.fetch_raw_data("DK1", session=MagicMock())
    assert result and result["raw_data"]["today"]
    params = client.fetch.call_args.kwargs["params"]
    assert params.get("date", params.get("start", "").split("T")[0]) == delivery_date
