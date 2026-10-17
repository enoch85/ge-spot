"""Italian areas must request their own bidding zone from ENTSO-E.

The expected codes are the SDAC registrations, which pair each EIC with GME's
zone code (Day-ahead Annex 3 "MRC cost coefficients", ENTSO-E):
NORD 10Y1001A1001A73I, CNOR 10Y1001A1001A70O, CSUD 10Y1001A1001A71M,
SUD 10Y1001A1001A788, CALA 10Y1001C--00096J, SICI 10Y1001A1001A75E,
SARD 10Y1001A1001A74G. Before this was fixed, five areas were shifted by one
zone (e.g. "IT-Sicily" requested Sardinia, "IT-South" the Corsica AC zone).
"""

import pytest

from custom_components.ge_spot.const.areas import (
    AreaMapping,
    Timezone,
    get_available_sources,
)

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
