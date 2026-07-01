"""Price-specific sensor implementations."""

import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, Callable
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import callback, Event
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.restore_state import RestoreEntity, ExtraStoredData
from homeassistant.util import dt as dt_util

from .base import BaseElectricityPriceSensor
from .consumption import WeightedAverageAccumulator
from ..const.attributes import Attributes

_LOGGER = logging.getLogger(__name__)


class PriceValueSensor(BaseElectricityPriceSensor):
    """Representation of a GE Spot price sensor."""

    def __init__(
        self,
        coordinator,
        config_data,
        sensor_type,
        name_suffix,
        value_fn: Callable[[Dict[str, Any]], Optional[float]],  # Added parameter
        additional_attrs: Optional[
            Callable[[Dict[str, Any]], Dict[str, Any]]
        ] = None,  # Added parameter
    ):
        """Initialize the sensor."""
        # Ensure config_data is a dictionary before passing to super().__init__
        if not isinstance(config_data, dict):
            config_data = {"entry_id": coordinator.config_entry.entry_id}

        super().__init__(coordinator, config_data, sensor_type, name_suffix)
        self._value_fn = value_fn
        self._additional_attrs = additional_attrs

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if not self.coordinator.data:
            return None

        # Return the value directly from the coordinator data via the value function.
        # The DataProcessor/CurrencyConverter already handles subunit conversion.
        value = self._value_fn(self.coordinator.data)

        return value

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = super().extra_state_attributes

        # Add additional attributes if provided
        if self._additional_attrs and self.coordinator.data:
            additional = self._additional_attrs(self.coordinator.data)
            if additional:
                # Keep essential additional attributes
                # Include tomorrow_valid and export price lists for export sensors
                essential_keys = {
                    "tomorrow_valid",
                    "export_today_prices",
                    "export_tomorrow_prices",
                }
                essential_attrs = {}
                for key, value in additional.items():
                    if key in essential_keys:
                        essential_attrs[key] = value
                attrs.update(essential_attrs)

        return attrs


class ExtremaPriceSensor(PriceValueSensor):
    """Base class for min/max price sensors."""

    def __init__(
        self,
        coordinator,
        config_data,
        sensor_type,
        name_suffix,
        day_offset=0,
        extrema_type="min",
    ):
        """Initialize the extrema price sensor."""
        self._day_offset = day_offset
        self._extrema_type = extrema_type

        # Create value extraction function
        def extract_value(data):
            if not data:
                _LOGGER.debug(f"ExtremaSensor {self.entity_id}: No data available")
                return None

            # data is IntervalPriceData object - use properties
            stats = data.statistics if day_offset == 0 else data.tomorrow_statistics
            if not stats:
                _LOGGER.debug(
                    f"ExtremaSensor {self.entity_id}: statistics not available for day_offset={day_offset}"
                )
                return None

            # stats is PriceStatistics object - access as attribute
            value = stats.min if extrema_type == "min" else stats.max
            _LOGGER.debug(
                f"ExtremaSensor {self.entity_id}: Reading '{extrema_type}' from statistics. Found value: {value}."
            )
            return value

        def get_timestamp(data):
            if not data:
                return {}

            # data is IntervalPriceData object - use properties
            stats = data.statistics if day_offset == 0 else data.tomorrow_statistics
            if not stats:
                return {}

            # Get timestamp and price from PriceStatistics object
            timestamp = (
                stats.min_timestamp if extrema_type == "min" else stats.max_timestamp
            )
            price_value = stats.min if extrema_type == "min" else stats.max

            # Format the price value
            if isinstance(price_value, (int, float)):
                price_value = round(price_value, 2)

            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    # Use HA's datetime format
                    formatted_time = dt_util.as_local(dt).isoformat(timespec="minutes")
                    return {"timestamp": formatted_time, "value": price_value}
                except (ValueError, TypeError):
                    return {"timestamp": timestamp, "value": price_value}
            return {}

        # Initialize parent class
        super().__init__(
            coordinator,
            config_data,
            sensor_type,
            name_suffix,
            extract_value,
            get_timestamp,
        )


