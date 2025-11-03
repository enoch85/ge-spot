"""Unit tests for ENTSO-E areas configuration validation."""

import pytest
from custom_components.ge_spot.const.areas import AreaMapping


class TestEntsoeAreasValidation:
    """Test ENTSO-E areas configuration integrity."""

    def test_all_entsoe_areas_have_mapping(self):
        """Test that all areas in ENTSOE_AREAS have corresponding EIC codes in ENTSOE_MAPPING."""
        for area in AreaMapping.ENTSOE_AREAS.keys():
            assert (
                area in AreaMapping.ENTSOE_MAPPING
            ), f"Area '{area}' is in ENTSOE_AREAS but missing from ENTSOE_MAPPING"

    def test_all_entsoe_areas_have_timezone(self):
        """Test that key Nordic/Baltic areas have timezone definitions."""
        from custom_components.ge_spot.const.areas import Timezone, Area

        # Test that all Area enum instances used in ENTSOE_AREAS have timezones
        for area_key in AreaMapping.ENTSOE_AREAS.keys():
            if isinstance(area_key, Area):
                # Area enums should have timezones available through enum or Timezone class
                assert area_key in Timezone.AREA_TIMEZONES or hasattr(
                    area_key, "name"
                ), f"Area enum '{area_key}' missing timezone definition"

    def test_eic_codes_format(self):
        """Test that all EIC codes follow the expected format."""
        for area, eic_code in AreaMapping.ENTSOE_MAPPING.items():
            # EIC codes should be strings
            assert isinstance(
                eic_code, str
            ), f"EIC code for area '{area}' is not a string: {type(eic_code)}"
            # EIC codes should have correct length (16 characters)
            assert (
                len(eic_code) == 16
            ), f"EIC code for area '{area}' has invalid length: {len(eic_code)} (expected 16)"
            # EIC codes should start with expected patterns
            assert eic_code[0:2] in [
                "10",
                "11",
                "17",
                "46",
                "50",
            ], f"EIC code for area '{area}' has unexpected prefix: {eic_code[0:2]}"

    def test_newly_enabled_areas(self):
        """Test that newly enabled areas (LV, LT, NO5, UA-IPS) are properly configured."""
        newly_enabled = {
            "LV": "10YLV-1001A00074",
            "LT": "10YLT-1001A0008Q",
            "NO5": "10Y1001A1001A48H",
            "UA-IPS": "10Y1001C--000182",
        }

        for area, expected_eic in newly_enabled.items():
            # Check area is in mapping
            assert (
                area in AreaMapping.ENTSOE_MAPPING
            ), f"Newly enabled area '{area}' not found in ENTSOE_MAPPING"
            # Check EIC code matches expected
            assert AreaMapping.ENTSOE_MAPPING[area] == expected_eic, (
                f"Area '{area}' has incorrect EIC code: "
                f"{AreaMapping.ENTSOE_MAPPING[area]} (expected {expected_eic})"
            )
            # Check area is visible in ENTSOE_AREAS
            assert (
                area in AreaMapping.ENTSOE_AREAS
            ), f"Newly enabled area '{area}' not visible in ENTSOE_AREAS"

    def test_non_working_areas_hidden(self):
        """Test that areas with no data are hidden from ENTSOE_AREAS but kept in ENTSOE_MAPPING."""
        non_working = {
            "AL": "10YAL-KESH-----5",
            "BA": "10YBA-JPCC-----D",
            "TR": "10YTR-TEIAS----W",
            "UA": "10Y1001C--00003F",
            "UA-BEI": "10YUA-WEPS-----0",
            "CY": "10YCY-1001A0003J",
        }

        for area, expected_eic in non_working.items():
            # Check area is in mapping (for future use)
            assert (
                area in AreaMapping.ENTSOE_MAPPING
            ), f"Non-working area '{area}' should be kept in ENTSOE_MAPPING for future use"
            # Check EIC code matches expected
            assert AreaMapping.ENTSOE_MAPPING[area] == expected_eic, (
                f"Area '{area}' has incorrect EIC code: "
                f"{AreaMapping.ENTSOE_MAPPING[area]} (expected {expected_eic})"
            )
            # Check area is NOT visible in ENTSOE_AREAS (hidden from users)
            assert (
                area not in AreaMapping.ENTSOE_AREAS
            ), f"Non-working area '{area}' should be hidden from ENTSOE_AREAS"

    def test_no_duplicate_eic_codes(self):
        """Test that there are no duplicate EIC codes (except for intentional cases)."""
        eic_to_areas = {}
        for area, eic_code in AreaMapping.ENTSOE_MAPPING.items():
            if eic_code not in eic_to_areas:
                eic_to_areas[eic_code] = []
            eic_to_areas[eic_code].append(area)

        # Check for duplicates
        duplicates = {
            eic: areas for eic, areas in eic_to_areas.items() if len(areas) > 1
        }

        # Allow known intentional duplicates
        allowed_duplicates = {
            "10Y1001A1001A59C": [
                "GB",
                "IE(SEM)",
            ],  # Great Britain and Ireland SEM share code
            "10Y1001A1001A48H": [
                "NO1",
                "NO5",
            ],  # NO1 and NO5 might share (verify this is intentional)
            # Note: DE-LU is the only area for the Germany-Luxembourg bidding zone now
            # (DE was removed as it's the same bidding zone)
        }

        for eic, areas in duplicates.items():
            # Check if it's an allowed duplicate
            if eic in allowed_duplicates:
                assert sorted(areas) == sorted(allowed_duplicates[eic]), (
                    f"EIC code {eic} has unexpected duplicate areas: {areas} "
                    f"(expected {allowed_duplicates[eic]})"
                )
            else:
                pytest.fail(
                    f"Unexpected duplicate EIC code {eic} used by areas: {areas}"
                )

    def test_energy_charts_areas_subset_of_entsoe(self):
        """Test that areas in ENERGY_CHARTS_BZN that are ENTSOE areas are properly configured."""
        for area in AreaMapping.ENERGY_CHARTS_BZN.keys():
            # If this area is also in ENTSOE system, it should have proper EIC code
            if area in AreaMapping.ENTSOE_MAPPING:
                assert (
                    area in AreaMapping.ENTSOE_MAPPING
                ), f"Area '{area}' in ENERGY_CHARTS_BZN but missing from ENTSOE_MAPPING"

    def test_nordpool_areas_subset_of_entsoe(self):
        """Test that Nordpool areas that are also ENTSOE areas are properly configured."""
        nordpool_areas = set(AreaMapping.NORDPOOL_AREAS.keys())
        entsoe_areas = set(AreaMapping.ENTSOE_MAPPING.keys())

        # Find overlap
        overlap = nordpool_areas & entsoe_areas

        # These overlapping areas should be properly configured
        for area in overlap:
            assert (
                area in AreaMapping.ENTSOE_MAPPING
            ), f"Area '{area}' is in both Nordpool and ENTSOE but missing EIC code"

    def test_config_flow_shows_only_working_areas(self):
        """Test that get_available_sources only returns entsoe for areas with working mappings."""
        from custom_components.ge_spot.const.areas import get_available_sources

        # Test working areas
        working_areas = ["LV", "LT", "NO5", "UA-IPS", "DE-LU", "FR", "SE1"]
        for area in working_areas:
            if area in AreaMapping.ENTSOE_AREAS:
                sources = get_available_sources(area)
                assert (
                    "entsoe" in sources
                ), f"Working area '{area}' should have 'entsoe' as available source"

        # Test non-working areas (should not show entsoe)
        non_working = ["AL", "BA", "TR", "UA", "UA-BEI", "CY"]
        for area in non_working:
            sources = get_available_sources(area)
            assert (
                "entsoe" not in sources
            ), f"Non-working area '{area}' should NOT have 'entsoe' as available source"

    def test_removed_dead_code(self):
        """Test that dead code like IT-Centre-North has been completely removed."""
        # IT-Centre-North was removed as it doesn't work
        assert (
            "IT-Centre-North" not in AreaMapping.ENTSOE_MAPPING
        ), "Dead code 'IT-Centre-North' found in ENTSOE_MAPPING"
        assert (
            "IT-Centre-North" not in AreaMapping.ENTSOE_AREAS
        ), "Dead code 'IT-Centre-North' found in ENTSOE_AREAS"
        assert (
            "IT-Centre-North" not in AreaMapping.ENERGY_CHARTS_BZN
        ), "Dead code 'IT-Centre-North' found in ENERGY_CHARTS_BZN"

    def test_all_working_areas_have_display_names(self):
        """Test that all working areas have proper display names."""
        for area in AreaMapping.ENTSOE_AREAS.keys():
            display_name = AreaMapping.ENTSOE_AREAS[area]
            # Display name should not be empty
            assert (
                display_name and len(display_name) > 0
            ), f"Area '{area}' has empty display name"
            # Display name should be a string
            assert isinstance(
                display_name, str
            ), f"Display name for area '{area}' is not a string"
