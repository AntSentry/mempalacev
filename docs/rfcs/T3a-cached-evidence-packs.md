# RFC T3a — Cached Evidence Packs by Query Fingerprint

**Status:** Draft (Phase 10 Tier 3 — experimental)
**Author:** mempalace engineering
**Tracking:** `claim_evidence_pack_cache_correctness`

## 1. Purpose

`build_evidence_pack` is currently invoked on every traced-recall request. It
re-queries `gap_events` (for the stale partition) and walks
`find_contradictions` (for the contradicting partition) every time, even when
the underlying palace has not changed since the last identical query.

For repeated agent-side queries — especially in benchmark loops, ablation
runs, and warm session-startup wake-up — this work is fully redundant. A
content-addressed cache keyed on `(query, palace_state_version)` returns the
exact same `EvidencePack` instance without re-querying.

This RFC adds an opt-in in-memory LRU cache, with optional disk persistence
behind an env flag. **Drawer text is never cached** — only the partitioned
drawer-id lists in `EvidencePack`.

## 2. Query fingerprint

```
fingerprint = blake2b(
    normalized_query.encode("utf-8") + b"\x00" + str(palace_write_seq).encode("utf-8"),
    digest_size=16,
).hexdigest()
```

Where:
- `normalized_query = " ".join(query.lower().strip().split())` — collapses
  whitespace and casing differences so trivially-different queries share a
  cache slot.
- `palace_write_seq` is a monotonic counter that increments on every palace
  write (drawer add/update/delete, KG add/invalidate, gap-event transition).

## 3. Cache invalidation rule

**Any palace write bumps `palace_write_seq`, which invalidates every cached
pack.** No partial invalidation. This is intentional:

- Correctness over hit rate. Partial invalidation requires reasoning about
  which queries could have surfaced a newly-added/modified drawer; the cost
  of getting that wrong is a stale evidence pack, which is the exact failure
  mode evidence packs exist to prevent.
- The append-only invariant (CLAUDE.md) means writes are bounded; cache
  thrash is acceptable.
- Cache hits are still common in the dominant access pattern: an agent
  asking the same question multiple times within one read-only session.

## 4. TTL

No wall-clock TTL. Eviction is purely:

1. **Version mismatch** — cached entry's `palace_write_seq` does not match
   the current value. (This is checked on `get`; the cache may still hold
   stale entries until they are evicted or queried.)
2. **LRU pressure** — when the cache exceeds `MAX_ENTRIES` (default 256,
   configurable via `MEMPALACE_EVIDENCE_CACHE_SIZE`), the least-recently-used
   entry is evicted.

## 5. Max size

- In-memory: `MAX_ENTRIES = 256` entries (overridable via env).
- Disk (when enabled): no hard cap; on-disk files are pruned lazily when
  `palace_write_seq` advances and a new write would otherwise create the
  257th in-memory entry. A future RFC may add explicit disk-side eviction.

## 6. File location

- In-memory: process-local `EvidencePackCache` instance.
- Disk (opt-in via `MEMPALACE_EVIDENCE_CACHE_DISK=1`):
  `~/.mempalace/cache/evidence_packs/<fingerprint>.json`. The JSON shape
  mirrors `dataclasses.asdict(pack)`. Files are atomically written
  (`write to .tmp + rename`).

## 7. Wire-in

`build_evidence_pack` accepts an optional `cache: EvidencePackCache` and an
optional `palace_write_seq: int` argument. When both are provided:

- Compute fingerprint; if cache hit and version matches, return the cached
  pack without invoking gap-graph or contradiction queries.
- Otherwise compute the pack normally and store it.

When either is omitted, behavior is unchanged (default off).

## 8. Out of scope

- Translating the cache layer to multi-process (would require a SQLite
  cache backend and a real version-bump notification — both deferred to a
  future RFC).
- Caching `serialize_trace` output (covered by the same fingerprint, but
  the trace contains route metadata that drifts with searcher changes;
  cache it independently if needed).
- Caching at the searcher layer (orthogonal — `searcher.search_memories`
  results are already cheap-ish and can change with HNSW state).
