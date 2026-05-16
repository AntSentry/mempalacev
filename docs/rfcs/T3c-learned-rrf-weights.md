# RFC T3c — Learned RRF Route Weights via Coordinate Descent

**Status:** Draft (Phase 10 Tier 3 — experimental)
**Author:** mempalace engineering
**Tracking:** `claim_learned_rrf_weights_converge`

## 1. Purpose

`mempalace.retrieval.fusion.rrf_score` accepts a `route_weights: dict[str,
float]` argument that defaults to `1.0` for every route. In practice some
routes are noisier than others — vector retrieval is strong on narrative
prose but weak on terminology lookups; BM25 is the inverse; KG-temporal
helps current-state queries but hurts free-text recall; topology-axis is
high-precision but low-recall.

Hand-tuning weights is fragile and gets stale as the corpus shifts. This
RFC adds a small coordinate-descent fitter that takes a list of `(query,
relevant_drawer_ids)` training pairs and returns a `{route: weight}` dict
that maximizes mean recall@5 across those pairs.

## 2. Training pair format

```python
TrainPair = Tuple[str, Set[str]]
# (query_text, set_of_relevant_drawer_ids)
```

A small training set (50–500 pairs) is enough for coordinate descent to
converge on a meaningful weight assignment. The fitter is route-agnostic —
it accepts any callable `routes: Dict[str, Callable[[str], List[str]]]`
where each route maps a query to a ranked list of drawer ids.

## 3. Coordinate descent algorithm

```
weights = {route: 1.0 for route in routes}
for iteration in range(n_iter):
    changed = False
    for route in routes:
        best_weight = weights[route]
        best_recall = mean_recall_at_5(weights, train_pairs)
        for multiplier in (0.5, 0.8, 1.0, 1.25, 2.0):
            trial = max(0.1, min(5.0, weights[route] * multiplier))
            weights[route] = trial
            recall = mean_recall_at_5(weights, train_pairs)
            if recall > best_recall:
                best_recall = recall
                best_weight = trial
        weights[route] = best_weight
        if best_weight != initial_weight_for_route:
            changed = True
    if not changed:
        break
return weights
```

This is intentionally simple — five trial multipliers per coordinate, one
sweep per iteration, early stop when no weight moved. We are not competing
with a learning-to-rank toolkit; we want a deterministic, dependency-free
fitter that produces interpretable weights.

## 4. Weight bounds

`[0.1, 5.0]`. Lower bound prevents zero-weighting a route entirely
(routes can be disabled at the searcher layer; the weight fitter is for
*relative emphasis*). Upper bound prevents one route from dominating to
the point where RRF degrades to single-source ranking — that defeats the
purpose of fusion.

## 5. Saved-weights file

```
~/.mempalace/rrf_weights.json
```

Shape:

```json
{
  "weights": {"vector": 1.25, "bm25": 1.0, "kg_temporal": 0.8},
  "fitted_at": "2026-05-15T12:00:00Z",
  "train_pair_count": 137,
  "n_iter_used": 4
}
```

Atomically written (`write to .tmp + rename`). Path is overridable for
tests via the `path=` kwarg on `save_route_weights`/`load_route_weights`.

## 6. Opt-in

Loading happens only when `MEMPALACE_USE_LEARNED_WEIGHTS=1`. When the
flag is off, `load_route_weights()` returns `{}` (which triggers RRF's
default uniform behavior). When the flag is on but the file is missing,
the loader returns `{}` as well — never errors.

## 7. Out of scope

- Online learning. Fitting is a deliberate, offline action triggered by
  a maintainer running the fitter against a curated training set.
- Per-wing weights. A future RFC may add `~/.mempalace/rrf_weights/<wing>.json`
  fall-through; this RFC does global weights only.
- Anything resembling a published-claim improvement number. The claim
  tracked here is **convergence**, not lift — lift requires a sealed
  benchmark run (Phase 8).
