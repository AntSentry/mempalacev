"""Retrieval trace construction."""

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class RouteAttribution:
    route: str
    rank: int
    reason: str = ""
    raw_score: float = None


@dataclass(frozen=True)
class Trace:
    query: str
    top_drawer_id: str = None
    routes: List[RouteAttribution] = field(default_factory=list)
    supporting: List[str] = field(default_factory=list)
    contradicting: List[str] = field(default_factory=list)
    stale: List[str] = field(default_factory=list)
    confidence: str = "unsupported"


def build_trace(query: str, fused_candidates, evidence_pack) -> Trace:
    top = fused_candidates[0] if fused_candidates else None
    top_id = None
    attrs = []
    if top is not None:
        top_id = top.get("drawer_id") if isinstance(top, dict) else getattr(top, "drawer_id", None)
        route_hits = top.get("route_hits", []) if isinstance(top, dict) else getattr(top, "route_hits", [])
        routes = top.get("routes", []) if isinstance(top, dict) else []
        if route_hits:
            attrs = [RouteAttribution(hit.route, hit.rank, hit.reason, hit.raw_score) for hit in route_hits]
        else:
            attrs = [RouteAttribution(route, idx) for idx, route in enumerate(routes, start=1)]
    confidence = "supported" if len(attrs) >= 3 else "weak" if attrs else "unsupported"
    if evidence_pack.stale and not evidence_pack.supporting:
        confidence = "unsupported"
    return Trace(query, top_id, attrs, evidence_pack.supporting, evidence_pack.contradicting, evidence_pack.stale, confidence)


def serialize_trace(trace: Trace) -> dict:
    return {
        "query": trace.query,
        "top_drawer_id": trace.top_drawer_id,
        "routes": [attr.__dict__ for attr in trace.routes],
        "supporting": trace.supporting,
        "contradicting": trace.contradicting,
        "stale": trace.stale,
        "confidence": trace.confidence,
    }
