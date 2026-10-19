"""Italian areas must request their own bidding zone from ENTSO-E.

The expected codes are the SDAC registrations, which pair each EIC with GME's
zone code (Day-ahead Annex 3 "MRC cost coefficients", ENTSO-E):
NORD 10Y1001A1001A73I, CNOR 10Y1001A1001A70O, CSUD 10Y1001A1001A71M,
SUD 10Y1001A1001A788, CALA 10Y1001C--00096J, SICI 10Y1001A1001A75E,
SARD 10Y1001A1001A74G. Before this was fixed, five areas were shifted by one
zone (e.g. "IT-Sicily" requested Sardinia, "IT-South" the Corsica AC zone).
"""

import json
from unittest.mock import MagicMock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.ge_spot.const.areas import (
    AreaMapping,
    Timezone,
    get_available_sources,
)
from custom_components.ge_spot.coordinator.cache_manager import CacheManager
from custom_components.ge_spot.coordinator.data_models import IntervalPriceData

ZONES = {
    "IT-North": "10Y1001A1001A73I",
    "IT-Centre-North": "10Y1001A1001A70O",
    "IT-Centre-South": "10Y1001A1001A71M",
    "IT-South": "10Y1001A1001A788",
    "IT-Calabria": "10Y1001C--00096J",
    "IT-Sicily": "10Y1001A1001A75E",
    "IT-Sardinia": "10Y1001A1001A74G",
}


@pytest.mark.parametrize("area,eic", ZONES.items())
def test_italian_zone_requests_its_own_eic(area, eic):
    assert AreaMapping.ENTSOE_MAPPING[area] == eic


@pytest.mark.parametrize("area", ZONES)
def test_italian_zone_is_offered_by_both_sources(area):
    assert {"entsoe", "energy_charts"} <= set(get_available_sources(area))
    assert Timezone.AREA_TIMEZONES[area] == "Europe/Rome"


def test_legacy_italian_areas_name_the_zone_they_return():
    """Existing "IT" and "IT-South-2" setups keep their data, labelled honestly."""
    assert AreaMapping.ENTSOE_MAPPING["IT"] == ZONES["IT-Centre-North"]
    assert AreaMapping.ENTSOE_MAPPING["IT-South-2"] == ZONES["IT-Sicily"]
    assert AreaMapping.ENTSOE_AREAS["IT"] == "IT (Centre-North)"
    assert AreaMapping.ENTSOE_AREAS["IT-South-2"] == "IT-South-2 (Sicily)"


def test_persisted_prices_from_before_the_correction_are_fetched_again(tmp_path):
    """A persisted cache must not keep serving the zone the old code requested."""
    hass = MagicMock()
    hass.config.path = lambda *parts: str(tmp_path)
    hass.async_add_executor_job = lambda func, *args: func(*args)
    config = {"persist_cache": True, "cache_ttl": 60}
    now = dt_util.now()

    writer = CacheManager(hass, config)
    for area, source in (("IT-Sicily", "entsoe"), ("SE3", "nordpool")):
        writer.store(
            area=area,
            source=source,
            data=IntervalPriceData(
                area=area, source=source, today_interval_prices={"00:00": 0.05}
            ),
            timestamp=now,
        )
    # Entries written before this change carry no area code; the ENTSO-E one
    # holds whatever zone the old mapping requested (Sardinia for IT-Sicily).
    cache_file = tmp_path / "cache" / "price_cache.json"
    entries = json.loads(cache_file.read_text())
    for entry in entries.values():
        entry["metadata"].pop("area_code", None)
    cache_file.write_text(json.dumps(entries))

    reader = CacheManager(hass, config)

    assert reader.get_data(area="IT-Sicily", target_date=now.date()) is None
    assert reader.get_data(area="SE3", target_date=now.date()) is not None


def test_persisted_prices_fetched_with_the_current_code_are_kept(tmp_path):
    hass = MagicMock()
    hass.config.path = lambda *parts: str(tmp_path)
    hass.async_add_executor_job = lambda func, *args: func(*args)
    config = {"persist_cache": True, "cache_ttl": 60}
    now = dt_util.now()

    CacheManager(hass, config).store(
        area="IT-Sicily",
        source="entsoe",
        data=IntervalPriceData(
            area="IT-Sicily", source="entsoe", today_interval_prices={"00:00": 0.07}
        ),
        timestamp=now,
    )

    cached = CacheManager(hass, config).get_data(
        area="IT-Sicily", target_date=now.date()
    )
    assert cached.today_interval_prices == {"00:00": 0.07}
