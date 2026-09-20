---
name: cut-release
description: >-
  Cut a new tagged release of this Home Assistant integration. Use when asked to
  "release", "cut a release", "ship a version", or publish a new vX.Y.Z. Covers the
  version scheme, the fact that manifest.json is bumped automatically by CI and never by
  hand, the commit and release-notes conventions, and how to verify the release landed.
---

# Cutting a release

A release is a GitHub release with a `vX.Y.Z` tag. HACS serves the tagged tree, so the
tag is the whole delivery mechanism, and whatever `manifest.json` says inside that tag is
what every installation reports.

## The one thing that trips people up

**The version has to be committed before the tag, not after.** `scripts/bump-version
0.13.0` writes `manifest.json` and commits it; push that, then create the release. Do it
the other way round and the tag contains the previous version: the release page says
v0.13.0 while everyone who installs it sees 0.12.0.

This is what `release.yml` used to get wrong. It now only *checks* that the tagged
manifest matches the tag, and fails the release if it does not.

Do not hand-edit the version either. `scripts/bump-version` refuses on a dirty tree, on
a tag that already exists, and on a version that is already set, all of which are
mistakes worth catching before a tag is permanent.

## Version scheme

- Tags are v-prefixed semver: `v0.13.0`.
- While still `0.x`, a normal change — feature or fix — is a **minor** bump
  (`0.12.0` → `0.13.0`). Reserve a patch bump for a same-day follow-up to a release that
  shipped broken.
- Check the last tag first: `git tag --sort=-creatordate | head -1`.

## Steps

1. **Be releasable.** On `main`, working tree clean, and green:
   ```bash
   scripts/test
   ```
   CI additionally runs hassfest and the HACS action on every push. Don't ship red.

2. **Verify on a real Home Assistant.** A green suite is not the finish line. Deploy the
   changed files to a test instance, restart, and exercise the change. A config-entry
   reload is *not* enough — Python caches imported modules, so code changes need a full
   restart.

   If the integration ships frontend assets, **bump the manifest version on the test box
   too, or you are testing the old panel.** Panels are usually registered as
   `…/panel.js?v={integration.version}`, so the browser keys its cache on the version in
   the *installed* `manifest.json`. Deploying the JS alone leaves the URL unchanged and
   the browser serves the cached copy forever; a restart does not help. Then confirm what
   is actually being served — `grep` the deployed file for a string only your change
   contains — before believing any UI result. This has burned whole debugging sessions.

3. **Bump the version.**
   ```bash
   scripts/bump-version 0.13.0
   git push origin main
   ```
   Nothing else should be uncommitted when you do this: the tag should point at the
   tree you tested.

4. **Commit the content.** One commit per logical change, present-tense summary line, and
   a body that says *why*. Match the surrounding `git log`, which is discursive and
   explains reasoning rather than restating the diff. No attribution trailers: the commit
   is yours, so write it the way you write the rest of them. Then `git push origin main`.

5. **Create the release.** `gh release create` tags `HEAD`, which is now the version
   commit. Write notes to a file and:
   ```bash
   gh release create vX.Y.Z --title "vX.Y.Z" --notes-file /tmp/release-X.Y.Z.md
   ```
   Notes tone: plain and direct, lead with the essence in one or two lines, `##` sections
   ("Fix", "New", …), and — while the project is pre-1.0 — close with a standing line
   saying so. Read the previous release for the voice: `gh release view <lasttag>`.

6. **Verify it landed.**
   ```bash
   gh run list -L 5   # the "Release" run should be success
   git show vX.Y.Z:custom_components/*/manifest.json | grep version
   ```
   The version inside the *tag* is the one that matters. If the Release run failed, the
   two disagree: the release is out with the wrong version, so bump, push, and cut a
   patch release rather than moving the tag, which people may already have fetched.

## Releasing the library

`pyunipolsai` has its own train, because PyPI and HACS are different delivery
mechanisms with different tags.

**Order matters.** The integration pins the library exactly and Home Assistant resolves
that pin from PyPI when the entry sets up. The library has to be on PyPI before the
integration release that needs it, or installs fail with "Requirements for unipolsai
not found".

**Bump the library version and the manifest pin in the same commit.** The `pin` job
compares them, so moving one without the other leaves CI red. This is the one place the
"never edit a version by hand" rule does not hold: the release workflow will set the
library version to the same value from the tag, so the two agree and its commit-back is
a no-op.

```bash
# 1. one commit: library version + manifest pin, both to the new number
git commit -am "..." && git push origin main    # CI green, pin job agrees

# 2. library to PyPI
git tag pyunipolsai-v0.2.0 && git push origin pyunipolsai-v0.2.0
gh run watch                       # build -> publish -> version commit-back

# 3. integration, once the library is visible on PyPI
gh release create v0.2.0 --title "v0.2.0" --notes-file /tmp/notes.md
```

Publishing uses PyPI trusted publishing, so there is no token to rotate. It needs a
one-time publisher configured on PyPI for this repository, workflow
`release-library.yml`, environment `pypi`. Until that exists the `publish` job fails
with an OIDC error and nothing is uploaded, which is the safe direction.

A version is permanent on PyPI: it cannot be replaced, only yanked. Build locally first
if in doubt:

```bash
.venv/bin/python -m build pyunipolsai && .venv/bin/python -m twine check pyunipolsai/dist/*
```

## Notes

- Releases go out from `main` directly. No release branch.
- **Never amend, squash, or rebase a commit already pushed to a PR branch** — history is
  meant to be followed.
- If CI on the tagged commit fails after the release is out, fix forward with a patch
  release rather than deleting the tag. Someone has already installed it.
