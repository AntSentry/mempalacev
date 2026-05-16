"""Tests for ``mempalace.topology.axis_routes``.

``build_axis_queries`` still exposes the deterministic six-orientation
constructor; ``execute_axis_query`` now runs the orientation against real
backends (knowledge graph + ChromaDB collection) and returns ``RouteHit``
records keyed on real ``drawer_id`` values.
"""

from __future__ import annotations

from mempalace.retrieval.query_frame import extract_query_frame
from mempalace.topology.axis_routes import (
    ORIENTATIONS,
    build_axis_queries,
    execute_axis_query,
)


def test_build_axis_queries_returns_six_distinct_objects():
    queries = build_axis_queries(extract_query_frame("Riley project now"))
    assert len(queries) == 6
    assert [query.orientation for query in queries] == list(ORIENTATIONS)


def test_execute_axis_query_returns_empty_without_backends():
    """No backends wired ⇒ no synthetic ids per the §6.4 F4 rule."""
    queries = build_axis_queries(extract_query_frame("Riley project now"))
    hits = execute_axis_query(queries[0], k=5)
    assert hits == []


def test_execute_axis_query_against_real_palace(
    palace_path, seeded_collection, kg
):
    """Seed a palace with a Riley-anchored drawer + KG triple, then drive
    ``execute_axis_query`` for each orientation and assert returned drawer ids
    actually exist in the palace.

    ``palace_path`` is part of the fixture chain that seats ``seeded_collection``
    inside an isolated palace directory; it is intentionally unused directly.
    """
    _ = palace_path

    seeded_collection.add(
        ids=["drawer_axis_001", "drawer_axis_002"],
        documents=[
            "Riley shipped the topology layer in May.",
            "Riley discussed axis orientations.",
        ],
        metadatas=[
            {
                "wing": "project",
                "room": "backend",
                "source_file": "riley_topology.md",
                "chunk_index": 0,
                "primary_entity": "Riley",
                "filed_at": "2026-05-01T00:00:00",
            },
            {
                "wing": "project",
                "room": "backend",
                "source_file": "riley_axes.md",
                "chunk_index": 0,
                "primary_entity": "Riley",
                "filed_at": "2026-05-02T00:00:00",
            },
        ],
    )

    kg.add_triple(
        "Riley",
        "works_on",
        "TopologyLayer",
        valid_from="2026-04-01",
        source_drawer_id="drawer_axis_001",
    )

    # ``ids`` for everything in the seeded palace — the assertion needs to
    # confirm returned drawer_ids really live in the collection.
    everything = seeded_collection.get(include=[])
    palace_ids = set(everything["ids"] if isinstance(everything, dict) else everything.ids)
    assert "drawer_axis_001" in palace_ids

    frame = extract_query_frame("Riley topology")
    queries = build_axis_queries(frame)

    backend = {"collection": seeded_collection, "knowledge_graph": kg}

    surfaced = set()
    for q in queries:
        hits = execute_axis_query(q, backend=backend, k=5)
        for hit in hits:
            assert hit.drawer_id, "drawer_id must be non-empty"
            assert "axis:" not in hit.drawer_id, "no fabricated axis:{orient}:{idx}"
            assert hit.drawer_id in palace_ids, (
                f"hit {hit.drawer_id!r} is not a real palace drawer"
            )
            surfaced.add(hit.drawer_id)

    # The KG-anchored drawer must be reachable through at least one orientation.
    assert "drawer_axis_001" in surfaced
