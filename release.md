# GE-Spot releases

1. Make a production release with the release script, following semantic versioning:

   ```bash
   bash scripts/release/release.sh vMAJOR.MINOR.PATCH
   ```

   Run from a clean, current `main` after tests pass. Prepare and commit the release notes using [the template](scripts/release/notes-template.md).

2. Immediately after the release is published, mark it as a prerelease. The release workflow does this automatically in the next command after publication.

The owner can test this exact release before marking it as latest:

```bash
gh release edit vMAJOR.MINOR.PATCH --repo enoch85/ge-spot --prerelease=false --latest
```

Promotion keeps the same version, tag, release notes and ZIP. See [the release guide](scripts/release/make_release.md) for preparation and verification.
