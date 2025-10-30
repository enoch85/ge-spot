"""Data models for price data with computed properties.

This module implements a compute-on-demand architecture where only source data
is stored in cache, and all metadata/statistics are computed as properties.
This eliminates cache coherency bugs and simplifies maintenance.

Core Principle: Single Source of Truth
- Store ONLY immutable source data (interval prices, metadata)
- Compute EVERYTHING else on-demand (validity, statistics, flags)
- Migration logic in ONE place: migrate_to_new_day()
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from homeassistant.util import dt as dt_util

from ..api.base.data_structure import PriceStatistics
from ..const.time import TimeInterval
from .data_validity import DataValidity, calculate_data_validity

_LOGGER = logging.getLogger(__name__)


@dataclass
class IntervalPriceData:
    """Source data for interval prices with computed properties.

    This class stores ONLY source data in cache. All metadata is computed
    on-demand as properties, ensuring cache coherency and eliminating sync bugs.

    The key insight: If you only store raw prices and metadata, everything else
    can be calculated from that. No need to store validity, statistics, flags, etc.

    Example:
        # Create with source data
        data = IntervalPriceData(
            today_interval_prices={"14:00": 0.25, "14:15": 0.28, ...},
            tomorrow_interval_prices={"00:00": 0.20, ...},
            source="nordpool",
            area="SE3",
            _tz_service=tz_service
        )

        # Properties compute automatically
        validity = data.data_validity  # Computed from interval counts
        stats = data.statistics  # Computed from price values
        has_tomorrow = data.has_tomorrow_prices  # Computed from dict existence

        # Migration is trivial
        data.migrate_to_new_day()  # Properties auto-update!
    """

    # ========== SOURCE DATA (stored in cache) ==========

    # Price data - the core source of truth
    today_interval_prices: Dict[str, float] = field(default_factory=dict)
    tomorrow_interval_prices: Dict[str, float] = field(default_factory=dict)
    today_raw_prices: Dict[str, float] = field(default_factory=dict)
    tomorrow_raw_prices: Dict[str, float] = field(default_factory=dict)

    # Source metadata
    source: str = ""
    area: str = ""
    source_currency: str = "EUR"
    target_currency: str = "SEK"
    source_timezone: str = "UTC"
    target_timezone: str = "UTC"

    # Currency conversion data
    ecb_rate: Optional[float] = None
    ecb_updated: Optional[str] = None

    # Display configuration
    vat_rate: float = 0.0
    vat_included: bool = False
    display_unit: str = "EUR/kWh"

    # Timestamps
    fetched_at: Optional[str] = None
    last_updated: Optional[str] = None

    # Migration tracking
    migrated_from_tomorrow: bool = False
    original_cache_date: Optional[str] = None

    # Fallback information
    attempted_sources: list = field(default_factory=list)
    fallback_sources: list = field(default_factory=list)
    using_cached_data: bool = False

    # Attribution (for sources requiring it)
    data_source_attribution: Optional[str] = None

    # Raw API data (for debugging)
    raw_data: Optional[Dict[str, Any]] = None
    raw_interval_prices_original: Optional[Dict[str, float]] = None

    # Timezone service (NOT serialized to cache)
    _tz_service: Optional[Any] = field(default=None, repr=False, compare=False)

    # ========== COMPUTED PROPERTIES (NOT stored in cache) ==========

    @property
    def data_validity(self) -> DataValidity:
        """Calculate data validity from interval prices.

        Always computed fresh from source data, ensuring accuracy.
        This eliminates the Issue #44 bug where validity wasn't recalculated
        after midnight migration.

        Returns:
            DataValidity object with computed fields
        """
        if not self._tz_service:
            _LOGGER.warning(
                "Cannot calculate data_validity without timezone service. "
                "Returning empty validity."
            )
            return DataValidity()

        try:
            now = dt_util.now()
            current_interval_key = self._tz_service.get_current_interval_key()

            return calculate_data_validity(
                interval_prices=self.today_interval_prices,
                tomorrow_interval_prices=self.tomorrow_interval_prices,
                now=now,
                current_interval_key=current_interval_key,
                target_timezone=self.target_timezone,
            )
        except Exception as e:
            _LOGGER.error(f"Error calculating data_validity: {e}", exc_info=True)
            return DataValidity()

    @property
    def statistics(self) -> PriceStatistics:
        """Calculate statistics from today's prices.

        Computed on-demand from interval prices, always accurate.

        Returns:
            PriceStatistics with avg, min, max
        """
        if not self.today_interval_prices:
            return PriceStatistics()

        try:
            prices = list(self.today_interval_prices.values())

            # Find min/max with timestamps
            min_price = min(prices)
            max_price = max(prices)

            # Get timestamps for min/max
            min_timestamp = None
            max_timestamp = None
            for key, price in self.today_interval_prices.items():
                if price == min_price and min_timestamp is None:
                    min_timestamp = key
                if price == max_price and max_timestamp is None:
                    max_timestamp = key

            return PriceStatistics(
                avg=sum(prices) / len(prices),
                min=min_price,
                max=max_price,
                min_timestamp=min_timestamp,
                max_timestamp=max_timestamp,
            )
        except Exception as e:
            _LOGGER.error(f"Error calculating statistics: {e}", exc_info=True)
            return PriceStatistics()

    @property
    def tomorrow_statistics(self) -> PriceStatistics:
        """Calculate statistics from tomorrow's prices.

        Computed on-demand from tomorrow's interval prices.

        Returns:
            PriceStatistics with avg, min, max
        """
        if not self.tomorrow_interval_prices:
            return PriceStatistics()

        try:
            prices = list(self.tomorrow_interval_prices.values())

            # Find min/max with timestamps
            min_price = min(prices)
            max_price = max(prices)

            # Get timestamps for min/max
            min_timestamp = None
            max_timestamp = None
            for key, price in self.tomorrow_interval_prices.items():
                if price == min_price and min_timestamp is None:
                    min_timestamp = key
                if price == max_price and max_timestamp is None:
                    max_timestamp = key

            return PriceStatistics(
                avg=sum(prices) / len(prices),
                min=min_price,
                max=max_price,
                min_timestamp=min_timestamp,
                max_timestamp=max_timestamp,
            )
        except Exception as e:
            _LOGGER.error(f"Error calculating tomorrow_statistics: {e}", exc_info=True)
            return PriceStatistics()

    @property
    def has_tomorrow_prices(self) -> bool:
        """Check if tomorrow prices exist.

        Simple boolean check, computed from dict existence.

        Returns:
            True if tomorrow_interval_prices is non-empty
        """
        return bool(self.tomorrow_interval_prices)

    @property
    def current_price(self) -> Optional[float]:
        """Get current interval price.

        Looks up price for the current interval key.

        Returns:
            Current price or None if not available
        """
        if not self._tz_service:
            _LOGGER.warning("Cannot get current_price without timezone service")
            return None

        try:
            current_key = self._tz_service.get_current_interval_key()
            return self.today_interval_prices.get(current_key)
        except Exception as e:
            _LOGGER.error(f"Error getting current_price: {e}", exc_info=True)
            return None

    @property
    def next_interval_price(self) -> Optional[float]:
        """Get next interval price.

        Looks up price for the next interval key.

        Returns:
            Next interval price or None if not available
        """
        if not self._tz_service:
            _LOGGER.warning("Cannot get next_interval_price without timezone service")
            return None

        try:
            next_key = self._tz_service.get_next_interval_key()
            # Check today first, then tomorrow
            price = self.today_interval_prices.get(next_key)
            if price is None:
                price = self.tomorrow_interval_prices.get(next_key)
            return price
        except Exception as e:
            _LOGGER.error(f"Error getting next_interval_price: {e}", exc_info=True)
            return None

    @property
    def current_interval_key(self) -> Optional[str]:
        """Get current interval key.

        Returns:
            Current interval key (e.g., "14:15") or None
        """
        if not self._tz_service:
            return None

        try:
            return self._tz_service.get_current_interval_key()
        except Exception as e:
            _LOGGER.error(f"Error getting current_interval_key: {e}", exc_info=True)
            return None

    @property
    def next_interval_key(self) -> Optional[str]:
        """Get next interval key.

        Returns:
            Next interval key (e.g., "14:30") or None
        """
        if not self._tz_service:
            return None

        try:
            return self._tz_service.get_next_interval_key()
        except Exception as e:
            _LOGGER.error(f"Error getting next_interval_key: {e}", exc_info=True)
            return None

    @property
    def tomorrow_valid(self) -> bool:
        """Check if tomorrow's data is valid.

        Computed from tomorrow interval count against expected intervals per day.

        Returns:
            True if tomorrow has expected number of intervals
        """
        if not self.tomorrow_interval_prices:
            return False

        expected_intervals = TimeInterval.get_intervals_per_day()
        actual_intervals = len(self.tomorrow_interval_prices)

        # Allow for DST transitions (92-100 intervals)
        return 92 <= actual_intervals <= 100

    # ========== METHODS ==========

    def migrate_to_new_day(self) -> None:
        """Migrate tomorrow's data to today after midnight.

        This is the ONLY place migration logic exists.
        All properties automatically update after this method runs.

        This eliminates the Issue #44 bug where data_validity wasn't
        recalculated after migration - now it's ALWAYS computed fresh.
        """
        _LOGGER.debug(
            f"[{self.area}] Migrating tomorrow data to today. "
            f"Before: today={len(self.today_interval_prices)}, "
            f"tomorrow={len(self.tomorrow_interval_prices)}"
        )

        # Move tomorrow → today
        self.today_interval_prices = self.tomorrow_interval_prices.copy()
        self.today_raw_prices = self.tomorrow_raw_prices.copy()

        # Clear tomorrow
        self.tomorrow_interval_prices = {}
        self.tomorrow_raw_prices = {}

        # Mark as migrated
        self.migrated_from_tomorrow = True
        self.last_updated = dt_util.now().isoformat()

        _LOGGER.debug(
            f"[{self.area}] Migration complete. "
            f"After: today={len(self.today_interval_prices)}, "
            f"tomorrow={len(self.tomorrow_interval_prices)}"
        )

        # That's it! All properties (data_validity, statistics, etc.)
        # automatically recalculate from the new source data.

    def to_cache_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for cache storage.

        Returns ONLY source data, not computed properties.
        This is what gets stored in .storage/ files.

        Returns:
            Dictionary with source data only
        """
        return {
            # Price data (source of truth)
            "today_interval_prices": self.today_interval_prices,
            "tomorrow_interval_prices": self.tomorrow_interval_prices,
            "today_raw_prices": self.today_raw_prices,
            "tomorrow_raw_prices": self.tomorrow_raw_prices,
            # Source metadata
            "source": self.source,
            "area": self.area,
            "source_currency": self.source_currency,
            "target_currency": self.target_currency,
            "source_timezone": self.source_timezone,
            "target_timezone": self.target_timezone,
            # Conversion data
            "ecb_rate": self.ecb_rate,
            "ecb_updated": self.ecb_updated,
            # Display configuration
            "vat_rate": self.vat_rate,
            "vat_included": self.vat_included,
            "display_unit": self.display_unit,
            # Timestamps
            "fetched_at": self.fetched_at,
            "last_updated": self.last_updated,
            # Migration tracking
            "migrated_from_tomorrow": self.migrated_from_tomorrow,
            "original_cache_date": self.original_cache_date,
            # Fallback information
            "attempted_sources": self.attempted_sources,
            "fallback_sources": self.fallback_sources,
            "using_cached_data": self.using_cached_data,
            # Attribution
            "data_source_attribution": self.data_source_attribution,
            # Raw data
            "raw_data": self.raw_data,
            "raw_interval_prices_original": self.raw_interval_prices_original,
        }

    @classmethod
    def from_cache_dict(
        cls, data: Dict[str, Any], tz_service: Optional[Any] = None
    ) -> "IntervalPriceData":
        """Create from cache dictionary.

        Converts stored cache data back into an IntervalPriceData instance.

        Args:
            data: Dictionary from cache (source data only)
            tz_service: Timezone service for computing properties

        Returns:
            IntervalPriceData instance
        """
        return cls(
            # Price data
            today_interval_prices=data.get("today_interval_prices", {}),
            tomorrow_interval_prices=data.get("tomorrow_interval_prices", {}),
            today_raw_prices=data.get("today_raw_prices", {}),
            tomorrow_raw_prices=data.get("tomorrow_raw_prices", {}),
            # Source metadata
            source=data.get("source", ""),
            area=data.get("area", ""),
            source_currency=data.get("source_currency", "EUR"),
            target_currency=data.get("target_currency", "SEK"),
            source_timezone=data.get("source_timezone", "UTC"),
            target_timezone=data.get("target_timezone", "UTC"),
            # Conversion data
            ecb_rate=data.get("ecb_rate"),
            ecb_updated=data.get("ecb_updated"),
            # Display configuration
            vat_rate=data.get("vat_rate", 0.0),
            vat_included=data.get("vat_included", False),
            display_unit=data.get("display_unit", "EUR/kWh"),
            # Timestamps
            fetched_at=data.get("fetched_at"),
            last_updated=data.get("last_updated"),
            # Migration tracking
            migrated_from_tomorrow=data.get("migrated_from_tomorrow", False),
            original_cache_date=data.get("original_cache_date"),
            # Fallback information
            attempted_sources=data.get("attempted_sources", []),
            fallback_sources=data.get("fallback_sources", []),
            using_cached_data=data.get("using_cached_data", False),
            # Attribution
            data_source_attribution=data.get("data_source_attribution"),
            # Raw data
            raw_data=data.get("raw_data"),
            raw_interval_prices_original=data.get("raw_interval_prices_original"),
            # Timezone service (for property computation)
            _tz_service=tz_service,
        )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"IntervalPriceData("
            f"area={self.area}, "
            f"source={self.source}, "
            f"today_intervals={len(self.today_interval_prices)}, "
            f"tomorrow_intervals={len(self.tomorrow_interval_prices)}, "
            f"migrated={self.migrated_from_tomorrow})"
        )
