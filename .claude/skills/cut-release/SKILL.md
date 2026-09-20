---
name: cut-release
description: >-
  Cut a new tagged release of this Home Assistant integration. Use when asked to
  "release", "cut a release", "ship a version", or publish a new vX.Y.Z. Covers the
  version scheme, the fact that manifest.json is bumped automatically by CI and never by
  hand, the commit and release-notes conventions, and how to verify the release landed.
---

# Cutting a release

A release is a GitHub release with a `vX.Y.Z` tag. Publishing it triggers
`.github/workflows/release.yml`, which sets `manifest.json`'s version from the tag and
commits it as `github-actions[bot]`. That is the whole delivery mechanism — HACS serves
the tagged commit.

## The one thing that trips people up

**Do not edit `manifest.json`'s `version` yourself.** The release workflow does it from
the tag name (`v0.13.0` → `0.13.0`) and pushes a `Set version to vX.Y.Z` commit
afterwards. Bumping it by hand gives you a duplicate, conflicting change. Your job is to
commit the *content* and create the *release*; the version follows the tag.

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

3. **Commit the content.** One commit per logical change, present-tense summary line, and
   a body that says *why*. Match the surrounding `git log`, which is discursive and
   explains reasoning rather than restating the diff. End every commit with the trailer:
   ```
   Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
   ```
   Then `git push origin main`.

4. **Create the release.** Write notes to a file and:
   ```bash
   gh release create vX.Y.Z --title "vX.Y.Z" --notes-file /tmp/release-X.Y.Z.md
   ```
   Notes tone: plain and direct, lead with the essence in one or two lines, `##` sections
   ("Fix", "New", …), and — while the project is pre-1.0 — close with a standing line
   saying so. Read the previous release for the voice: `gh release view <lasttag>`.

5. **Verify it landed.**
   ```bash
   gh run list -L 5   # the "Release" run should be success
   git fetch origin main && git show origin/main:custom_components/*/manifest.json | grep version
   ```
   The manifest should read the new version, committed by `github-actions[bot]`. Then
   `git pull --ff-only` so local main includes that bump.

## Notes

- Releases go out from `main` directly. No release branch.
- **Never amend, squash, or rebase a commit already pushed to a PR branch** — history is
  meant to be followed.
- If CI on the tagged commit fails after the release is out, fix forward with a patch
  release rather than deleting the tag. Someone has already installed it.
