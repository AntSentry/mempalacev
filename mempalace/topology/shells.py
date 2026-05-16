"""Bounded topology shell expansion.

Each shell radius pulls real ``drawer_id`` values from the existing backends
described in MEMPALACE_TOPOLOGY_SPEC §6.5:

* radius 0 — the center drawer itself
* radius 1 — same source-file neighbors via ``searcher._expand_with_neighbors``
* radius 2 — same-entity drawers via ``knowledge_graph.query_entity``
* radius 3 — same-room rooms across wings via ``palace_graph.find_tunnels`` /
  ``follow_tunnels``
* radius 4 — drawers referenced by open ``gap_events`` touching the center's
  entities (read via ``graph.gap_graph.find_open_gaps``)

A hard cap of ``radius == 4`` is enforced. When no real backends are wired the
function returns only the center drawer at radius 0 — it never fabricates
synthetic ``drawer_id`` strings to fill higher shells, because that violates
the "no synthetic IDs" rule in MEMPALACE_BUILD_PLAN Phase 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass(frozen=True)
class CandidateRequest:
    drawer_id: str
    radius: int
    reason: str


def topology_shells(
    center: str,
    radius: int,
    collection: Any = None,
    knowledge_graph: Any = None,
    gap_connection: Any = None,
    palace_path: Optional[str] = None,
) -> List[CandidateRequest]:
    """Expand ``center`` into a bounded neighborhood of real drawer ids.

    Parameters
    ----------
    center:
        The drawer_id at the center of the expansion. For radius 0 this is the
        only return value; for higher radii it is looked up in ``collection``
        to find its source file, wing, room, and entity neighbors.
    radius:
        Maximum shell radius. Bounded ``[0, 4]``. Higher values raise
        ``ValueError`` per the §6.5 hard cap.
    collection:
        Drawer collection (ChromaDB or compatible) used for radius 1 and
        radius 3 lookups. ``None`` skips those shells.
    knowledge_graph:
        :class:`mempalace.knowledge_graph.KnowledgeGraph` instance used for
        radius 2 entity expansion. ``None`` skips that shell.
    gap_connection:
        SQLite connection (typically ``knowledge_graph._conn()``) used to read
        ``gap_events`` for radius 4. ``None`` skips that shell.
    palace_path:
        Palace directory used for radius 3 tunnel traversal via
        ``palace_graph``. ``None`` skips that shell.
    """

    if radius < 0 or radius > 4:
        raise ValueError("shell radius must be in [0, 4]")

    results: List[CandidateRequest] = [
        CandidateRequest(drawer_id=str(center), radius=0, reason="center drawer")
    ]
    seen = {str(center)}

    if radius == 0:
        return results

    center_meta = _load_center_meta(collection, str(center))

    if radius >= 1 and collection is not None and center_meta is not None:
        for did, reason in _radius_one_source_neighbors(collection, str(center), center_meta):
            if did in seen:
                continue
            seen.add(did)
            results.append(CandidateRequest(did, 1, reason))

    if radius >= 2 and knowledge_graph is not None and center_meta is not None:
        for did, reason in _radius_two_entity_neighbors(knowledge_graph, center_meta):
            if did in seen:
                continue
            seen.add(did)
            results.append(CandidateRequest(did, 2, reason))

    if radius >= 3 and collection is not None and center_meta is not None:
        for did, reason in _radius_three_room_tunnels(
            collection, center_meta, palace_path=palace_path
        ):
            if did in seen:
                continue
            seen.add(did)
            results.append(CandidateRequest(did, 3, reason))

    if radius >= 4 and gap_connection is not None and center_meta is not None:
        for did, reason in _radius_four_gap_neighbors(
            gap_connection, knowledge_graph, center_meta
        ):
            if did in seen:
                continue
            seen.add(did)
            results.append(CandidateRequest(did, 4, reason))

    return results


# ── Helpers ─────────────────────────────────────────────────────────────


def _load_center_meta(collection: Any, center_id: str) -> Optional[dict]:
    """Fetch the center drawer's metadata + document text from the collection."""
    if collection is None:
        return None
    try:
        record = collection.get(
            ids=[center_id], include=["metadatas", "documents"]
        )
    except Exception:
        return None
    metas = _coerce_field(record, "metadatas")
    docs = _coerce_field(record, "documents")
    if not metas:
        return None
    meta = dict(metas[0] or {})
    if docs:
        meta["__document__"] = docs[0] or ""
    return meta


