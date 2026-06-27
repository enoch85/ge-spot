"""Regression tests for ENTSO-E coarse-resolution Point expansion.

Many ENTSO-E day-ahead zones publish hourly (PT60M, 24 points). The
integration works on a 15-minute grid (96 slots/day), so each hourly point
must be expanded across the four 15-min slots it covers; otherwise the day
parses as 24/96 and the coordinator reports "Incomplete data". Zones that
already publish 96 PT15M points must be unaffected.
"""

from custom_components.ge_spot.api.parsers.entsoe_parser import EntsoeParser
from custom_components.ge_spot.const.time import TimeInterval

NS = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"


def _document(
    resolution,
    points,
    start="2026-06-26T22:00Z",
    end="2026-06-27T22:00Z",
):
    body = "".join(
        f"<Point><position>{pos}</position>"
        f"<price.amount>{price}</price.amount></Point>"
        for pos, price in points
    )
    return (
        f'<Publication_MarketDocument xmlns="{NS}">'
        "<TimeSeries><businessType>A44</businessType>"
        "<currency_Unit.name>EUR</currency_Unit.name>"
        "<price_Measure_Unit.name>MWH</price_Measure_Unit.name>"
        "<curveType>A03</curveType>"
        f"<Period><timeInterval><start>{start}</start><end>{end}</end>"
        f"</timeInterval><resolution>{resolution}</resolution>{body}</Period>"
        "</TimeSeries></Publication_MarketDocument>"
    )


def test_hourly_pt60m_expands_to_full_15min_day():
    """24 hourly PT60M Points must expand to 96 fifteen-minute intervals."""
    expected = TimeInterval.get_intervals_per_day()  # 96
    document = _document("PT60M", [(p, 50.0 + p) for p in range(1, 25)])

    result = EntsoeParser().parse(document)
    prices = result["interval_raw"]

    assert len(prices) == expected, (
        f"PT60M with 24 hourly Points should expand to {expected} intervals, "
        f"got {len(prices)}"
    )
    # The hourly price is held constant across its four 15-min sub-slots.
    assert prices["2026-06-26T22:00:00+00:00"] == 51.0
    assert prices["2026-06-26T22:15:00+00:00"] == 51.0
    assert prices["2026-06-26T22:45:00+00:00"] == 51.0
    assert prices["2026-06-26T23:00:00+00:00"] == 52.0


def test_native_pt15m_full_day_is_unchanged():
    """A complete 96-point PT15M curve is unaffected (1 slot per point)."""
    expected = TimeInterval.get_intervals_per_day()  # 96
    document = _document("PT15M", [(p, 10.0 + p) for p in range(1, expected + 1)])

    result = EntsoeParser().parse(document)
    prices = result["interval_raw"]

    assert len(prices) == expected
    assert prices["2026-06-26T22:00:00+00:00"] == 11.0
    assert prices["2026-06-27T21:45:00+00:00"] == 10.0 + expected