class TomorrowSensorMixin:
    """Mixin to provide tomorrow-specific behavior."""

    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False
        # Only available if tomorrow data is valid (computed property)
        return self.coordinator.data.tomorrow_valid if self.coordinator.data else False


class TomorrowExtremaPriceSensor(TomorrowSensorMixin, ExtremaPriceSensor):
    """Extrema price sensor for tomorrow data with proper availability behavior."""


class TomorrowAveragePriceSensor(TomorrowSensorMixin, PriceValueSensor):
    """Average price sensor for tomorrow data with proper availability behavior."""


class PriceStatisticSensor(PriceValueSensor):
    """Sensor for price statistics (average, min, max)."""

    device_class = SensorDeviceClass.MONETARY
    state_class = None

    def __init__(self, coordinator, config_data, sensor_type, name_suffix, stat_type):
        """Initialize the price statistic sensor."""

        # Create value extraction function
        def extract_value(data):
            # data is IntervalPriceData object, not dict - use properties
            if not data:
                _LOGGER.debug(
                    f"PriceStatisticSensor {self.entity_id}: No data available."
                )
                return None

            stats = data.statistics
            if not stats:
                _LOGGER.debug(
                    f"PriceStatisticSensor {self.entity_id}: statistics property returned empty."
                )
                return None

            # stats is PriceStatistics object - access as attribute
            value = getattr(stats, stat_type, None)
            _LOGGER.debug(
                f"PriceStatisticSensor {self.entity_id}: Reading '{stat_type}' from statistics. Found value: {value}."
            )
            return value

        # Initialize parent class, passing the full config_data
        super().__init__(
            coordinator,
            config_data,  # Pass the full config_data
            sensor_type,
            name_suffix,
            extract_value,
            None,
        )
        self._stat_type = stat_type

    # Add this property to inherit unit logic from base class
    @property
    def native_unit_of_measurement(self):
        return super().native_unit_of_measurement


class PriceDifferenceSensor(PriceValueSensor):
    """Sensor for price difference between two values."""

    device_class = SensorDeviceClass.MONETARY
    state_class = None

    def __init__(
        self, coordinator, config_data, sensor_type, name_suffix, value1_key, value2_key
    ):
        """Initialize the price difference sensor."""

        # Create value extraction function
        def extract_value(data):
            if not data:
                _LOGGER.debug(
                    f"PriceDifferenceSensor {self.entity_id}: No data available."
                )
                return None

            # data is IntervalPriceData object - use properties
            value1 = None
            if value1_key == "current_price":
                value1 = data.current_price
                _LOGGER.debug(
                    f"PriceDifferenceSensor {self.entity_id}: current_price from property: {value1}"
                )
            else:
                # Try to get as property
                value1 = getattr(data, value1_key, None)
                _LOGGER.debug(
                    f"PriceDifferenceSensor {self.entity_id}: {value1_key} from property: {value1}"
                )

            value2 = None
            if value2_key == "average":
                # Get from statistics property
                stats = data.statistics
                value2 = stats.avg if stats else None
                _LOGGER.debug(
                    f"PriceDifferenceSensor {self.entity_id}: Reading average from statistics: {value2}"
                )
            else:
                value2 = getattr(data, value2_key, None)
                _LOGGER.debug(
                    f"PriceDifferenceSensor {self.entity_id}: Reading {value2_key} as property: {value2}"
                )

            if value1 is None or value2 is None:
                _LOGGER.debug(
                    f"PriceDifferenceSensor {self.entity_id}: Calculation failed. value1={value1}, value2={value2}"
                )
                return None

            result = value1 - value2
            _LOGGER.debug(
                f"PriceDifferenceSensor {self.entity_id}: Calculated difference: {result} (value1={value1}, value2={value2})"
            )
            return result

        # Initialize parent class, passing the full config_data
        super().__init__(
            coordinator,
            config_data,  # Pass the full config_data
            sensor_type,
            name_suffix,
            extract_value,
            None,
        )
        self._value1_key = value1_key
        self._value2_key = value2_key


