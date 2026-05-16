<!--
DRAFT — Topology Layer README section.

This file is the working draft for the Phase 9 README addition. It uses
ONLY phrasing allowed by MEMPALACE_TOPOLOGY_SPEC.md §15.1 and marks
every claim with its claim-ledger status. Items whose ledger entry is
`publishable: false` are tagged [EXPERIMENTAL — pending Phase 8] so a
careless copy-paste into README.md cannot accidentally publish them.

Do NOT publish this file as-is. The Phase 9 release protocol requires:
1. `mempalace claims audit --require-signoffs` passes.
2. A maintainer-signed sign-off YAML under `mempalace/evidence/sign_offs/`
   exists for every claim id appearing below.
3. Forbidden-phrase scan passes.
-->

# Topology Layer

The topology layer extends MemPalace with deterministic candidate-route
generation, a gap graph for stale memories, retrieval traces, and rank
fusion. Each capability has a claim-ledger entry; status reflects what
the current evidence supports.

## What it adds

- **Deterministic topology-derived candidate routes.** Adds deterministic
  topology-derived candidate routes.
  Claim: `claim_topology_coord_deterministic`.
  Status: [EXPERIMENTAL — pending Phase 8].
  Implementation-supported coordinates are deterministic per drawer +
  palace salt; the held-out retrieval-quality claim
  `claim_topology_routes_improve_recall` remains experimental until
  benchmark evidence ships.

- **Gap graph for stale, contradicted, and superseded memories.** Adds a
  gap graph for stale, contradicted, and superseded memories.
  Claims:
  - `claim_gap_graph_feature_gated` — Status: implementation-supported.
  - `claim_gap_state_machine_enforced` — Status: implementation-supported.
  - `claim_gap_reduces_stale_answers` — Status:
    [EXPERIMENTAL — pending Phase 8].

- **Retrieval traces.** Adds retrieval traces explaining which routes
  found each memory.
  Claim: `claim_trace_recall_stub_unavailable`.
  Status: implementation-supported — the MCP tool is a non-claiming stub
  until trace evidence packs ship.

- **Reciprocal Rank Fusion.** Uses Reciprocal Rank Fusion to combine
  independent retrieval routes.
  Claim: `claim_rrf_source_supported`.
  Status: source-supported (Cormack, Clarke, Büttcher; SIGIR 2009).

- **Typed relations with mirror-write closure.** Stores typed relations
  with mirror-write closure for symmetric classes.
  Claim: `claim_schema_migrations_reversible`.
  Status: implementation-supported.

## What we do not claim

- No physical, biological, energy, or empirical-resonance effect is
  derived from the topology layer.
  Claim: `claim_physical_effects_rejected`. Status: source-supported.

- No retrieval-quality improvement on any public benchmark.
  Held-out benchmark numbers are pending Phase 8 sealed evaluation;
  until then `claim_topology_routes_improve_recall`,
  `claim_gap_reduces_stale_answers`, and
  `claim_balanced_wakeup_improves_session_start` stay experimental and
  non-publishable.

## Operational guarantees

- **Verbatim storage.** MemPalace stores drawer text verbatim — never
  summarized, paraphrased, or lossy-compressed.
  Claim: `claim_verbatim_storage`. Status: source-supported.

- **Append-only after build.** MemPalace storage is append-only after
  initial build. Claim: `claim_append_only`. Status: source-supported.

- **Local-first by default.** MemPalace operates local-first; no
  external APIs are required by default.
  Claim: `claim_local_first`. Status: source-supported.

<!--
Footer for the sign-off audit:

When this section is promoted to README.md, run:

    mempalace claims signoff <claim_id> --surface README.md --reviewer <name>

for each claim id referenced above whose ledger entry is publishable,
then `mempalace claims audit --require-signoffs` must pass before tagging
the release.
-->
