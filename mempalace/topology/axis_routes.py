"""Six deterministic topology axis-route orientations.

Each orientation reorders the (entity, topic, time) traversal as described in
MEMPALACE_TOPOLOGY_SPEC §6.4. ``execute_axis_query`` runs the orientation
against the existing knowledge-graph and vector backends and returns a list of
``RouteHit`` records keyed on real ``drawer_id`` values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from mempalace.retrieval.fusion import RouteHit


ORIENTATIONS: Tuple[Tuple[str, str, str], ...] = (
    ("entity", "topic", "time"),
    ("entity", "time", "topic"),
    ("topic", "entity", "time"),
    ("topic", "time", "entity"),
    ("time", "entity", "topic"),
    ("time", "topic", "entity"),
)


@dataclass(frozen=True)
class AxisQuery:
    orientation: Tuple[str, str, str]
    primary_filter: str
    secondary_filter: str
    tertiary_filter: str
    weight_overrides: Dict[str, float] = field(default_factory=dict)
    frame: Any = None


def build_axis_queries(frame) -> List[AxisQuery]:
    return [_build_axis_query(frame, orientation) for orientation in ORIENTATIONS]


def _build_axis_query(frame, orientation: Tuple[str, str, str]) -> AxisQuery:
    weights = {
        "entity": {"entity_anchored_embedding": 2.0},
        "topic": {"topic_embedding": 1.5},
        "time": {"recency": 1.25},
    }.get(orientation[0], {})
    return AxisQuery(
        orientation=orientation,
        primary_filter=_filter_value(frame, orientation[0]),
        secondary_filter=_filter_value(frame, orientation[1]),
        tertiary_filter=_filter_value(frame, orientation[2]),
        weight_overrides=weights,
        frame=frame,
    )


def _filter_value(frame, axis: str) -> str:
    if axis == "entity":
        return ",".join(frame.entities_extracted) or "*"
    if axis == "topic":
        return ",".join(frame.topics) or "*"
    if axis == "time":
        return frame.as_of or "current"
    return "*"


def execute_axis_query(
    query: AxisQuery,
    backend: Any = None,
    k: int = 5,
    knowledge_graph: Any = None,
    collection: Any = None,
) -> List[RouteHit]:
    """Run an :class:`AxisQuery` against the real backends.

    The orientation's primary axis decides which backend leads:

    * ``entity`` primary — KG ``query_entity`` first, then optional vector
      retrieval scoped to the same entity name. KG-derived drawer ids rank
      ahead of vector ids.
    * ``topic`` primary — Vector retrieval over the topic tokens leads, KG
      entity matches add a tie-breaker contribution.
    * ``time`` primary — KG ``query_entity`` with ``as_of`` first, then vector
      retrieval.

    Inputs:

    ``backend`` may be a mapping ``{"collection": col, "knowledge_graph": kg}``
    or omitted when ``collection`` / ``knowledge_graph`` are passed
    explicitly. When neither is available the function returns an empty list
    rather than fabricating synthetic ``drawer_id`` strings — that "no
    synthetic IDs" rule is mandated by Phase 4 of MEMPALACE_BUILD_PLAN.
    """

    collection, knowledge_graph = _resolve_backends(
        backend, collection=collection, knowledge_graph=knowledge_graph
    )
    if collection is None and knowledge_graph is None:
        return []

    base = "|".join(query.orientation)
    primary_axis = query.orientation[0]
    frame = getattr(query, "frame", None)

    hits: List[RouteHit] = []
    seen: set = set()

    def _emit(drawer_id: str, source: str, reason_suffix: str) -> None:
        if not drawer_id or drawer_id in seen:
            return
        seen.add(drawer_id)
        rank = len(hits) + 1
        hits.append(
            RouteHit(
                route="topology_axis",
                drawer_id=str(drawer_id),
                rank=rank,
                reason=f"axis {base} ({source}: {reason_suffix})",
                payload={
                    "orientation": query.orientation,
                    "weight_overrides": query.weight_overrides,
                    "source": source,
                },
            )
        )

    kg_results = list(_kg_drawer_ids(knowledge_graph, frame, primary_axis))
    vec_results = list(_vector_drawer_ids(collection, frame, primary_axis, k * 2))

    if primary_axis == "entity":
        ordered: Iterable[tuple] = list(kg_results) + list(vec_results)
    elif primary_axis == "topic":
        ordered = list(vec_results) + list(kg_results)
    else:  # time
        ordered = list(kg_results) + list(vec_results)

    for drawer_id, source, reason in ordered:
        if len(hits) >= k:
            break
        _emit(drawer_id, source, reason)

    return hits


# ── Backend resolution ──────────────────────────────────────────────────


def _resolve_backends(
    backend: Any, collection: Any = None, knowledge_graph: Any = None
) -> Tuple[Any, Any]:
    """Resolve ``backend`` into a ``(collection, knowledge_graph)`` pair."""
    if backend is None:
        return collection, knowledge_graph
    if isinstance(backend, dict):
        return (
            collection or backend.get("collection"),
            knowledge_graph or backend.get("knowledge_graph") or backend.get("kg"),
        )
    return (
        collection or getattr(backend, "collection", None),
        knowledge_graph
        or getattr(backend, "knowledge_graph", None)
        or getattr(backend, "kg", None),
    )


# ── KG path ─────────────────────────────────────────────────────────────


def _kg_drawer_ids(knowledge_graph: Any, frame: Any, primary_axis: str) -> List[tuple]:
    """Yield ``(drawer_id, "kg", reason)`` tuples from the knowledge graph."""
    if knowledge_graph is None or frame is None:
        return []
    entities = list(getattr(frame, "entities_extracted", []) or [])
    if not entities:
        return []
    as_of: Optional[str] = None
    if primary_axis == "time":
        as_of = getattr(frame, "as_of", None)
    pairs: List[tuple] = []
    seen: set = set()
    for name in entities:
        try:
            rows = knowledge_graph.query_entity(name, as_of=as_of, direction="both")
        except Exception:
            continue
        for row in rows:
            did = row.get("source_closet") or row.get("source_drawer_id")
            if not did or did in seen:
                continue
            seen.add(did)
            pairs.append((str(did), "kg", f"entity '{name}'"))
    return pairs


# ── Vector path ─────────────────────────────────────────────────────────


def _vector_drawer_ids(
    collection: Any, frame: Any, primary_axis: str, n_results: int
) -> List[tuple]:
    """Yield ``(drawer_id, "vector", reason)`` tuples from the vector index.

    Uses the same chromadb collection API the rest of the codebase uses
    (``.query(query_texts=...)``). Builds a query string biased toward the
    primary axis so the six orientations produce operationally different
    candidate pools (per §6.4 Jaccard < 0.7 expectation).
    """
    if collection is None or frame is None or n_results <= 0:
        return []
    query_text = _build_vector_query(frame, primary_axis)
    if not query_text:
        return []
    where = _build_where(frame)
    try:
        kwargs = {
            "query_texts": [query_text],
            "n_results": max(1, n_results),
            "include": ["metadatas"],
        }
        if where:
            kwargs["where"] = where
        result = collection.query(**kwargs)
    except Exception:
        return []

    raw_ids = _first_field(result, "ids")
    metas = _first_field(result, "metadatas")
    pairs: List[tuple] = []
    for did, meta in zip(raw_ids, metas):
        if did is None:
            continue
        reason = f"vector match ({primary_axis} primary)"
        if meta and isinstance(meta, dict):
            wing = meta.get("wing")
            if wing:
                reason = f"vector match in wing '{wing}' ({primary_axis} primary)"
        pairs.append((str(did), "vector", reason))
    return pairs


def _build_vector_query(frame: Any, primary_axis: str) -> str:
    text = getattr(frame, "text", "") or ""
    entities = list(getattr(frame, "entities_extracted", []) or [])
    topics = list(getattr(frame, "topics", []) or [])
    as_of = getattr(frame, "as_of", None)

    parts: List[str] = []
    if primary_axis == "entity":
        parts.extend(entities)
        parts.extend(topics)
    elif primary_axis == "topic":
        parts.extend(topics)
        parts.extend(entities)
    else:  # time
        if as_of:
            parts.append(as_of)
        parts.extend(entities)
        parts.extend(topics)
    parts.append(text)
    return " ".join(part for part in parts if part).strip()


def _build_where(frame: Any) -> Optional[dict]:
    wing = getattr(frame, "wing", None)
    room = getattr(frame, "room", None)
    if wing and room:
        return {"$and": [{"wing": wing}, {"room": room}]}
    if wing:
        return {"wing": wing}
    if room:
        return {"room": room}
    return None


def _first_field(result: Any, name: str) -> list:
    """Return the first row of a Chroma query result, dict or typed."""
    if result is None:
        return []
    if isinstance(result, dict):
        outer = result.get(name)
    else:
        outer = getattr(result, name, None)
    if not outer:
        return []
    first = outer[0]
    return list(first or [])
