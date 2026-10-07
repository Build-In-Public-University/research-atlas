# Navier–Stokes Validation Architecture

- ID: `navier-stokes-validation`
- Source repository: https://github.com/leo-guinan/ns-validation
- Status: `candidate_family`
- Evidence ceiling: `unvalidated_extracted_ledger`

README-supported observation: the project defines a conservative extraction pipeline and explicitly does not claim to solve Navier–Stokes.

## Claims

- `ns-validation/readme-boundary` — `readme_observed`: The project implements conservative extraction into a JSON ledger and text report and explicitly does not claim to solve Navier–Stokes.
- `ns-validation/source-ledger-status` — `ledger_observed`: The source ledger marks reported search scale, proof length, and formalization time as unverified, while treating compression and reuse-break-even formulas as locally checked definitions.

## Artifacts

- [ns-validation/readme](https://github.com/leo-guinan/ns-validation) — `readme_observed` (`README.md`)
- [ns-validation/source-ledger](https://github.com/leo-guinan/ns-validation) — `ledger_observed` (`data/source-ledger.json`)
