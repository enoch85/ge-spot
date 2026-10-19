# Releasing GE-Spot

1. **Make a production release with the release script, following semantic versioning.**
2. **Immediately after publication, make it a prerelease.** The workflow performs this automatically so the owner can test the published package before promoting it to latest.

## Prepare the release

Choose `vMAJOR.MINOR.PATCH`:

- Increase MAJOR for breaking changes.
- Increase MINOR for compatible new features.
- Increase PATCH for fixes and compatible small improvements.

Use a normal production version such as `v1.9.2`. Prerelease status is a GitHub release flag; the version and tag keep the same name when promoted.

Work from current `main`. Run the tests on Python 3.15 and fix failures before publishing:

```bash
bash scripts/run_pytest.sh
python -m pytest -q
black --check .
flake8 . --select=E9,F63,F7,F82
```

Prepare `scripts/release/notes/vMAJOR.MINOR.PATCH.md` from [notes-template.md](notes-template.md), replacing every placeholder. Follow [v1.6.3](https://github.com/enoch85/ge-spot/releases/tag/v1.6.3):

- `## What's Changed`: merged changes with author and pull-request links.
- `### Key Changes`: concise bullets with bold names describing the changes users will see.
- `**Full Changelog**`: a comparison URL from the previous version to this version.

Commit the code and release notes before running the script. The script requires a clean checkout and validates the version and notes before creating a tag. Git, authenticated GitHub CLI, jq and Python 3 are required.

## Publish and hold for owner testing

From the repository root:

```bash
bash scripts/release/release.sh vMAJOR.MINOR.PATCH
```

The script fast-forwards `main`, updates `custom_components/ge_spot/manifest.json` and the README badge, commits and pushes those changes when necessary, then pushes the annotated version tag.

The tag triggers `.github/workflows/release.yml`. It packages `ge_spot/`, `README.md` and `LICENSE` into `ge_spot.zip`, then runs `scripts/release/publish.sh` to:

1. Publish the production release with the committed release notes and ZIP.
2. Immediately mark that same release as a prerelease and clear its latest flag.

Both operations run together. A transient conversion failure is retried; a persistent failure makes the workflow fail and needs immediate attention.

Check that the workflow succeeded, the release is published with the prerelease flag, and the ZIP manifest contains the requested version. Existing tags and packages are retained.

## Promote after testing

After the owner tests the package, edit the release on GitHub: clear **Set as a pre-release** and mark it as the latest release. The equivalent command is:

```bash
gh release edit vMAJOR.MINOR.PATCH --repo enoch85/ge-spot --prerelease=false --latest
```

This promotes the exact package already tested. Do not rerun the release script or create another tag or version for promotion.
