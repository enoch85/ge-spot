"""Validate stable release versions and the shared release-notes format."""

from pathlib import Path
import re
import sys

VERSION = r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
COMPARE_URL = "https://github.com/enoch85/ge-spot/compare/"


def validate_notes(version: str, current_version: str | None = None) -> Path:
    """Return the notes file after checking its version, sections and changelog."""
    if not re.fullmatch(VERSION, version):
        raise ValueError("Use a production version in the form vMAJOR.MINOR.PATCH")
    if current_version is not None:
        if not re.fullmatch(VERSION, current_version):
            raise ValueError("The manifest must contain a production version")
        if tuple(map(int, version[1:].split("."))) < tuple(
            map(int, current_version[1:].split("."))
        ):
            raise ValueError("The release version cannot precede the manifest version")

    notes = Path("scripts/release/notes") / f"{version}.md"
    body = notes.read_text().strip()
    if "{{" in body or "}}" in body:
        raise ValueError("Fill in all release-notes template placeholders")
    match = re.fullmatch(
        r"## What's Changed\n(?P<changes>.+?)\n+"
        r"### Key Changes\n(?P<keys>.+?)\n+"
        r"\*\*Full Changelog\*\*: (?P<url>\S+)",
        body,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError(
            "Use the What's Changed, Key Changes and Full Changelog template"
        )
    if not any(line.startswith("* ") for line in match["changes"].splitlines()):
        raise ValueError("List the merged changes under What's Changed")
    if not any(line.startswith("- **") for line in match["keys"].splitlines()):
        raise ValueError("Describe the user-visible changes under Key Changes")
    if not re.fullmatch(
        re.escape(COMPARE_URL) + VERSION + r"\.\.\." + re.escape(version), match["url"]
    ):
        raise ValueError("The Full Changelog URL must end at the requested version")
    return notes


if __name__ == "__main__":
    try:
        print(validate_notes(*sys.argv[1:]))
    except (ValueError, OSError, TypeError) as error:
        raise SystemExit(str(error)) from error
