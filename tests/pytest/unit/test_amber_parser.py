"""Tests for the Amber parser, incl. the DataProcessor wrapper-dict path."""

from custom_components.ge_spot.api.parsers.amber_parser import AmberParser
from custom_components.ge_spot.const.currencies import Currency

SAMPLE = [
    {"type": "ActualInterval", "startTime": "2026-06-25T00:00:00Z", "perKwh": 25.0},
    {"type": "ActualInterval", "startTime": "2026-06-25T00:30:00Z", "perKwh": 30.5},
]


def test_parse_raw_list():
    """Parser extracts prices from the bare API list (the inline parse path)."""
    result = AmberParser().parse(SAMPLE)
    assert len(result["interval_raw"]) == 2
    assert result["currency"] == Currency.AUD


def test_parse_direct_data_key():
    """Parser handles a dict whose 'data' key holds the list."""
    result = AmberParser().parse({"data": SAMPLE})
    assert len(result["interval_raw"]) == 2


def test_parse_fetch_raw_data_wrapper():
    """Regression: parser must read the wrapper AmberAPI.fetch_raw_data returns.

    The DataProcessor re-parses that wrapper (``parser.parse(data)``). Before the
    fix the price list was nested under ``raw_data -> data`` and was never found,
    so Amber produced zero prices end-to-end.
    """
    wrapper = {
        "interval_raw": {},  # discarded by the DataProcessor, which re-parses
        "timezone": "Australia/Sydney",
        "currency": Currency.AUD,
        "source_name": "amber",
        "raw_data": {
            "data": SAMPLE,
            "timestamp": "2026-06-25T00:00:00+00:00",
            "area": "12345",
            "date_range": {"start": "2026-06-24", "end": "2026-06-26"},
        },
        "data_source": "amber",
        "attempted_sources": ["amber"],
    }
    result = AmberParser().parse(wrapper)
    assert len(result["interval_raw"]) == 2, "Amber wrapper dict must yield prices"


def test_parse_normalizes_perkwh_cents_to_aud_per_kwh():
    """'perKwh' (cents/kWh) is normalized to AUD/kWh (25 c/kWh -> 0.25 AUD/kWh).

    Without this, the DataProcessor reads the value as AUD/MWh and the final
    price is ~10x too low.
    """
    result = AmberParser().parse(
        [{"startTime": "2026-06-25T00:00:00Z", "perKwh": 25.0}]
    )
    assert list(result["interval_raw"].values()) == [0.25]


def test_parse_rrp_fallback_normalizes_to_aud_per_kwh():
    """'rrp' (AUD/MWh) also normalizes to AUD/kWh (100 AUD/MWh -> 0.10 AUD/kWh)."""
    result = AmberParser().parse([{"startTime": "2026-06-25T00:00:00Z", "rrp": 100.0}])
    assert list(result["interval_raw"].values()) == [0.10]
