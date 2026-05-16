<!--
DRAFT — CHANGELOG entry template for the topology-layer release.

This template is pre-filled with implementation-supported items
(safe to publish) and benchmark-supported placeholders marked
`[Pending Phase 8]` (NOT safe to publish until sealed evaluation lands).

Promotion checklist before pasting into CHANGELOG.md:

1. Replace `vX.Y.Z` and `YYYY-MM-DD` with the actual release version + date.
2. Replace every `[Pending Phase 8]` placeholder with the actual delta + CI from
   the sealed run, or remove the line entirely if the benchmark did not
   support a publishable improvement.
3. Run `mempalace claims audit --require-signoffs` against CHANGELOG.md.
4. Run the forbidden-phrase scan (it is part of `claims audit`).
-->

## [vX.Y.Z] — YYYY-MM-DD

### Added

- Deterministic topology-derived candidate routes for retrieval.
  Implementation-supported via `tests/test_topology_coordinates.py`.
  Claim id: `claim_topology_coord_deterministic`.
- Gap graph for stale, contradicted, and superseded memories, gated by
  `MEMPALACE_ENABLE_GAP_GRAPH`. Implementation-supported.
  Claim ids: `claim_gap_graph_feature_gated`,
  `claim_gap_state_machine_enforced`.
- Retrieval traces explaining which routes found each memory.
  Implementation-supported stub at the MCP boundary.
  Claim id: `claim_trace_recall_stub_unavailable`.
- Reciprocal Rank Fusion across independent retrieval routes
  (Cormack, Clarke, Büttcher; SIGIR 2009). Source-supported.
  Claim id: `claim_rrf_source_supported`.
- Reversible topology-layer schema migrations.
  Implementation-supported.
  Claim id: `claim_schema_migrations_reversible`.
- Sealed-evaluation protocol with contamination-log enforcement and
  emergency-unseal audit trail (`eval/ablations.py --seal`,
  `--unseal-emergency`). Implementation-supported.
  Claim id: `claim_seal_protocol_enforced`.
- Public-benchmark adapter scaffolds for LongMemEval, LoCoMo, ConvoMem,
  and MemBench. Implementation-supported on the local dev split.
  Claim id: `claim_benchmark_adapters_load_dev_split`.
- Sign-off generator + audit hook for public-facing claims
  (`mempalace claims signoff`, `mempalace claims audit
  --require-signoffs`). Implementation-supported.
  Claim id: `claim_signoff_required_for_publishable`.
- Pre-commit hook scaffold that runs claims audit + ruff + a fast test
  subset. Implementation-supported.
  Claim id: `claim_pre_commit_runs_audit`.

### Changed

- Ablation runner now records dataset SHA before every sealed run and
  appends a contamination-log entry on success.
  Implementation-supported.

### Deprecated

- None this release.

### Security

- No new external-API dependencies. Local-first architecture unchanged.
  Claim id: `claim_local_first`.

### Phase status

- Phase 7 validation results: committed.
- Phase 8 sealed evaluation: `[Pending Phase 8]`.
- Held-out retrieval-quality benchmark deltas:
  - Topology routes vs. baseline: `[Pending Phase 8]`.
  - Gap graph on stale-fact queries: `[Pending Phase 8]`.
  - Balanced wake-up on session-start tasks: `[Pending Phase 8]`.
