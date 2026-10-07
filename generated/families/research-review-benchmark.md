# Research Review Benchmark

- ID: `research-review-benchmark`
- Source repository: https://github.com/Build-In-Public-University/research-review-benchmark
- Status: `candidate_family`
- Evidence ceiling: `calibrated_repository_audit`

README-supported observation: the tool performs a reproducible first-pass audit with adversarial verification and exact token/cost receipts; it is not peer review.

## Claims

- `review-benchmark/audit-boundary` — `readme_observed`: The review benchmark freezes a repository revision, audits the same evidence with an adversarial pass, and emits exact model token/cost receipts; it is explicitly not peer review or an endorsement.
- `review-benchmark/collision-ideals-run` — `receipt_observed`: The curated benchmark record reports a two-pass GPT-5.2 audit at 220,398 tokens and $0.53486675, with verdict pass_with_corrections and three listed verification errors; publication was not attempted.

## Artifacts

- [review-benchmark/readme](https://github.com/Build-In-Public-University/research-review-benchmark) — `readme_observed` (`README.md`)
- [review-benchmark/collision-ideals](https://github.com/Build-In-Public-University/research-review-benchmark) — `receipt_observed` (`benchmarks/collision-ideals/benchmark.json`)
