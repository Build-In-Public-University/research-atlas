# Research Atlas

A cross-project index for Leo Guinan and Build-In-Public-University research.

The atlas is an index, not a replacement for source repositories. It records research families, claims, evidence boundaries, artifacts, releases, and corrections while preserving each source repository as the authority for its own content.

## Current source projects

- [The Return of Magic: Causal Compression in Adaptive Systems](https://github.com/leo-guinan/the-return-of-magic-causal-compression)
- [The Shape of Trust](https://github.com/leo-guinan/shape-of-trust-paper)
- [Build-In-Public-University research](https://github.com/Build-In-Public-University/research)
- [OpenAI math catalogue](https://github.com/openai/math) — external catalogue model

## Evidence rule

A compressed entry must preserve what was observed, what was inferred, the current evidence ceiling, and what would falsify the claim. Public availability is not the same as empirical validation or formal verification.

## Status

The atlas imports public source-repository metadata, preserves source commit and tree SHAs, checks indexed files against live default branches, builds generated family and review pages, and validates catalog references. The current generated snapshot covers 15 families, 24 claims, 27 artifacts, and 14 source manifests; OpenAI/math remains a reference-only catalogue model.

## Commands

```bash
python3 tools/atlas.py import    # fetch public GitHub metadata and tree manifests
python3 tools/atlas.py drift    # compare indexed paths with live default branches
python3 tools/atlas.py drift --check  # check for drift without writing state
python3 tools/atlas.py review   # list unresolved review events
python3 tools/atlas.py build     # build generated overview, family, digest, and review pages
python3 tools/atlas.py validate  # validate catalog references and import receipts
python3 tools/atlas.py all       # run import, drift, build, and validation stages

# Resolve a reviewed drift event without catalog mutation
python3 tools/atlas.py resolve EVENT_ID \
  --outcome no_catalog_change \
  --resolution "Reviewed; no catalog update required."
```

Import manifests record the source commit, tree SHA, branch, fetch time, and paths observed. They are receipts of repository state, not proof that the indexed claims are true.

## Layout

- `catalog/` — families, claims, artifacts, releases, corrections, extraction ledger, and review queue
- `schemas/` — machine-readable record contracts
- `sources/` — source repository manifest and import receipts
- `generated/` — generated overview, source inventory, release digest, review report, and family pages
- `tools/` — import, drift, review, resolution, build, and validation tools

The public review surface is [generated/review-report.md](generated/review-report.md). Scheduled drift checks run through [`.github/workflows/source-drift.yml`](.github/workflows/source-drift.yml); changed sources fail the run and upload the extraction ledger plus review queue as an artifact.
