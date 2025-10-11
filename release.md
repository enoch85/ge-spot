RELEASE=1.3.4

OK, we are ready to release $RELEASE!

Now I want you to:

1. Go to the main branch.
2. Run this: /workspaces/ge-spot/scripts/run_pytest.sh - fix any failing tests.
3. Remove all $RELEASE-beta tags
4. Remove all $RELEASE-beta releases
5. Make a new release with the release.sh script (no need to edit manifest.json)

You can use something like:
- git tag -l "v$RELEASE-beta*"

- for tag in $(git tag -l "v$RELEASE-beta*"); do git tag -d $tag; done

- for tag in v$RELEASE-beta.1 v$RELEASE-beta.2 v$RELEASE-beta.3 v$RELEASE-beta4 v$RELEASE-beta5 v$RELEASE-beta6 v$RELEASE-beta7 v$RELEASE-beta8 v$RELEASE-beta9 v$RELEASE-beta10 v$RELEASE-beta11 v$RELEASE-beta12 v$RELEASE-beta13 v$RELEASE-beta14 v$RELEASE-beta15 v$RELEASE-beta16; do git push origin :refs/tags/$tag; done

- gh release list | grep "v$RELEASE-beta"

- for tag in v$RELEASE-beta.1 v$RELEASE-beta.2 v$RELEASE-beta.3 v$RELEASE-beta4 v$RELEASE-beta5 v$RELEASE-beta6 v$RELEASE-beta7 v$RELEASE-beta8 v$RELEASE-beta9 v$RELEASE-beta10 v$RELEASE-beta11 v$RELEASE-beta12 v$RELEASE-beta13 v$RELEASE-beta14 v$RELEASE-beta15 v$RELEASE-beta16; do gh release delete $tag -y; done