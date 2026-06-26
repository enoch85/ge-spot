"""Regression test: ComEd must declare its source energy unit as kWh.

ComEd's real-time feed reports prices in cents/kWh (already per-kWh). The
adapter's ``fetch_raw_data`` result is what ``DataProcessor`` reads to decide
the source energy unit:

    source_unit = data.get("source_unit", EnergyUnit.MWH)

If ``source_unit`` is missing it defaults to MWh, and the downstream
MWh->kWh conversion divides every ComEd price by 1000. This test pins the
contract so the unit declaration cannot silently regress again.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.ge_spot.api.comed import ComedAPI
from custom_components.ge_spot.const.energy import EnergyUnit


async def test_comed_fetch_raw_data_declares_kwh_source_unit():
    """fetch_raw_data must set source_unit=kWh so prices are not /1000."""
    api = ComedAPI()

    # Stub the parser so the test targets fetch_raw_data's result construction
    # (the fix site), not parser internals.
    fake_parser = MagicMock()
    fake_parser.parse.return_value = {"interval_raw": {"2026-06-26T12:00:00": 2.5}}
    fake_parser.extract_metadata.return_value = {
        "timezone": "America/Chicago",
        "currency": "cents",
    }

    # _fetch_data is mocked, so the injected session is never actually used;
    # it only needs to be non-None to satisfy the ApiClient session guard.
    with patch.object(
        api, "_fetch_data", AsyncMock(return_value=[{"price": "2.5"}])
    ), patch.object(api, "get_parser_for_area", return_value=fake_parser):
        result = await api.fetch_raw_data(area="5minutefeed", session=MagicMock())

    assert result, "fetch_raw_data returned empty result"
    assert result.get("source_unit") == EnergyUnit.KWH
    # Sanity: ComEd is reported in cents (per kWh), not MWh.
    assert result.get("currency") == "cents"
