# RFC T3b — Closed-Form Query Mode Enum at the MCP Boundary

**Status:** Draft (Phase 10 Tier 3 — experimental)
**Author:** mempalace engineering
**Tracking:** `claim_query_mode_enum_distinct`

## 1. Purpose

The MCP `mempalace_search` tool currently accepts an unbounded query string
plus a handful of optional filters. Agents (and tests, and benchmarks) tend
to want a small number of well-named query *shapes* — "summary view of X",
"contrast X against its opposite", "find sibling drawers" — rather than
tuning ad-hoc filter combinations.

A closed-form enum at the MCP boundary:

1. Surfaces the query shapes as named, discoverable operations.
2. Lets us fingerprint and cache each shape (RFC T3a) more aggressively.
3. Makes ablation rows reproducible — "row A9 = MIRROR_VIEW only" instead
   of "row A9 = vector + KG-temporal + topology-axis with negation flag".
4. Gives us a coverage check: every prior search query in the test corpus
   must be expressible as one of the modes. If not, we know what's missing.

## 2. The closed enum

```python
class QueryMode(str, Enum):
    DIRECT_RECALL  = "direct_recall"
    SUMMARY_VIEW   = "summary_view"
    CONTRAST_VIEW  = "contrast_view"
    MIRROR_VIEW    = "mirror_view"
    FAMILY_VIEW    = "family_view"
    POLAR_VIEW     = "polar_view"
```

Six modes. New modes require a new RFC; the closed-form contract is the
whole point.

## 3. Mode → flag-set mapping

Each mode is a closed-form combination of four parameters:

| Mode | step_size | ray_count | polarity_filter | status_filter |
|------|-----------|-----------|-----------------|----------------|
| DIRECT_RECALL  | 0 | 1 | any      | active         |
| SUMMARY_VIEW   | 1 | 3 | any      | active         |
| CONTRAST_VIEW  | 1 | 2 | opposite | active         |
| MIRROR_VIEW    | 2 | 2 | any      | active         |
| FAMILY_VIEW    | 1 | 4 | any      | active         |
| POLAR_VIEW     | 2 | 6 | opposite | any            |

Where:
- `step_size` — how many edges out from the seed drawer to walk
  (0 = the seed itself; 1 = direct neighbors; 2 = neighbors-of-neighbors).
- `ray_count` — how many independent retrieval rays to fuse via RRF
  (1 = vector-only; ≥2 enables fusion).
- `polarity_filter` — `any` includes both sides of contradictory triples;
  `opposite` deliberately surfaces the *other* side of the seed's polarity.
- `status_filter` — `active` excludes superseded/rejected gap events;
  `any` includes the historical record.

These mappings are documented as a single `MODE_FLAGS` dict in
`mempalace/retrieval/query_modes.py` so that adding a 7th mode requires a
single edit there plus the enum and a test row — no scattered changes.

## 4. MCP tool signature

```python
def mempalace_search_with_mode(
    query: str,
    mode: str,            # one of QueryMode values
    wing: str = None,
    k: int = 10,
) -> dict:
    ...
```

Returns the same shape as `mempalace_search` plus a `mode` echo and a
`mode_flags` field that exposes the resolved flag-set. Errors out cleanly
on unknown mode strings.

A companion `mempalace_list_query_modes(wing=None)` returns the enum
membership and per-mode flag-set so agents can discover what's available.

## 5. Feature flag

Both new tools are gated by `MEMPALACE_ENABLE_QUERY_MODES=1`. When the
flag is off, calling `mempalace_search_with_mode` returns a structured
error — never silently falls back, never raises raw `NotImplementedError`
into the MCP wire (which would crash the agent loop).

## 6. Out of scope

- Routing per-mode through learned RRF weights (RFC T3c handles weights
  separately — modes are orthogonal).
- Returning `EvidencePack` directly from these tools (a future RFC may
  unify search + traced-recall under modes).
- Mode chaining (e.g. "MIRROR_VIEW after SUMMARY_VIEW") — handled at the
  agent layer for now.

## 7. Coverage check

Tests assert that every query in `tests/conftest.py::seeded_collection`
plus a small fixed list of representative queries can be answered by one
of the six modes. Failures here mean the enum is too narrow.
