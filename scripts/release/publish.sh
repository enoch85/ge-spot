#!/usr/bin/env bash
# Keep publication and prerelease conversion together, with no intervening steps.
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
version_tag="${1:?Pass the release version}"
repo="${GITHUB_REPOSITORY:-enoch85/ge-spot}"
notes_file=$(python3 "$SCRIPT_DIR/validate_notes.py" "$version_tag")

gh release create "$version_tag" \
    --repo "$repo" \
    --verify-tag \
    --title "GE-Spot Home Assistant $version_tag" \
    --notes-file "$notes_file" \
    --latest \
    "ge_spot.zip#GE-Spot Home Assistant $version_tag"

# Retry a transient edit failure immediately; leave the workflow failed if all fail.
for attempt in 1 2 3; do
    if gh release edit "$version_tag" --repo "$repo" --prerelease --latest=false; then
        exit 0
    fi
done
echo "Could not mark $version_tag as a prerelease after publication." >&2
exit 1
