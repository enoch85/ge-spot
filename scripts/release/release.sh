#!/usr/bin/env bash
# Publish GE-Spot through the production workflow, then hold it as a prerelease.
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
MANIFEST_PATH="custom_components/ge_spot/manifest.json"
REPO_NAME="enoch85/ge-spot"

show_usage() {
    echo "Usage: bash scripts/release/release.sh vMAJOR.MINOR.PATCH"
    echo "The workflow publishes the production release and immediately marks it as a prerelease."
    echo "Prepare scripts/release/notes/vMAJOR.MINOR.PATCH.md before running this script."
}

if [[ $# -eq 1 && ( "$1" == "--help" || "$1" == "-h" ) ]]; then
    show_usage
    exit 0
fi
if [[ $# -ne 1 || "$1" == -* ]]; then
    show_usage >&2
    exit 1
fi
version_tag="$1"

for tool in git gh jq python3; do
    if ! command -v "$tool" >/dev/null; then
        echo "Required tool not found: $tool" >&2
        exit 1
    fi
done
gh auth status >/dev/null 2>&1
if [[ "$(git branch --show-current)" != "main" ]]; then
    echo "Run the release script from main." >&2
    exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
    echo "Commit your changes, including the release notes, before releasing." >&2
    exit 1
fi

# Fast-forward only: a release must not rewrite local or published history.
git pull --ff-only
if git show-ref --verify --quiet "refs/tags/$version_tag"; then
    echo "Tag $version_tag already exists." >&2
    exit 1
fi
for file in "$MANIFEST_PATH" README.md LICENSE; do
    if [[ ! -f "$file" ]]; then
        echo "Required release file not found: $file" >&2
        exit 1
    fi
done
notes_file=$(python3 "$SCRIPT_DIR/validate_notes.py" "$version_tag" "$(jq -r .version "$MANIFEST_PATH")")

# Keep manifest formatting and update the same version badge on Linux and macOS.
if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' "s/\"version\": *\"[^\"]*\"/\"version\": \"$version_tag\"/" "$MANIFEST_PATH"
else
    sed -i "s/\"version\": *\"[^\"]*\"/\"version\": \"$version_tag\"/" "$MANIFEST_PATH"
fi
temp_readme=$(mktemp)
trap 'rm -f "$temp_readme"' EXIT
sed -E "s|badge/version-[0-9]+[.][0-9]+[.][0-9]+-blue[.]svg|badge/version-${version_tag#v}-blue.svg|" README.md > "$temp_readme"
cat "$temp_readme" > README.md
jq -e --arg version "$version_tag" '.version == $version' "$MANIFEST_PATH" >/dev/null
grep -Fq "badge/version-${version_tag#v}-blue.svg" README.md

cat "$notes_file"
git diff --stat
read -r -p "Publish $version_tag through the production workflow? (y/n): " reply
if [[ ! "$reply" =~ ^[Yy]$ ]]; then
    echo "Release cancelled."
    exit 1
fi
if ! git diff --quiet; then
    git add -- "$MANIFEST_PATH" README.md
    git commit -m "Release $version_tag of GE-Spot"
    git push origin main
fi

git tag -a "$version_tag" -m "Release $version_tag"
git push origin "$version_tag"
echo "The workflow will publish $version_tag, then immediately mark it as a prerelease."
echo "After testing, promote the same release with:"
echo "gh release edit $version_tag --repo $REPO_NAME --prerelease=false --latest"
echo "https://github.com/$REPO_NAME/releases/tag/$version_tag"
