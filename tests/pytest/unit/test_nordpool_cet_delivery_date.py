"""Regression: Nord Pool must request the delivery date in CET, not UTC.

Nord Pool's ``date`` query parameter is the delivery date in the market's local
(CET/CEST) time. Computing it from the UTC date means that for the ~2 hours
after local midnight (when the CET date is already the next day but UTC is not),
the integration requests the previous delivery day — so the new day's prices are
classified as "neither today nor tomorrow" and every nordpool area shows no price
until UTC catches up. These tests freeze the clock across that boundary.
"""

from unittest.mock import AsyncMock

from custom_components.ge_spot.api.nordpool import NordpoolAPI


def _client_capturing_dates():
    calls = []

    async def fake_fetch(url, params=None, **kwargs):
        calls.append((params or {}).get("date"))
        # Non-empty so the tomorrow-availability check treats it as published
        # (an empty list would trigger fetch_with_retry's retry loop).
        return {"multiAreaEntries": [{}]}

    client = AsyncMock()
    client.fetch = AsyncMock(side_effect=fake_fetch)
    return client, calls


async def _dates_fetched():
    api = NordpoolAPI()
    client, calls = _client_capturing_dates()
    try:
        await api._fetch_data(client, "SE4", reference_time=None)
    except Exception:  # pragma: no cover - we only assert the captured params
        pass
    return calls


async def test_uses_cet_date_just_after_local_midnight(freezer):
    # 22:08 UTC == 00:08 Oslo (CEST) on the next calendar day.
    freezer.move_to("2026-06-26 22:08:00")
    dates = await _dates_fetched()
    # The "today" delivery date must be the CET date (2026-06-27), NOT the UTC
    # date (2026-06-26). Before the fix, only 2026-06-26 was ever requested.
    assert "2026-06-27" in dates, f"expected CET today 2026-06-27 in {dates}"
    assert "2026-06-26" not in dates, f"must not request UTC date 2026-06-26: {dates}"


async def test_daytime_date_unchanged(freezer):
    # 12:00 UTC == 14:00 Oslo (CEST), same calendar day as UTC.
    freezer.move_to("2026-06-26 12:00:00")
    dates = await _dates_fetched()
    # Today is unchanged (2026-06-26); past 13:00 CET tomorrow is also requested.
    assert "2026-06-26" in dates, f"expected today 2026-06-26 in {dates}"
    assert "2026-06-27" in dates, f"expected tomorrow 2026-06-27 in {dates}"
