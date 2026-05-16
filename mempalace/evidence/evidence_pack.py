"""Evidence pack assembly for traced retrieval.

The ``EvidencePack`` returned at the retrieval boundary partitions candidate
drawers into three disjoint sets — ``supporting``, ``contradicting``, and
``stale`` — per MEMPALACE_TOPOLOGY_SPEC §F4.2 and the implementation rules in
MEMPALACE_BUILD_PLAN Phase 5.

``stale`` is populated from ``gap_events`` whose ``status`` is ``superseded``
or ``rejected`` and whose ``subject`` matches an entity in the active query.
``contradicting`` is populated from :func:`mempalace.graph.contradiction.find_contradictions`
— drawer ids whose source triples have a current-time opposite-polarity (or
different-object) sibling. ``supporting`` is the residual: every candidate
that is neither stale nor contradicting.

Partitions are disjoint by construction: stale wins over contradicting wins
over supporting, so a drawer can appear in at most one set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Set


@dataclass(frozen=True)
class EvidencePack:
    query: str
    supporting: List[str] = field(default_factory=list)
    contradicting: List[str] = field(default_factory=list)
    stale: List[str] = field(default_factory=list)
    route_count_for_top: int = 0


def build_evidence_pack(
    query: str,
    fused_candidates: Iterable,
    knowledge_graph: Any = None,
    gap_graph: Any = None,
    query_entities: Optional[Iterable[str]] = None,
    cache: Any = None,
    palace_write_seq: Optional[int] = None,
) -> EvidencePack:
    """Assemble an :class:`EvidencePack` from fused retrieval candidates.

    Parameters
    ----------
    query:
        Original query text. Included for trace serialization; entities are
        re-extracted from it when ``query_entities`` is omitted.
    fused_candidates:
        Iterable of fused candidates. Each item may be a string drawer_id, a
        :class:`mempalace.retrieval.fusion.RankedCandidate`, or a dict shaped
        like the legacy search response.
    knowledge_graph:
        Optional ``KnowledgeGraph`` whose connection is used by
        :func:`mempalace.graph.contradiction.find_contradictions`. When None,
        ``contradicting`` is left empty.
    gap_graph:
        Optional source of gap events. May be a :class:`sqlite3.Connection`
        or any object exposing ``list_gap_events(status, ...)``. When None,
        ``stale`` is left empty.
    query_entities:
        Optional iterable of entity names that should drive the gap-event
        subject filter. Defaults to entities extracted from ``query``.
    """

    # Cache short-circuit (RFC T3a). Only consult the cache when both a
    # cache and a palace_write_seq are supplied — otherwise we cannot key
    # the entry safely. Drawer text is never cached; the EvidencePack only
    # stores drawer ids and partition labels.
    if cache is not None and palace_write_seq is not None:
        cached = cache.get(query, palace_write_seq)
        if cached is not None:
            return cached

    candidates = list(fused_candidates or [])
    candidate_ids = [_candidate_id(item) for item in candidates]
    candidate_ids = [item for item in candidate_ids if item]

    entities = _resolve_query_entities(query, query_entities)
    entity_ids = {_entity_id(name) for name in entities if name}

    stale: Set[str] = _compute_stale(gap_graph, entity_ids)
    contradicting: Set[str] = _compute_contradicting(knowledge_graph, entity_ids)

    # Disjointness rule: stale wins over contradicting (a superseded fact has
    # already been retired; flagging it as a live contradiction is double-
    # counting). Build the contradicting set with stale ids removed so the
    # final partitions are pairwise disjoint by construction.
    contradicting -= stale

    # Restrict each non-supporting partition to ids actually in the candidate
    # pool. Candidates referenced by gap_events or contradictions that did
    # not surface via retrieval are not in scope for this answer.
    candidate_set = set(candidate_ids)
    stale_in_pool = stale & candidate_set
    contradicting_in_pool = contradicting & candidate_set

    supporting = [
        item
        for item in candidate_ids
        if item not in stale_in_pool and item not in contradicting_in_pool
    ]

    top_routes = _count_top_routes(candidates)

    pack = EvidencePack(
        query=query,
        supporting=supporting,
        contradicting=sorted(contradicting_in_pool),
        stale=sorted(stale_in_pool),
        route_count_for_top=top_routes,
    )

    if cache is not None and palace_write_seq is not None:
        cache.set(query, palace_write_seq, pack)

    return pack


def is_answerable(pack: EvidencePack) -> bool:
    """Return True when the pack meets the F4.1 answerable rule.

    Per MEMPALACE_BUILD_PLAN Phase 5: supporting non-empty AND not stale-only
    AND route_count_for_top ``>= 2``.
    """
    return (
        bool(pack.supporting)
        and not (pack.stale and not pack.supporting)
        and pack.route_count_for_top >= 2
    )


# ── Candidate plumbing ──────────────────────────────────────────────────


def _candidate_id(item: Any) -> Optional[str]:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("drawer_id") or item.get("id") or item.get("source_file")
    return getattr(item, "drawer_id", None)


def _count_top_routes(candidates: list) -> int:
    if not candidates:
        return 0
    first = candidates[0]
    if isinstance(first, dict):
        return len(first.get("routes") or first.get("route_hits") or [])
    return len(getattr(first, "route_hits", []) or [])


def _resolve_query_entities(
    query: str, query_entities: Optional[Iterable[str]]
) -> List[str]:
    if query_entities is not None:
        return [name for name in query_entities if isinstance(name, str) and name.strip()]
    try:
        from mempalace.retrieval.query_frame import extract_query_frame

        frame = extract_query_frame(query or "")
        return list(frame.entities_extracted)
    except Exception:
        return []


def _entity_id(name: str) -> str:
    """Match :meth:`KnowledgeGraph._entity_id` so subject lookups align."""
    return name.lower().replace(" ", "_").replace("'", "")


# ── Stale / contradicting computation ───────────────────────────────────


_STALE_STATUSES = ("superseded", "rejected")


def _compute_stale(gap_graph: Any, entity_ids: Set[str]) -> Set[str]:
    """Drawer ids referenced by gap_events with stale status touching the query."""
    if gap_graph is None or not entity_ids:
        return set()
    conn = _gap_connection(gap_graph)
    stale: Set[str] = set()
    for status in _STALE_STATUSES:
        rows = _list_gap_events(gap_graph, conn, status)
        for row in rows:
            subject = (row.get("subject") or "").lower()
            if subject not in entity_ids:
                continue
            for key in ("old_drawer_id", "new_drawer_id", "evidence_drawer_id"):
                did = row.get(key)
                if did:
                    stale.add(str(did))
    return stale


def _compute_contradicting(knowledge_graph: Any, entity_ids: Set[str]) -> Set[str]:
    """Drawer ids whose triples currently contradict another currently-valid triple."""
    if knowledge_graph is None or not entity_ids:
        return set()
    conn = _kg_connection(knowledge_graph)
    if conn is None:
        return set()
    from mempalace.graph.contradiction import find_contradictions

    try:
        contradictions = find_contradictions(conn, polarity_required=False)
    except Exception:
        return set()
    if not contradictions:
        return set()

    triple_ids = set()
    for c in contradictions:
        if c.subject in entity_ids:
            triple_ids.add(c.first_triple_id)
            triple_ids.add(c.second_triple_id)
    if not triple_ids:
        return set()

    placeholders = ",".join(["?"] * len(triple_ids))
    rows = conn.execute(
        f"SELECT id, source_drawer_id, source_closet, source_file "
        f"FROM triples WHERE id IN ({placeholders})",
        list(triple_ids),
    ).fetchall()
    out: Set[str] = set()
    for row in rows:
        did = (
            row["source_drawer_id"]
            if "source_drawer_id" in row.keys()
            else None
        )
        if not did and "source_closet" in row.keys():
            did = row["source_closet"]
        if not did and "source_file" in row.keys():
            did = row["source_file"]
        if did:
            out.add(str(did))
    return out


def _gap_connection(gap_graph: Any) -> Any:
    """Return a sqlite connection from a gap_graph handle, if available."""
    if gap_graph is None:
        return None
    # Plain sqlite3.Connection passed directly.
    if hasattr(gap_graph, "execute") and hasattr(gap_graph, "cursor"):
        return gap_graph
    # KnowledgeGraph-style wrapper exposing ``_conn()`` or ``conn``.
    for attr in ("_conn", "conn", "connection"):
        candidate = getattr(gap_graph, attr, None)
        if callable(candidate):
            try:
                return candidate()
            except Exception:
                continue
        if candidate is not None:
            return candidate
    return None


def _kg_connection(knowledge_graph: Any) -> Any:
    """Return a sqlite connection from a KnowledgeGraph handle."""
    if knowledge_graph is None:
        return None
    conn = getattr(knowledge_graph, "_conn", None)
    if callable(conn):
        try:
            return conn()
        except Exception:
            return None
    return getattr(knowledge_graph, "conn", None)


def _list_gap_events(gap_graph: Any, conn: Any, status: str) -> List[dict]:
    """Read gap_events at ``status`` from whichever handle was provided."""
    # First try a domain-level helper exposed by the gap_graph object itself.
    helper = getattr(gap_graph, "list_gap_events", None)
    if callable(helper):
        try:
            return list(helper(status=status))
        except Exception:
            pass
    if conn is None:
        return []
    try:
        from mempalace.graph.gap_graph import list_gap_events

        return list_gap_events(conn, status=status, limit=500)
    except Exception:
        return []