class PricePercentSensor(PriceValueSensor):
    """Sensor for price percentage relative to a reference value."""

    # A percentage (unit "%") is not a monetary amount; MONETARY here is a
    # device_class/unit mismatch. Override the base MONETARY device_class to None.
    device_class = None
    state_class = None

    def __init__(
        self,
        coordinator,
        config_data,
        sensor_type,
        name_suffix,
        value_key,
        reference_key,
    ):
        """Initialize the price percentage sensor."""

        # Create value extraction function
        def extract_value(data):
            if not data:
                _LOGGER.debug(
                    f"PricePercentSensor {self.entity_id}: No data available."
                )
                return None

            # data is IntervalPriceData object - use properties
            value = None
            if value_key == "current_price":
                value = data.current_price
                _LOGGER.debug(
                    f"PricePercentSensor {self.entity_id}: current_price from property: {value}"
                )
            else:
                value = getattr(data, value_key, None)
                _LOGGER.debug(
                    f"PricePercentSensor {self.entity_id}: {value_key} from property: {value}"
                )

            reference = None
            if reference_key == "average":
                # Get from statistics property
                stats = data.statistics
                reference = stats.avg if stats else None
                _LOGGER.debug(
                    f"PricePercentSensor {self.entity_id}: Reading average from statistics: {reference}"
                )
            else:
                reference = getattr(data, reference_key, None)
                _LOGGER.debug(
                    f"PricePercentSensor {self.entity_id}: Reading {reference_key} as property: {reference}"
                )

            if value is None or reference is None or reference == 0:
                _LOGGER.debug(
                    f"PricePercentSensor {self.entity_id}: Calculation failed. value={value}, reference={reference}"
                )
                return None

            result = (value / reference - 1) * 100
            _LOGGER.debug(
                f"PricePercentSensor {self.entity_id}: Calculated percentage: {result} (value={value}, reference={reference})"
            )
            return result

        # Initialize parent class, passing the full config_data
        super().__init__(
            coordinator,
            config_data,  # Pass the full config_data
            sensor_type,
            name_suffix,
            extract_value,
            None,
        )
        self._value_key = value_key
        self._reference_key = reference_key

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return "%"


