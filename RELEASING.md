# Releasing TalkPipe

There is no version string to bump. The package version is derived from the
git tag by `setuptools_scm`, so a release is a tag plus a published release
that triggers the publish workflow.

## Tag conventions

Tags are PEP 440 versions with a `v` prefix, on `develop`:

| Kind        | Tag          | Example      |
|-------------|--------------|--------------|
| Final       | `vX.Y.Z`     | `v1.0.0`     |
| Beta        | `vX.Y.ZbN`   | `v1.0.0b2`   |
| Release candidate | `vX.Y.ZrcN` | `v1.0.0rc1` |

Do not use other spellings (`v1.0.0-beta.1`, `v1.0.0.b1`) — they exist in old
history and only made version sorting harder. Semantic versioning rules
(what may change in a PATCH / MINOR / MAJOR) are in
`docs/contributing/developer-handbook.md`.

## Steps

1. **Check the tree.** `develop` is up to date, CI is green on it, and the
   working tree is clean.
2. **Changelog.** Rename the `## Unreleased` section in `CHANGELOG.md` to
   `## X.Y.Z (YYYY-MM-DD)` and add a fresh empty `## Unreleased` above it.
   Land that through the normal branch → merge request flow.
3. **Tag** the merge commit on `develop` and push the tag:

   ```bash
   git checkout develop && git pull
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```

4. **Publish a release** for the tag (Gitea: *Releases → New Release*;
   GitHub mirror: *Releases → Draft a new release*). The CI workflow's
   `release: published` trigger runs `publish-package`, which builds the
   sdist and wheel, `twine check`s them, and uploads to PyPI with the
   `PYPI_API_TOKEN` repository secret. Mark betas and release candidates as
   pre-releases. Watch the run finish; the package job and the container build
   (GitHub only) run in the same workflow.
5. **Fast-forward `main`.** `main` is the stable branch and should point at
   the latest final release (it may also carry a release candidate that is
   worth pinning):

   ```bash
   git checkout main && git pull
   git merge --ff-only vX.Y.Z
   git push origin main
   ```

6. **Verify** with a fresh environment: `pip install talkpipe==X.Y.Z`,
   `python -c "import talkpipe; print(talkpipe.__version__)"`.

Nothing is bumped afterwards; the next commit on `develop` reports itself as
`X.Y.(Z+1).devN` automatically.

## Downstream

The consumers in this suite pin a floor on talkpipe (`talkpipe_vault`,
`talkpipe-agents`, `talkpipe-writing-assistant`, `privateer`, `local-m2v`).
When a release adds API they rely on, or when the major version changes,
raise their floors in a follow-up merge request in each repo.
