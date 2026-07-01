"""Pure consumption-weighted average accumulator.

This module is deliberately free of any Home Assistant imports so the
accumulation, period-reset, and benchmark math can be unit-tested in isolation.
The Home Assistant sensor wrapper lives in ``sensor/price.py``.

The accumulator answers a single question: *did you beat the market average?*
Over the current period (a day or a month) it tracks two running averages:

* the **consumption-weighted** average price you actually paid, weighting each
  interval's spot price by the energy you consumed during it, and
* the **simple** (unweighted) average spot price over the same elapsed
  intervals, used as the benchmark.

If the weighted average is below the simple average you shifted consumption into
cheaper-than-average intervals, i.e. you beat the average.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

__all__ = ["WeightedAverageAccumulator"]


@dataclass
class WeightedAverageAccumulator:
    """Running consumption-weighted and simple price averages for one period.

    All prices are stored in whatever unit the caller supplies (the integration
    passes the configured display unit, e.g. SEK/kWh or öre/kWh); the
    accumulator performs no unit conversion. Energy is in kWh.

    ``last_energy`` is the meter baseline used to derive per-update consumption
    deltas. It is intentionally NOT cleared by :meth:`maybe_reset`: an energy
    meter is monotonic across a midnight/month boundary, so the baseline must
    survive a period reset — otherwise the first delta of the new period would
    be swallowed as a fresh baseline and that consumption lost.

    Args:
        period: Either ``"daily"`` or ``"monthly"`` — selects the granularity of
            the period key used to detect rollovers.
    """

    period: str
    cost_acc: float = 0.0
    energy_acc: float = 0.0
    simple_sum: float = 0.0
    simple_count: int = 0
    period_start_key: Optional[str] = None
    last_interval_key: Optional[str] = None
    last_energy: Optional[float] = None

    @staticmethod
    def period_key(period: str, now_local: datetime) -> str:
        """Return the rollover key for ``now_local`` at the given granularity.

        Monthly periods roll over when the calendar month changes, daily periods
        when the calendar date changes. ``now_local`` must already be expressed
        in the timezone the period boundaries are defined in (the display/area
        timezone), so callers convert before passing it in.
        """
        return now_local.strftime("%Y-%m" if period == "monthly" else "%Y-%m-%d")

    def maybe_reset(self, now_local: datetime) -> bool:
        """Reset the accumulators if ``now_local`` falls in a new period.

        Zeroes the cost/energy/simple accumulators and clears
        ``last_interval_key`` so benchmark sampling restarts, but preserves
        ``last_energy`` (see the class docstring). On the first ever call it just
        records the current period key, with nothing to clear.

        Returns:
            True if a reset (or the initial key assignment) occurred.
        """
        key = self.period_key(self.period, now_local)
        if key == self.period_start_key:
            return False
        self.cost_acc = 0.0
        self.energy_acc = 0.0
        self.simple_sum = 0.0
        self.simple_count = 0
        self.last_interval_key = None
        self.period_start_key = key
        return True

    def add_energy(
        self, new_kwh: float, price: Optional[float], now_local: datetime
    ) -> None:
        """Fold one energy-meter reading into the weighted average.

        Computes the consumption since the last reading and prices it at the
        current interval price. Rolls the period over first so consumption is
        attributed to the correct period.

        Edge cases:
            * No baseline yet → record the reading as the baseline; nothing to
              accumulate.
            * ``new_kwh`` < baseline → the meter reset (or was replaced); adopt
              the new value as the baseline and skip the bogus negative delta.
            * ``price`` is None (no price for the current interval) → keep the
              baseline so the unpriced energy is folded into the next priced
              delta rather than being dropped.
        """
        self.maybe_reset(now_local)

        if self.last_energy is None:
            self.last_energy = new_kwh
            return

        delta = new_kwh - self.last_energy
        if delta < 0:
            # Meter reset/replacement — re-baseline, don't count a negative jump.
            self.last_energy = new_kwh
            return

        if price is None:
            # Can't price this energy yet; leave the baseline so it is captured
            # by the next priced delta instead of being lost.
            return

        self.last_energy = new_kwh
        if delta > 0:
            self.cost_acc += delta * price
            self.energy_acc += delta

    def sample_simple(
        self, dedup_key: str, price: Optional[float], now_local: datetime
    ) -> None:
        """Add the current interval's price to the simple (benchmark) average.

        Counts each interval exactly once via ``dedup_key``. The caller supplies
        a date-qualified interval key so the monthly benchmark keeps counting
        across days (a bare HH:MM repeats daily). Rolls the period over first.
        """
        self.maybe_reset(now_local)
        if price is None:
            return
        if dedup_key != self.last_interval_key:
            self.simple_sum += price
            self.simple_count += 1
            self.last_interval_key = dedup_key

    @property
    def weighted(self) -> Optional[float]:
        """Consumption-weighted average price, or None before any consumption."""
        if self.energy_acc <= 0:
            return None
        return self.cost_acc / self.energy_acc

    @property
    def simple(self) -> Optional[float]:
        """Unweighted average spot price over elapsed intervals, or None."""
        if self.simple_count <= 0:
            return None
        return self.simple_sum / self.simple_count