class HourlyAverageSensor(PriceValueSensor):
    """Sensor that calculates hourly average prices from 15-minute intervals."""

    device_class = SensorDeviceClass.MONETARY
    state_class = None

    # Override to exclude hourly price arrays from database (like interval prices)
    _unrecorded_attributes = frozenset(
        {
            "today_hourly_prices",
            "tomorrow_hourly_prices",
        }
    )

    def __init__(
        self,
        coordinator,
        config_data,
        sensor_type,
        name_suffix,
        day_offset=0,
        use_raw=False,
    ):
        """Initialize the hourly average price sensor.

        Args:
            coordinator: Data coordinator
            config_data: Configuration data
            sensor_type: Type identifier for the sensor
            name_suffix: Display name suffix
            day_offset: 0 for today, 1 for tomorrow
            use_raw: If True, average the base market prices (raw, before
                VAT/taxes/tariffs) instead of the all-in prices (Issue #70)
        """
        self._day_offset = day_offset
        self._use_raw = use_raw

        # Create value extraction function
        def extract_value(data):
            """Extract current hour's average price."""
            hourly_prices = self._calculate_hourly_averages(data)
            if not hourly_prices:
                return None

            # Get current hour (or first hour of tomorrow for tomorrow sensor)
            if self._day_offset == 0:
                # For today: current hour in the area timezone so it matches the
                # area-local interval keys (HA's zone may differ from the area's).
                now = dt_util.now().astimezone(self._target_timezone)
                current_hour = f"{now.hour:02d}:00"
                return hourly_prices.get(current_hour)
            else:
                # For tomorrow: return first hour's average
                sorted_hours = sorted(hourly_prices.keys())
                if sorted_hours:
                    return hourly_prices[sorted_hours[0]]
                return None

        # Create additional attributes function (not used, we override extra_state_attributes)
        def get_hourly_attrs(data):
            """Get hourly price attributes."""
            return {}

        # Initialize parent class
        super().__init__(
            coordinator,
            config_data,
            sensor_type,
            name_suffix,
            extract_value,
            get_hourly_attrs,
        )

    def _calculate_hourly_averages(self, data: Dict[str, Any]) -> Dict[str, float]:
        """Calculate hourly averages from 15-minute interval prices.

        Args:
            data: Coordinator data containing interval prices

        Returns:
            Dictionary mapping hour (HH:00) to average price
        """
        # Get the appropriate interval prices based on day offset. When use_raw
        # is set, use the base market prices (before VAT/taxes/tariffs).
        if not data:
            interval_prices = {}
        elif self._day_offset == 0:
            interval_prices = (
                data.today_raw_prices if self._use_raw else data.today_interval_prices
            )
        else:
            interval_prices = (
                data.tomorrow_raw_prices
                if self._use_raw
                else data.tomorrow_interval_prices
            )

        if not interval_prices:
            return {}

        # Group intervals by hour and calculate averages
        hourly_data = {}
        for interval_key, price in interval_prices.items():
            try:
                # Extract hour from HH:MM format
                hour = interval_key.split(":")[0]
                hour_key = f"{hour}:00"

                # Initialize list for this hour if needed
                if hour_key not in hourly_data:
                    hourly_data[hour_key] = []

                # Add price to this hour's list
                hourly_data[hour_key].append(float(price))
            except (ValueError, AttributeError) as e:
                _LOGGER.warning(f"Failed to process interval {interval_key}: {e}")
                continue

        # Calculate averages
        hourly_averages = {}
        for hour_key, prices in hourly_data.items():
            if prices:
                hourly_averages[hour_key] = sum(prices) / len(prices)

        return hourly_averages

    def _convert_hourly_to_list(
        self, hourly_prices: Dict[str, float], base_date
    ) -> list:
        """Convert hourly prices dict to list format with datetime objects.

        Args:
            hourly_prices: Dictionary mapping hour (HH:00) to price
            base_date: Date to use for datetime objects

        Returns:
            List of dicts with 'time' (datetime) and 'value' (float) keys
        """
        # Get target timezone (area-local interval keys, see _target_timezone)
        target_tz = self._target_timezone

        hourly_list = []
        for hhmm_key in sorted(hourly_prices.keys()):
            try:
                hour = int(hhmm_key.split(":")[0])
                dt_obj = datetime(
                    base_date.year,
                    base_date.month,
                    base_date.day,
                    hour,
                    0,
                    0,
                    tzinfo=target_tz,
                )
                price = hourly_prices[hhmm_key]
                hourly_list.append(
                    {
                        "time": dt_obj,
                        "value": round(float(price), 4),
                    }
                )
            except (ValueError, AttributeError) as e:
                _LOGGER.warning(f"Failed to convert hourly interval {hhmm_key}: {e}")
                continue

        return hourly_list

    @property
    def extra_state_attributes(self):
        """Return hourly price attributes instead of interval prices."""
        # Get base attributes from parent (but we'll override the interval prices)
        attrs = super().extra_state_attributes

        if not self.coordinator.data:
            return attrs

        # Get target timezone for datetime conversion (area-local interval keys)
        target_tz = self._target_timezone
        now = dt_util.now().astimezone(target_tz)

        # Calculate hourly averages for today and tomorrow
        today_hourly = {}
        tomorrow_hourly = {}

        # Get interval prices from coordinator data (properties). When use_raw
        # is set, use the base market prices (before VAT/taxes/tariffs).
        if not self.coordinator.data:
            today_intervals = {}
            tomorrow_intervals = {}
        elif self._use_raw:
            today_intervals = self.coordinator.data.today_raw_prices
            tomorrow_intervals = self.coordinator.data.tomorrow_raw_prices
        else:
            today_intervals = self.coordinator.data.today_interval_prices
            tomorrow_intervals = self.coordinator.data.tomorrow_interval_prices

        # Calculate hourly averages for today
        if today_intervals:
            hourly_data = {}
            for interval_key, price in today_intervals.items():
                try:
                    hour = interval_key.split(":")[0]
                    hour_key = f"{hour}:00"
                    if hour_key not in hourly_data:
                        hourly_data[hour_key] = []
                    hourly_data[hour_key].append(float(price))
                except (ValueError, AttributeError):
                    continue

            for hour_key, prices in hourly_data.items():
                if prices:
                    today_hourly[hour_key] = sum(prices) / len(prices)

        # Calculate hourly averages for tomorrow
        if tomorrow_intervals:
            hourly_data = {}
            for interval_key, price in tomorrow_intervals.items():
                try:
                    hour = interval_key.split(":")[0]
                    hour_key = f"{hour}:00"
                    if hour_key not in hourly_data:
                        hourly_data[hour_key] = []
                    hourly_data[hour_key].append(float(price))
                except (ValueError, AttributeError):
                    continue

            for hour_key, prices in hourly_data.items():
                if prices:
                    tomorrow_hourly[hour_key] = sum(prices) / len(prices)

        # Convert to list format with datetime objects
        today_date = now.date()
        tomorrow_date = (now + timedelta(days=1)).date()

        attrs["today_hourly_prices"] = self._convert_hourly_to_list(
            today_hourly, today_date
        )
        attrs["tomorrow_hourly_prices"] = self._convert_hourly_to_list(
            tomorrow_hourly, tomorrow_date
        )

        # Add statistics for today's hourly prices
        if today_hourly:
            values = list(today_hourly.values())
            attrs["today_min_price"] = round(min(values), 5)
            attrs["today_max_price"] = round(max(values), 5)
            attrs["today_avg_price"] = round(sum(values) / len(values), 5)

        # Add statistics for tomorrow's hourly prices
        if tomorrow_hourly:
            values = list(tomorrow_hourly.values())
            attrs["tomorrow_min_price"] = round(min(values), 5)
            attrs["tomorrow_max_price"] = round(max(values), 5)
            attrs["tomorrow_avg_price"] = round(sum(values) / len(values), 5)

        # Remove the 15-minute interval prices from attributes for hourly sensors
        # These sensors focus on hourly data, not interval data
        attrs.pop("today_interval_prices", None)
        attrs.pop("tomorrow_interval_prices", None)

        return attrs


