"""Sync runtime dependency versions from requirements.txt into manifest.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from packaging.requirements import Requirement

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"
DEFAULT_MANIFEST_PATH = REPO_ROOT / "custom_components" / "ge_spot" / "manifest.json"


def _parse_requirement_map(requirements_path: Path) -> dict[str, str]:
    requirement_map: dict[str, str] = {}

    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue

        requirement = Requirement(line)
        requirement_map[requirement.name.lower()] = line

    return requirement_map


def sync_manifest_requirements(
    requirements_path: Path, manifest_path: Path, check: bool
) -> bool:
    requirement_map = _parse_requirement_map(requirements_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    updated_requirements: list[str] = []
    missing_packages: list[str] = []

    for requirement_line in manifest["requirements"]:
        requirement = Requirement(requirement_line)
        normalized_name = requirement.name.lower()

        synced_requirement = requirement_map.get(normalized_name)
        if synced_requirement is None:
            missing_packages.append(requirement.name)
            updated_requirements.append(requirement_line)
            continue

        updated_requirements.append(synced_requirement)

    if missing_packages:
        missing_names = ", ".join(sorted(missing_packages))
        raise ValueError(
            f"manifest.json packages missing from requirements.txt: {missing_names}"
        )

    changed = updated_requirements != manifest["requirements"]
    if not changed:
        print("manifest.json already matches requirements.txt")
        return False

    manifest["requirements"] = updated_requirements

    if check:
        print("manifest.json is out of sync with requirements.txt")
        return True

    manifest_path.write_text(
        json.dumps(manifest, indent=4, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print("Updated manifest.json requirements from requirements.txt")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync Home Assistant manifest requirements from requirements.txt."
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        default=DEFAULT_REQUIREMENTS_PATH,
        help="Path to requirements.txt",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Path to manifest.json",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with status 1 when manifest.json needs to be updated.",
    )
    args = parser.parse_args()

    changed = sync_manifest_requirements(args.requirements, args.manifest, args.check)
    if args.check and changed:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
