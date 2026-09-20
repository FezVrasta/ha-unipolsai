# Working in this repository

A Home Assistant custom integration, installed through HACS, plus the protocol library
it runs on. Two products in one repository:

- `custom_components/unipolsai/` — the integration, served by HACS from a `vX.Y.Z` tag.
- `pyunipolsai/` — a standalone async client published to PyPI from a
  `pyunipolsai-vX.Y.Z` tag. No Home Assistant imports, its own test suite.

## Before writing integration code

Read `.claude/skills/ha-integration-conventions`. It carries the rules that are cheap now
and expensive later — unique IDs, entity naming, `entry.runtime_data`, which exception the
coordinator raises for which failure.

Other skills: `integration-tests`, `readme-style`, `brand-assets`, `cut-release`,
`hacs-publish`.

## Invariants

- **`manifest.json`'s `version` belongs to the release commit.** Set it with
  `scripts/bump-version X.Y.Z`, which writes and commits it, *before* creating the
  release. HACS serves the tagged tree, so a version applied after the tag exists is a
  version nobody installs. CI checks the two agree and fails the release if they do not.
  `pyunipolsai`'s version moves in the same commit as the manifest pin, for the reason
  below.
- **The library ships before the integration that needs it.** `manifest.json` pins
  `pyunipolsai` exactly, and Home Assistant resolves that pin from PyPI at setup —
  checking its own site-packages, not `/config/deps`, so dropping a wheel on the box
  is not enough. A pin PyPI does not have fails with "Requirements for unipolsai not
  found", which reads like a broken integration rather than a missing release. The
  `pin` job in CI fails if the manifest pins a version this repository does not
  contain.
- **`strings.json` and `translations/en.json` must be identical.** `strings.json` is the
  source; the copy in `translations/` is what Home Assistant serves. CI diffs them.
- **Unique IDs are permanent.** Changing one orphans every user's history for that
  entity.
- **`api.py` (or whatever the protocol layer is called) imports nothing from Home
  Assistant.** That is what keeps it testable without Home Assistant and liftable into
  its own package.
- The `homeassistant` floor in `hacs.json`, the pin in `requirements-test.txt` and
  `PYTHON_VERSION` in `.github/workflows/ci.yml` move together.

## Checks

```bash
scripts/setup   # once
scripts/test    # ruff, the translations diff, pytest
```

CI additionally runs hassfest and the HACS action. Ruff is configured to mirror Home
Assistant core's own settings, so code here needs no reformatting if it is ever
upstreamed.

## Commits

Present-tense summary line, and a body that says *why* rather than restating the diff —
match the surrounding `git log`. Never amend, squash or rebase a commit already pushed to
a PR branch.
