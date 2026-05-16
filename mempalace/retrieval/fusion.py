"""Reciprocal Rank Fusion primitives for retrieval routes."""

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True)
class RouteHit:
    route: str
    drawer_id: str
    rank: int
    raw_score: Optional[float] = None
    reason: str = ""
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RankedCandidate:
    drawer_id: str
    score: float
    route_hits: List[RouteHit]
    best_rank: int
    route_count: int
    payload: dict = field(default_factory=dict)


def rrf_score(hits: Iterable[RouteHit], route_weights: Optional[Dict[str, float]] = None, k: int = 60) -> List[RankedCandidate]:
    """Rank candidates with Cormack-style Reciprocal Rank Fusion."""

    grouped: Dict[str, List[RouteHit]] = {}
    scores: Dict[str, float] = {}
    weights = route_weights or {}
    for hit in hits:
        weight = weights.get(hit.route, 1.0)
        if weight <= 0:
            continue
        grouped.setdefault(hit.drawer_id, []).append(hit)
        scores[hit.drawer_id] = scores.get(hit.drawer_id, 0.0) + weight / (k + max(1, hit.rank))

    ranked = []
    for drawer_id, route_hits in grouped.items():
        ordered_hits = sorted(route_hits, key=lambda h: (h.rank, h.route, h.drawer_id))
        best_rank = min(h.rank for h in ordered_hits)
        routes = {h.route for h in ordered_hits}
        payload = {}
        for hit in ordered_hits:
            payload.update(hit.payload or {})
        ranked.append(
            RankedCandidate(
                drawer_id=drawer_id,
                score=scores[drawer_id],
                route_hits=ordered_hits,
                best_rank=best_rank,
                route_count=len(routes),
                payload=payload,
            )
        )

    return sorted(
        ranked,
        key=lambda cand: (-cand.score, -cand.route_count, cand.best_rank, cand.drawer_id),
    )


# ── RFC T3c: learned RRF route weights via coordinate descent ────────────

WEIGHT_BOUND_LOW = 0.1
WEIGHT_BOUND_HIGH = 5.0
_TRIAL_MULTIPLIERS = (0.5, 0.8, 1.0, 1.25, 2.0)


TrainPair = Tuple[str, Set[str]]


def _clip_weight(value: float) -> float:
    return max(WEIGHT_BOUND_LOW, min(WEIGHT_BOUND_HIGH, value))


def _route_hits_for_query(
    query: str,
    routes: Dict[str, Callable[[str], List[str]]],
) -> List[RouteHit]:
    hits: List[RouteHit] = []
    for route_name, route_fn in routes.items():
        ranked_ids = route_fn(query) or []
        for rank, drawer_id in enumerate(ranked_ids, start=1):
            hits.append(RouteHit(route=route_name, drawer_id=drawer_id, rank=rank))
    return hits


def _mean_recall_at_k(
    weights: Dict[str, float],
    train_pairs: Iterable[TrainPair],
    routes: Dict[str, Callable[[str], List[str]]],
    k_recall: int,
    rrf_k: int,
) -> float:
    pairs = list(train_pairs)
    if not pairs:
        return 0.0
    total = 0.0
    for query, relevant in pairs:
        if not relevant:
            continue
        hits = _route_hits_for_query(query, routes)
        ranked = rrf_score(hits, route_weights=weights, k=rrf_k)
        top_ids = [c.drawer_id for c in ranked[:k_recall]]
        retrieved_relevant = sum(1 for did in top_ids if did in relevant)
        total += retrieved_relevant / len(relevant)
    return total / len(pairs)


def fit_route_weights(
    train_pairs: Iterable[TrainPair],
    routes: Dict[str, Callable[[str], List[str]]],
    k: int = 60,
    n_iter: int = 20,
    k_recall: int = 5,
) -> Dict[str, float]:
    """Coordinate-descent fit for RRF route weights (RFC T3c).

    Initializes every route to 1.0; for each iteration tries each
    multiplier in (0.5, 0.8, 1.0, 1.25, 2.0) per route and keeps the
    value that maximizes mean recall@``k_recall`` across ``train_pairs``.
    Stops when no weight changes during a full sweep.

    Weights are clamped to ``[WEIGHT_BOUND_LOW, WEIGHT_BOUND_HIGH]``.
    """

    pairs_list = list(train_pairs)
    weights: Dict[str, float] = {route: 1.0 for route in routes}
    if not pairs_list or not routes:
        return weights

    for _ in range(max(1, n_iter)):
        changed = False
        for route_name in list(routes.keys()):
            current = weights[route_name]
            best_weight = current
            best_recall = _mean_recall_at_k(weights, pairs_list, routes, k_recall, k)
            for multiplier in _TRIAL_MULTIPLIERS:
                trial = _clip_weight(current * multiplier)
                if trial == best_weight:
                    continue
                weights[route_name] = trial
                trial_recall = _mean_recall_at_k(weights, pairs_list, routes, k_recall, k)
                # Strict > avoids accepting a trial that ties (keeps the
                # search deterministic and the result reproducible).
                if trial_recall > best_recall:
                    best_recall = trial_recall
                    best_weight = trial
            if best_weight != current:
                changed = True
            weights[route_name] = best_weight
        if not changed:
            break
    return weights
