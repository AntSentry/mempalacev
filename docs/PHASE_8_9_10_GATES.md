# Phase 8-10 Gates

## Phase 8 — gated sealed evaluation

Phase 8 is not part of unattended implementation. It requires all of the following prerequisites:

- Phase 7 validation results are complete and committed.
- The git working tree is clean.
- Sealed test split files are present under `benchmarks/data/<benchmark>/test_split.jsonl`.
- A maintainer explicitly approves the one-shot sealed run.
- `mempalace/evidence/contamination_log.yaml` has no prior test-set run for the same dataset SHA.

Execution protocol:

1. Tag the implementation commit for the sealed evaluation candidate.
2. Run `python -m eval.ablations --set test --rows A0-A8 --seal` exactly once.
3. Commit only the generated test result files, manifest, summary, contamination-log entry, and claim-ledger updates.
4. Promote only statistically supported claims to `benchmark_supported`; unsupported claims remain `experimental` and non-publishable.

## Phase 9 — gated public release

Phase 9 is manual because public claims and tags require maintainer sign-off.

Prerequisites:

- Phase 8 sealed results are committed.
- Claim ledger audit passes.
- Public claim wording is approved.

Execution protocol:

1. Update public documentation only with source-supported or benchmark-supported claims.
2. Run the forbidden-phrase scan against public surfaces.
3. Create sign-off YAML entries for each public-facing claim.
4. Run `mempalace claims audit`.
5. Tag the release commit.

## Phase 10 — deferred Tier 3 roadmap

Phase 10 items are independent post-release RFC projects:

- Learned RRF route weights.
- Cached evidence packs by query fingerprint.
- Per-wing translation operators.
- Multi-series cell verifier with opt-in repair.
- Closed-form query mode enum at the MCP boundary.

Each item must begin with an RFC under `docs/rfcs/`, add an experimental claim-ledger entry, and evaluate as a new ablation row after implementation.
