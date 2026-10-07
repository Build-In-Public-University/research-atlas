# Proof-Kernel Verification

- ID: `proof-kernel-verification`
- Source repository: https://github.com/leo-guinan/bend-verdict-investigation
- Status: `candidate_family`
- Evidence ceiling: `bounded_pinned_release_investigation`

README-supported observation: one pinned Bend release was investigated; no bounty-grade falsehood was found, and one checker synchronization bug was reported.

## Claims

- `bend-verdict/readme-observation` — `readme_observed`: The investigation reports no bounty-grade falsehood in the pinned Bend 2.0.32 release and reports a reproducible checker/BendTT synchronization bug that BendTT rejects.
- `bend-verdict/corpus-results` — `report_observed`: The pinned Bend investigation reports a 1,508-file corpus with 960 verdict passes, 548 expected or intentional failures, zero timeouts, and no checker/kernel status mismatches in the corpus.

## Artifacts

- [bend-verdict/readme](https://github.com/leo-guinan/bend-verdict-investigation) — `readme_observed` (`README.md`)
- [bend-verdict/report](https://github.com/leo-guinan/bend-verdict-investigation) — `report_observed` (`REPORT.md`)
