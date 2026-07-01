"""Unit tests for the pure consumption-weighted average accumulator.

These exercise the accumulation, period-reset, benchmark de-duplication and
edge-case math without any Home Assistant scaffolding. The headline test is
``test_full_month_consumption_math`` which simulates a realistic month of
15-minute consumption and independently recomputes the expected weighted and
simple averages to prove the sensor reports the right numbers.
"""

from datetime import datetime, timezone

import pytest

from custom_components.ge_spot.sensor.consumption import WeightedAverageAccumulator


def _utc(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _price_curve():
    """96 interval prices: cheap overnight, pricey in the evening peak."""
    prices = []
    for i in range(96):
        hour = i // 4
        if 0 <= hour < 6:
            prices.append(0.50)  # cheap night
        elif 17 <= hour < 21:
            prices.append(2.00)  # evening peak
        else:
            prices.append(1.00)  # shoulder
    return prices


def _consumption_curve():
    """96 interval kWh: load-shifted into the cheap overnight window."""
    cons = []
    for i in range(96):
        hour = i // 4
        if 0 <= hour < 6:
            cons.append(2.0)  # e.g. EV charging overnight
        elif 17 <= hour < 21:
            cons.append(0.1)  # avoid the peak
        else:
            cons.append(0.5)
    return cons


# --- Core accumulation -----------------------------------------------------


def test_baseline_then_weighted_average():
    acc = WeightedAverageAccumulator(period="daily")
    now = _utc(2026, 6, 1, 12, 0)

    acc.add_energy(50.0, 1.0, now)  # first reading is the baseline only
    assert acc.weighted is None

    acc.add_energy(51.0, 2.0, now)  # +1 kWh @ 2.0
    acc.add_energy(53.0, 1.0, now)  # +2 kWh @ 1.0
    assert acc.energy_acc == pytest.approx(3.0)
    assert acc.cost_acc == pytest.approx(1 * 2.0 + 2 * 1.0)  # 4.0
    assert acc.weighted == pytest.approx(4.0 / 3.0)


def test_meter_reset_rebaselines_without_negative():
    acc = WeightedAverageAccumulator(period="daily")
    now = _utc(2026, 6, 1, 12, 0)
    acc.add_energy(100.0, 1.0, now)  # baseline
    acc.add_energy(102.0, 1.0, now)  # +2 kWh
    acc.add_energy(5.0, 1.0, now)  # meter reset/replacement -> re-baseline
    assert acc.energy_acc == pytest.approx(2.0)  # unchanged, no negative jump
    acc.add_energy(7.0, 1.0, now)  # +2 kWh from the new baseline of 5
    assert acc.energy_acc == pytest.approx(4.0)


def test_price_none_folds_into_next_priced_delta():
    acc = WeightedAverageAccumulator(period="daily")
    now = _utc(2026, 6, 1, 12, 0)
    acc.add_energy(10.0, 1.0, now)  # baseline
    acc.add_energy(12.0, None, now)  # price unknown -> keep baseline, skip
    assert acc.energy_acc == pytest.approx(0.0)
    assert acc.last_energy == pytest.approx(10.0)
    acc.add_energy(13.0, 2.0, now)  # delta 13-10 = 3 kWh @ 2.0 (folds the gap)
    assert acc.energy_acc == pytest.approx(3.0)
    assert acc.cost_acc == pytest.approx(6.0)


def test_empty_accumulator_returns_none():
    acc = WeightedAverageAccumulator(period="monthly")
    assert acc.weighted is None
    assert acc.simple is None


# --- Period reset ----------------------------------------------------------


def test_daily_reset_clears_accumulators_but_preserves_meter_baseline():
    acc = WeightedAverageAccumulator(period="daily")
    d1 = _utc(2026, 6, 1, 10, 0)
    acc.add_energy(100.0, 1.0, d1)  # baseline
    acc.add_energy(102.0, 1.0, d1)  # +2 kWh @ 1.0
    assert acc.weighted == pytest.approx(1.0)

    # New day: accumulators reset, but the monotonic meter baseline survives,
    # so the first delta of the new day is 105-102 = 3 (not 105).
    d2 = _utc(2026, 6, 2, 0, 0)
    acc.add_energy(105.0, 2.0, d2)
    assert acc.energy_acc == pytest.approx(3.0)
    assert acc.cost_acc == pytest.approx(6.0)
    assert acc.weighted == pytest.approx(2.0)


def test_monthly_does_not_reset_within_the_month():
    acc = WeightedAverageAccumulator(period="monthly")
    acc.add_energy(0.0, 1.0, _utc(2026, 6, 1, 0, 0))  # baseline
    acc.add_energy(1.0, 1.0, _utc(2026, 6, 1, 0, 0))
    acc.add_energy(2.0, 1.0, _utc(2026, 6, 20, 0, 0))  # later same month
    assert acc.energy_acc == pytest.approx(2.0)
    # New month resets first, then folds in this reading's delta (3-2=1) using
    # the preserved meter baseline -> 1.0, not 3.0 (which is what no reset gives).
    acc.add_energy(3.0, 1.0, _utc(2026, 7, 1, 0, 0))
    assert acc.energy_acc == pytest.approx(1.0)


# --- Benchmark sampling ----------------------------------------------------


def test_monthly_benchmark_counts_across_days():
    """Regression: a bare HH:MM key would freeze the monthly benchmark at day 1."""
    acc = WeightedAverageAccumulator(period="monthly")
    for day in range(1, 4):
        for i in range(96):
            hour, minute = i // 4, (i % 4) * 15
            now = _utc(2026, 6, day, hour, minute)
            dedup = f"2026-06-{day:02d}|{hour:02d}:{minute:02d}"
            acc.sample_simple(dedup, 1.0, now)
    assert acc.simple_count == 96 * 3


def test_daily_benchmark_converges_to_full_day_average():
    prices = _price_curve()
    acc = WeightedAverageAccumulator(period="daily")
    for i in range(96):
        hour, minute = i // 4, (i % 4) * 15
        dedup = f"2026-06-01|{hour:02d}:{minute:02d}"
        acc.sample_simple(dedup, prices[i], _utc(2026, 6, 1, hour, minute))
    assert acc.simple_count == 96
    assert acc.simple == pytest.approx(sum(prices) / 96)  # == market day average


# --- End-to-end month simulation (the math check) --------------------------


def test_full_month_consumption_math():
    """Simulate a month of load-shifted consumption and verify the numbers.

    Independently recomputes the consumption-weighted and simple averages and
    asserts the accumulator matches, that the benchmark counts every interval,
    and that load-shifting into cheap hours genuinely beats the market average.
    """
    prices = _price_curve()
    cons = _consumption_curve()
    days = 30

    acc = WeightedAverageAccumulator(period="monthly")
    meter = 1000.0
    acc.last_energy = meter  # establish the starting meter baseline

    for day in range(1, days + 1):
        for i in range(96):
            hour, minute = i // 4, (i % 4) * 15
            now = _utc(2026, 6, day, hour, minute)
            dedup = f"2026-06-{day:02d}|{hour:02d}:{minute:02d}"
            price = prices[i]
            # Benchmark: one sample per interval. Consumption: meter advances.
            acc.sample_simple(dedup, price, now)
            meter += cons[i]
            acc.add_energy(meter, price, now)

    sum_c = sum(cons)
    sum_cp = sum(c * p for c, p in zip(cons, prices))
    expected_weighted = sum_cp / sum_c
    expected_simple = sum(prices) / 96

    assert acc.simple_count == 96 * days
    assert acc.energy_acc == pytest.approx(sum_c * days)
    assert acc.weighted == pytest.approx(expected_weighted)
    assert acc.simple == pytest.approx(expected_simple)

    # Sanity: load-shifting into the cheap window beats the simple average.
    assert acc.weighted < acc.simple
    savings = acc.simple - acc.weighted
    assert savings == pytest.approx(expected_simple - expected_weighted)
    assert savings > 0
