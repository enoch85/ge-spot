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


def test_a03_sparse_pt15m_forward_fills_to_96():
    """A sparse A03 PT15M curve (omitted positions) fills to a full 96-slot day.

    Uses the exact gap pattern observed in live ENTSO-E IT zone documents.
    """
    expected = TimeInterval.get_intervals_per_day()  # 96
    missing = {3, 5, 14, 24, 38, 39, 46, 77, 86}  # 87/96, as seen live
    points = [(p, 100.0 + p) for p in range(1, expected + 1) if p not in missing]
    assert len(points) == 87

    prices = EntsoeParser().parse(_document("PT15M", points))["interval_raw"]
    assert (
        len(prices) == expected
    ), f"sparse A03 should fill to {expected}, got {len(prices)}"


def test_a03_omitted_position_is_exact_copy_no_drift():
    """An omitted A03 position must equal the previous position's EXACT value.

    A03 omits a Point only when its value is unchanged, so the fill is a pure
    decimal copy of the prior value -- never an interpolation/average.
    """
    # Real-style many-decimal prices; positions 3 and 5 omitted.
    present = {1: 147.17, 2: 137.91, 4: 134.80, 6: 134.19, 7: 133.10}
    points = [(p, present[p]) for p in present]
    points += [(p, 50.0 + p) for p in range(8, 97)]  # fill out a full day

    prices = EntsoeParser().parse(_document("PT15M", points))["interval_raw"]
    assert len(prices) == TimeInterval.get_intervals_per_day()
    # pos 3 (22:30) omitted -> exact copy of pos 2, NOT interpolated toward pos 4
    assert prices["2026-06-26T22:30:00+00:00"] == 137.91
    # pos 5 (23:00) omitted -> exact copy of pos 4
    assert prices["2026-06-26T23:00:00+00:00"] == 134.80


def test_a03_trailing_omission_filled_to_period_end():
    """Trailing omitted positions fill to the Period's end (not just last point)."""
    expected = TimeInterval.get_intervals_per_day()  # 96
    points = [(p, 200.0 + p) for p in range(1, 91)]  # only positions 1..90 present

    prices = EntsoeParser().parse(_document("PT15M", points))["interval_raw"]
    assert (
        len(prices) == expected
    ), f"trailing gaps should fill to {expected}, got {len(prices)}"
    # the final slots inherit position 90's exact value (290.0)
    assert prices["2026-06-27T21:45:00+00:00"] == 290.0