def _coerce_field(record: Any, name: str) -> list:
    """Read a list field from a ChromaDB ``get`` result (object or dict)."""
    if record is None:
        return []
    if isinstance(record, dict):
        value = record.get(name)
    else:
        value = getattr(record, name, None)
    if value is None:
        return []
    return list(value)


def _radius_one_source_neighbors(
    collection: Any, center_id: str, center_meta: dict
) -> List[tuple]:
    """Radius 1 — same source-file siblings.

    Mirrors the source-window logic in :func:`mempalace.searcher._expand_with_neighbors`:
    a ``±1`` chunk window around the center's ``chunk_index`` in the same
    ``source_file``. The MemPalace backend wrapper exposes typed results; the
    raw chromadb client returns dicts. ``_coerce_field`` smooths over both.
    """
    src = center_meta.get("source_file")
    chunk_idx = center_meta.get("chunk_index")
    if not src or not isinstance(chunk_idx, int):
        return []

    target_indexes = [chunk_idx - 1, chunk_idx, chunk_idx + 1]
    try:
        neighbors = collection.get(
            where={
                "$and": [
                    {"source_file": src},
                    {"chunk_index": {"$in": target_indexes}},
                ]
            },
            include=["metadatas"],
        )
    except Exception:
        return []

    ids = _coerce_field(neighbors, "ids")
    metas = _coerce_field(neighbors, "metadatas")
    pairs: List[tuple] = []
    for did, meta in zip(ids, metas):
        if did == center_id:
            continue
        ci = (meta or {}).get("chunk_index")
        pairs.append((str(did), f"same source neighbor (chunk_index={ci})"))
    return pairs


def _radius_two_entity_neighbors(
    knowledge_graph: Any, center_meta: dict
) -> List[tuple]:
    """Radius 2 — drawers sharing a KG entity with the center.

    Pulls outgoing/incoming triples for every entity name we can read off the
    drawer metadata (``entities`` list, ``primary_entity`` field, or a comma
    string in ``entity``). Each triple's ``source_drawer_id`` (or, when
    populated by older mines, ``source_closet``) becomes a candidate at
    radius 2.

    :meth:`KnowledgeGraph.query_entity` surfaces ``source_closet`` but not
    ``source_drawer_id``, so we read the underlying triples table directly
    via the same SQLite connection.
    """
    entities = _entity_names_from_meta(center_meta)
    if not entities:
        return []

    as_of = center_meta.get("filed_at") or center_meta.get("date") or None
    conn = _kg_connection(knowledge_graph)
    if conn is None:
        return []
    entity_id_fn = getattr(knowledge_graph, "_entity_id", None)
    if entity_id_fn is None:
        return []

    pairs: List[tuple] = []
    seen: set = set()
    for name in entities:
        # Surface KG-level triples first via ``query_entity`` so any caller
        # that has wired ``source_closet`` for older mines still gets credit.
        try:
            rows = knowledge_graph.query_entity(name, as_of=as_of, direction="both")
        except Exception:
            rows = []
        for row in rows:
            did = row.get("source_closet") or row.get("source_drawer_id")
            if did and did not in seen:
                seen.add(did)
                pairs.append((str(did), f"same entity '{name}'"))

        # Then read ``source_drawer_id`` directly — ``query_entity`` does not
        # surface that column today, but it is the RFC 002 §5.5 provenance
        # field every modern mine populates.
        try:
            eid = entity_id_fn(name)
        except Exception:
            continue
        try:
            triple_rows = conn.execute(
                """
                SELECT source_drawer_id FROM triples
                WHERE (subject = ? OR object = ?)
                  AND source_drawer_id IS NOT NULL
                """,
                (eid, eid),
            ).fetchall()
        except Exception:
            continue
        for trow in triple_rows:
            did = trow["source_drawer_id"] if "source_drawer_id" in trow.keys() else None
            if not did or did in seen:
                continue
            seen.add(did)
            pairs.append((str(did), f"same entity '{name}'"))
    return pairs


def _kg_connection(knowledge_graph: Any) -> Any:
    """Return a sqlite connection from a KnowledgeGraph handle."""
    if knowledge_graph is None:
        return None
    conn_attr = getattr(knowledge_graph, "_conn", None)
    if callable(conn_attr):
        try:
            return conn_attr()
        except Exception:
            return None
    return getattr(knowledge_graph, "conn", None)


