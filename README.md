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

The atlas imports public source-repository metadata, preserves source commit and tree SHAs, builds deterministic family pages, and validates catalog references. The first generated snapshot covers three source repositories; OpenAI/math remains a reference-only catalogue model.

## Commands

```bash
python3 tools/atlas.py import    # fetch public GitHub metadata and tree manifests
python3 tools/atlas.py build     # build generated overview and family pages
python3 tools/atlas.py validate  # validate catalog references and import receipts
python3 tools/atlas.py all       # run all three stages
```

Import manifests record the source commit, tree SHA, branch, fetch time, and paths observed. They are receipts of repository state, not proof that the indexed claims are true.

## Layout

- `catalog/` — families, claims, artifacts, releases, and corrections
- `schemas/` — machine-readable record contracts
- `sources/` — source repository manifest and import receipts
- `generated/` — future derived views
- `tools/` — future import and validation tools