class TomorrowHourlyAverageSensor(TomorrowSensorMixin, HourlyAverageSensor):
    """Hourly average price sensor for tomorrow with proper availability."""


@dataclass
class _WeightedAvgExtraData(ExtraStoredData):
    """Accumulator state persisted across restarts for the weighted average.

    The meter baseline (``last_energy``) is deliberately excluded: it is
    re-seeded from the meter on startup so consumption that happened while Home
    Assistant was down is not back-counted at the wrong price.
    """

    cost_acc: float
    energy_acc: float
    simple_sum: float
    simple_count: int
    period_start_key: Optional[str]
    last_interval_key: Optional[str]
    fingerprint: str

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict for the restore store."""
        return asdict(self)


class ConsumptionWeightedAverageSensor(RestoreEntity, BaseElectricityPriceSensor):
    """Consumption-weighted average price — your own average vs the market.

    Weights each interval's all-in spot price by the energy actually consumed
    (read from a user-selected cumulative kWh sensor) to show the average price
    you really paid this period, alongside the simple market average over the
    same elapsed intervals so you can tell whether you beat it.

    Accumulators persist across restarts (RestoreEntity) and reset at the start
    of each period: local midnight for ``daily``, month start for ``monthly``.
    """

    # device_class/state_class (MONETARY / None) and the display unit are
    # inherited from BaseElectricityPriceSensor, matching the Average Price
    # sensor so the two are directly comparable.

    # Only small scalar attributes are emitted here (never the big price arrays),
    # so nothing needs excluding from the recorder.
    _unrecorded_attributes = frozenset()

    def __init__(
        self,
        coordinator,
        config_data,
        sensor_type,
        name_suffix,
        energy_entity_id,
        period,
    ):
        """Initialize the consumption-weighted average sensor.

        Args:
            energy_entity_id: entity_id of the cumulative kWh consumption sensor.
            period: ``"daily"`` or ``"monthly"``.
        """
        # BaseElectricityPriceSensor does not chain super().__init__(); call it
        # directly to set up entity_id/name/unique_id, currency, display unit.
        BaseElectricityPriceSensor.__init__(
            self, coordinator, config_data, sensor_type, name_suffix
        )
        self._energy_entity_id = energy_entity_id
        self._period = period
        self._acc = WeightedAverageAccumulator(period=period)
        self._unsub_energy = None
        self._unsub_midnight = None

    # --- Lifecycle ---------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Restore state, then subscribe to the meter, coordinator and midnight.

        Intentionally does NOT call the base async_added_to_hass — it registers
        a plain coordinator listener that only writes state, whereas we need one
        that also samples the benchmark. RestoreEntity's own setup runs via
        async_internal_added_to_hass (invoked separately by the entity
        platform), so restore still works.
        """
        # 1) Restore persisted accumulators if the config fingerprint matches.
        last = await self.async_get_last_extra_data()
        if last is not None:
            self._restore_from(last.as_dict())

        # 2) Roll over if Home Assistant was down across a period boundary.
        self._acc.maybe_reset(self._now_local())

        # 3) Track the consumption meter.
        self._unsub_energy = async_track_state_change_event(
            self.hass, [self._energy_entity_id], self._handle_energy_change
        )
        self.async_on_remove(self._unsub_energy)

        # 4) Sample the benchmark on each coordinator update (≈ once per interval).
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

        # 5) Crisp local-midnight rollover. The content checks above are the
        #    correctness backstop; this just avoids up-to-15-min display lag.
        self._unsub_midnight = async_track_time_change(
            self.hass, self._handle_midnight, hour=0, minute=0, second=5
        )
        self.async_on_remove(self._unsub_midnight)

        # 6) Seed the meter baseline from its current reading so the first real
        #    delta isn't swallowed (and downtime consumption isn't back-counted).
        self._seed_baseline()

        self.async_write_ha_state()

    # --- Event handlers ----------------------------------------------------

    @callback
    def _handle_energy_change(self, event: Event) -> None:
        """Fold a consumption-meter change into the weighted average."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        try:
            new_kwh = float(new_state.state)
        except (ValueError, TypeError):
            return

        now_local = self._now_local()
        price = self._current_price()
        self._acc.add_energy(new_kwh, price, now_local)
        # Also sample the benchmark here so it stays fresh between coordinator
        # ticks; idempotent within an interval via the dedup key.
        dedup = self._interval_dedup_key(now_local)
        if dedup is not None:
            self._acc.sample_simple(dedup, price, now_local)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Sample the benchmark each interval and refresh the state."""
        now_local = self._now_local()
        dedup = self._interval_dedup_key(now_local)
        if dedup is not None:
            self._acc.sample_simple(dedup, self._current_price(), now_local)
        else:
            self._acc.maybe_reset(now_local)
        self.async_write_ha_state()

    @callback
    def _handle_midnight(self, now) -> None:
        """Backstop period rollover at local midnight."""
        self._acc.maybe_reset(self._now_local())
        self.async_write_ha_state()

    # --- State -------------------------------------------------------------

    @property
    def native_value(self):
        """Return the consumption-weighted average price for this period."""
        weighted = self._acc.weighted
        if weighted is None:
            return None
        return round(weighted, self._precision)

    @property
    def available(self) -> bool:
        """Always available once set up.

        The accumulated value stays meaningful even if a price refresh fails, so
        we don't propagate the coordinator's transient unavailability (which
        would blank the value and pollute history).
        """
        return True

    @property
    def extra_state_attributes(self):
        """Return the small scalar attributes for this sensor.

        Deliberately does NOT call the base implementation, which emits the full
        today/tomorrow interval price arrays and queries the price manager on
        every render — irrelevant and expensive here.
        """
        acc = self._acc
        weighted = acc.weighted
        simple = acc.simple

        attrs = {
            Attributes.CURRENCY: self._currency,
            Attributes.AREA: self._area,
            Attributes.VAT: f"{self._vat * 100:.1f}%",
            "display_unit": self._display_unit,
            "use_subunit": self._use_subunit,
            Attributes.ENERGY_SOURCE: self._energy_entity_id,
            Attributes.PERIOD: self._period,
            Attributes.PERIOD_START: acc.period_start_key,
            Attributes.CONSUMED_ENERGY: round(acc.energy_acc, 3),
            Attributes.ACCUMULATED_COST: round(acc.cost_acc, 2),
        }

        if simple is not None:
            attrs[Attributes.SIMPLE_AVERAGE] = round(simple, self._precision)
        if weighted is not None and simple is not None:
            attrs[Attributes.SAVINGS_VS_AVERAGE] = round(
                simple - weighted, self._precision
            )
            attrs[Attributes.BEATING_AVERAGE] = weighted < simple

        return attrs

    # --- Persistence -------------------------------------------------------

    @property
    def extra_restore_state_data(self) -> _WeightedAvgExtraData:
        """State persisted across restarts (excludes the meter baseline)."""
        acc = self._acc
        return _WeightedAvgExtraData(
            cost_acc=acc.cost_acc,
            energy_acc=acc.energy_acc,
            simple_sum=acc.simple_sum,
            simple_count=acc.simple_count,
            period_start_key=acc.period_start_key,
            last_interval_key=acc.last_interval_key,
            fingerprint=self._fingerprint(),
        )

    def _restore_from(self, data: Dict[str, Any]) -> None:
        """Restore accumulators from persisted data if the fingerprint matches.

        A changed fingerprint (display unit, VAT, currency or the energy entity)
        means the accumulated cost is no longer on the same basis, so we discard
        it and start fresh rather than mix bases.
        """
        if not data or data.get("fingerprint") != self._fingerprint():
            return
        acc = self._acc
        acc.cost_acc = float(data.get("cost_acc", 0.0) or 0.0)
        acc.energy_acc = float(data.get("energy_acc", 0.0) or 0.0)
        acc.simple_sum = float(data.get("simple_sum", 0.0) or 0.0)
        acc.simple_count = int(data.get("simple_count", 0) or 0)
        acc.period_start_key = data.get("period_start_key")
        acc.last_interval_key = data.get("last_interval_key")

    # --- Helpers -----------------------------------------------------------

    def _fingerprint(self) -> str:
        """Config fingerprint; a change invalidates persisted accumulators."""
        return (
            f"{self._currency}|{self._display_unit}|{self._vat}|"
            f"{self._energy_entity_id}"
        )

    def _now_local(self) -> datetime:
        """Current time in the area/display timezone (period boundaries)."""
        return dt_util.now().astimezone(self._target_timezone)

    def _current_price(self) -> Optional[float]:
        """All-in current interval price in the display unit, or None."""
        data = self.coordinator.data
        if not data:
            return None
        return data.current_price

    def _interval_dedup_key(self, now_local: datetime) -> Optional[str]:
        """Date-qualified current-interval key for benchmark de-duplication.

        Date-qualifying is required for the monthly sensor: a bare HH:MM repeats
        every day, which would freeze the monthly benchmark after day one.
        """
        if not self._tz_service:
            return None
        try:
            interval_key = self._tz_service.get_current_interval_key()
        except Exception:  # pragma: no cover - defensive
            return None
        if not interval_key:
            return None
        return f"{now_local.date().isoformat()}|{interval_key}"

    def _seed_baseline(self) -> None:
        """Seed the meter baseline from the meter's current state, if numeric."""
        state = self.hass.states.get(self._energy_entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        try:
            self._acc.last_energy = float(state.state)
        except (ValueError, TypeError):
            self._acc.last_energy = None
