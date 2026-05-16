"""Tests for the topology-axis route generator.

The generator delegates to ``execute_axis_query``, which now requires real
backends (KG + collection). Without backends the generator yields no hits;
with seeded backends every hit references a real ``drawer_id``.
"""

from __future__ import annotations

from mempalace.retrieval.generators.topology_axis import TopologyAxisGenerator
from mempalace.retrieval.query_frame import extract_query_frame
from mempalace.topology.axis_routes import execute_axis_query


def test_topology_axis_generator_returns_no_hits_without_backends():
    hits = TopologyAxisGenerator().candidates(extract_query_frame("Riley project"), 6)
    assert hits == []
    # All returned hits are tagged with the canonical route name when they exist.
    assert all(hit.route == "topology_axis" for hit in hits)


def test_topology_axis_generator_returns_real_hits_with_backends(
    palace_path, seeded_collection, kg, monkeypatch
):
    """Wire real backends via a patched ``execute_axis_query`` so the generator
    surfaces real ``drawer_id`` values."""
    _ = palace_path

    seeded_collection.add(
        ids=["drawer_gen_axis_001"],
        documents=["Riley shipped axis orientations."],
        metadatas=[
            {
                "wing": "project",
                "room": "backend",
                "source_file": "axis.md",
                "chunk_index": 0,
                "primary_entity": "Riley",
                "filed_at": "2026-05-01T00:00:00",
            }
        ],
    )
    kg.add_triple(
        "Riley",
        "works_on",
        "AxisOrientations",
        valid_from="2026-04-01",
        source_drawer_id="drawer_gen_axis_001",
    )

    backend = {"collection": seeded_collection, "knowledge_graph": kg}

    def _patched(query, backend=None, k=5, knowledge_graph=None, collection=None):
        # The generator passes no backend; inject ours.
        return execute_axis_query(query, backend=backend or globals_backend, k=k)

    globals_backend = backend
    monkeypatch.setattr(
        "mempalace.retrieval.generators.topology_axis.execute_axis_query",
        _patched,
    )

    hits = TopologyAxisGenerator().candidates(extract_query_frame("Riley"), 6)
    assert hits, "expected at least one real-backend hit"
    assert all(hit.route == "topology_axis" for hit in hits)
    assert any(hit.drawer_id == "drawer_gen_axis_001" for hit in hits)