def _radius_three_room_tunnels(
    collection: Any, center_meta: dict, palace_path: Optional[str] = None
) -> List[tuple]:
    """Radius 3 — drawers in the same room across wings via tunnels.

    ``palace_path`` is accepted for future call sites that need to route the
    tunnel lookup through a specific palace; the current
    :func:`mempalace.palace_graph.follow_tunnels` reads its own location.
    """
    _ = palace_path  # reserved for future palace-scoped tunnel lookups
    from mempalace import palace_graph as pg

    wing = center_meta.get("wing")
    room = center_meta.get("room")
    if not wing or not room:
        return []

    tunnels = pg.follow_tunnels(wing, room, col=collection)
    pairs: List[tuple] = []
    for tunnel in tunnels:
        did = tunnel.get("drawer_id")
        if did:
            pairs.append(
                (str(did), f"room '{room}' across wing '{tunnel.get('connected_wing')}'")
            )
            continue
        # Tunnel without an explicit drawer pin — surface any drawer the
        # target wing/room actually holds. This keeps radius 3 anchored on
        # real drawer ids instead of synthetic ``connected_wing/room``
        # placeholders.
        target_wing = tunnel.get("connected_wing")
        target_room = tunnel.get("connected_room")
        if not target_wing or not target_room:
            continue
        try:
            hits = collection.get(
                where={
                    "$and": [
                        {"wing": target_wing},
                        {"room": target_room},
                    ]
                },
                include=["metadatas"],
                limit=5,
            )
        except TypeError:
            # Older Chroma versions don't accept ``limit`` on .get(); retry without.
            try:
                hits = collection.get(
                    where={
                        "$and": [
                            {"wing": target_wing},
                            {"room": target_room},
                        ]
                    },
                    include=["metadatas"],
                )
            except Exception:
                continue
        except Exception:
            continue
        for did2 in _coerce_field(hits, "ids"):
            pairs.append(
                (str(did2), f"room '{target_room}' across wing '{target_wing}'")
            )
    return pairs


def _radius_four_gap_neighbors(
    gap_connection: Any, knowledge_graph: Any, center_meta: dict
) -> List[tuple]:
    """Radius 4 — drawers referenced by open ``gap_events`` touching center entities.

    ``knowledge_graph`` is accepted for parity with the other shell helpers
    and for future enrichment (e.g., predicate-filtered subject lookups). The
    current implementation only needs the raw subject ids derivable from
    ``center_meta``.
    """
    _ = knowledge_graph  # reserved for future predicate-filtered subject lookups
    from mempalace.graph.gap_graph import find_open_gaps

    entities = _entity_names_from_meta(center_meta)
    if not entities:
        return []

    # KG ``_entity_id`` lower-cases names and replaces spaces; reuse the same
    # transform so subject lookups in ``gap_events`` match what the KG wrote.
    def _eid(name: str) -> str:
        return name.lower().replace(" ", "_").replace("'", "")

    pairs: List[tuple] = []
    seen: set = set()
    for name in entities:
        try:
            gaps = find_open_gaps(gap_connection, subject_id=_eid(name))
        except Exception:
            continue
        for gap in gaps:
            for key in ("old_drawer_id", "new_drawer_id", "evidence_drawer_id"):
                did = gap.get(key)
                if not did or did in seen:
                    continue
                seen.add(did)
                pairs.append((str(did), f"open gap_event ({gap.get('gap_type')})"))
    return pairs


def _entity_names_from_meta(center_meta: dict) -> List[str]:
    """Read entity names from heterogeneous drawer metadata shapes."""
    candidates: List[str] = []
    raw = center_meta.get("entities")
    if isinstance(raw, (list, tuple)):
        candidates.extend(str(e) for e in raw if isinstance(e, str) and e.strip())
    elif isinstance(raw, str):
        candidates.extend(part.strip() for part in raw.split(";") if part.strip())
    primary = center_meta.get("primary_entity") or center_meta.get("entity")
    if isinstance(primary, str) and primary.strip():
        candidates.append(primary.strip())
    elif isinstance(primary, (list, tuple)):
        candidates.extend(str(p) for p in primary if isinstance(p, str) and p.strip())

    seen: set = set()
    out: List[str] = []
    for name in candidates:
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out
