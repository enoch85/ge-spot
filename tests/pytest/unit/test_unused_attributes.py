"""Test for detecting unused attributes in IntervalPriceData.

This test ensures that all attributes defined in the IntervalPriceData dataclass
are actually being set somewhere in the codebase (except for _tz_service which is
internal infrastructure).

This prevents accumulation of dead code like the _api_key_status, _last_fetch_attempt,
and _next_fetch_allowed_in_seconds attributes that were defined but never used.
"""

import ast
import re
from pathlib import Path
from typing import Dict, List, Set

import pytest


def get_dataclass_attributes() -> Set[str]:
    """Extract all attribute names from IntervalPriceData dataclass."""
    data_models_path = Path(
        "custom_components/ge_spot/coordinator/data_models.py"
    ).resolve()

    with open(data_models_path, "r") as f:
        content = f.read()

    # Parse the AST
    tree = ast.parse(content)

    # Find the IntervalPriceData class
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "IntervalPriceData":
            attributes = set()
            # Look for annotated assignments (dataclass fields)
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(
                    item.target, ast.Name
                ):
                    attr_name = item.target.id
                    # Skip properties (they start with @property decorator)
                    if not attr_name.startswith("__"):
                        attributes.add(attr_name)
            return attributes

    raise ValueError("IntervalPriceData class not found")


def find_attribute_assignments(attr_name: str) -> List[str]:
    """Find all places where an attribute is assigned in the codebase.

    Args:
        attr_name: The attribute name to search for

    Returns:
        List of file:line references where the attribute is set
    """
    # Search pattern: .attribute_name =
    pattern = rf"\.{re.escape(attr_name)}\s*="

    matches = []
    code_path = Path("custom_components/ge_spot").resolve()

    for py_file in code_path.rglob("*.py"):
        # Skip the dataclass definition file itself
        if py_file.name == "data_models.py":
            continue

        with open(py_file, "r") as f:
            for line_num, line in enumerate(f, 1):
                if re.search(pattern, line):
                    rel_path = py_file.relative_to(Path.cwd())
                    matches.append(f"{rel_path}:{line_num}")

    return matches


def get_attribute_usage_from_cache_methods() -> Set[str]:
    """Get attributes that are used in to_cache_dict/from_cache_dict methods.

    These are legitimate uses even if not set elsewhere.
    """
    data_models_path = Path(
        "custom_components/ge_spot/coordinator/data_models.py"
    ).resolve()

    with open(data_models_path, "r") as f:
        content = f.read()

    # Find attributes in to_cache_dict and from_cache_dict
    cache_attrs = set()

    # Pattern for dictionary keys in to_cache_dict: "attr_name": self.attr_name
    dict_pattern = r'"([^"]+)":\s*(?:self\.|data\.get\()'

    for match in re.finditer(dict_pattern, content):
        attr_name = match.group(1)
        cache_attrs.add(attr_name)

    return cache_attrs


def test_no_unused_dataclass_attributes():
    """Verify that all IntervalPriceData attributes are actually used.

    This test fails if there are attributes defined in the dataclass but never
    assigned anywhere in the codebase.

    Exceptions:
    - _tz_service: Internal infrastructure, set via constructor
    - Attributes used in cache methods (to_cache_dict/from_cache_dict)
    - Attributes set via constructor in from_cache_dict
    """
    all_attributes = get_dataclass_attributes()

    # Attributes that are allowed to not have explicit assignments
    # (they're set via constructor or are infrastructure)
    allowed_exceptions = {
        "_tz_service",  # Set via constructor, internal infrastructure
    }

    # Get attributes used in cache methods
    cache_attributes = get_attribute_usage_from_cache_methods()

    unused_attributes = {}

    for attr in all_attributes:
        # Skip allowed exceptions
        if attr in allowed_exceptions:
            continue

        # Find where this attribute is assigned
        assignments = find_attribute_assignments(attr)

        # Check if it's used in cache methods (which counts as usage)
        if attr in cache_attributes or f"_{attr}" in cache_attributes:
            # It's used in serialization, that's fine
            continue

        # If no assignments found, it might be unused
        if not assignments:
            unused_attributes[attr] = "No assignments found in codebase"

    # Report findings
    if unused_attributes:
        report = ["\n\nUnused attributes detected in IntervalPriceData:"]
        for attr, reason in unused_attributes.items():
            report.append(f"  - {attr}: {reason}")

        report.append(
            "\nThese attributes should either be removed or assignments should be added."
        )

        pytest.fail("\n".join(report))


def test_all_assigned_attributes_are_defined():
    """Verify that attributes being set on IntervalPriceData are actually defined.

    This catches typos where code tries to set attributes that don't exist
    in the dataclass definition.
    """
    all_attributes = get_dataclass_attributes()

    # Search for all .attribute = patterns in unified_price_manager.py
    manager_path = Path(
        "custom_components/ge_spot/coordinator/unified_price_manager.py"
    ).resolve()

    undefined_assignments = []

    with open(manager_path, "r") as f:
        for line_num, line in enumerate(f, 1):
            # Look for patterns like: some_data._attribute_name =
            # We're specifically looking for IntervalPriceData assignments
            if "._" in line and "=" in line:
                # Extract attribute name
                match = re.search(r"\._(\w+)\s*=", line)
                if match:
                    attr_name = f"_{match.group(1)}"

                    # Check if this attribute exists in the dataclass
                    if attr_name not in all_attributes:
                        # Could be a different object (like self._something)
                        # Only flag if it looks like IntervalPriceData
                        if any(
                            var in line
                            for var in [
                                "price_data",
                                "empty_data",
                                "processed_price_data",
                                "result",
                            ]
                        ):
                            undefined_assignments.append(
                                f"Line {line_num}: {line.strip()} (attribute '{attr_name}' not in dataclass)"
                            )

    if undefined_assignments:
        report = ["\n\nFound assignments to undefined IntervalPriceData attributes:"]
        report.extend(f"  - {item}" for item in undefined_assignments)
        report.append(
            "\nThese attributes should be added to the IntervalPriceData dataclass."
        )

        pytest.fail("\n".join(report))


def test_cache_serialization_matches_dataclass():
    """Verify that to_cache_dict and from_cache_dict handle all non-computed attributes.

    This ensures the cache methods stay in sync with the dataclass definition.
    """
    all_attributes = get_dataclass_attributes()
    cache_attributes = get_attribute_usage_from_cache_methods()

    # Attributes that shouldn't be serialized
    non_serialized = {
        "_tz_service",  # Runtime infrastructure, not cached
    }

    # Attributes that should be in cache but might be missing
    missing_from_cache = []

    for attr in all_attributes:
        # Skip non-serialized
        if attr in non_serialized:
            continue

        # Check if in cache methods
        if attr not in cache_attributes:
            missing_from_cache.append(attr)

    if missing_from_cache:
        report = ["\n\nAttributes missing from cache serialization methods:"]
        report.extend(f"  - {attr}" for attr in missing_from_cache)
        report.append(
            "\nThese should be added to to_cache_dict() and from_cache_dict()."
        )

        pytest.fail("\n".join(report))


if __name__ == "__main__":
    # Allow running this test standalone for debugging
    pytest.main([__file__, "-v"])
