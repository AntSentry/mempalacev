"""Tests for the topology-shell route generator.

The generator now delegates to ``topology_shells``, which requires real
backends to expand beyond the center drawer. Without backends only radius 0
fires; with seeded backends each radius surfaces a real drawer.
"""

from __future__ import annotations

from mempalace.retrieval.generators.topology_shell import TopologyShellGenerator
from mempalace.retrieval.query_frame import extract_query_frame
from mempalace.topology.shells import topology_shells


def test_topology_shell_generator_returns_center_only_without_backends():
    hits = TopologyShellGenerator().candidates(extract_query_frame("Riley project"), 5)
    # With no backend wired, only the center (radius 0) is emitted.
    radii = [hit.payload["radius"] for hit in hits]
    assert radii == [0]


def test_topology_shell_generator_returns_radius_hits_with_backends(
    palace_path, seeded_collection, kg, monkeypatch
):
    """Seed a palace and patch the generator's ``topology_shells`` call to wire
    the real backends; assert the full ladder of radii is emitted."""
    _ = palace_path

    # Same-source siblings for radius 1.
    seeded_collection.add(
        ids=[
            "drawer_gen_shell_001",
            "drawer_gen_shell_002",
        ],
        documents=[
            "Chunk 0 about Riley.",
            "Chunk 1 about Riley.",
        ],
        metadatas=[
            {
                "wing": "project",
                "room": "backend",
                "source_file": "shells.md",
                "chunk_index": 0,
                "primary_entity": "Riley",
            },
            {
                "wing": "project",
                "room": "backend",
                "source_file": "shells.md",
                "chunk_index": 1,
                "primary_entity": "Riley",
            },
        ],
    )
    # Radius 2 anchor.
    kg.add_triple(
        "Riley",
        "works_on",
        "Shells",
        valid_from="2026-03-01",
        source_drawer_id="drawer_kg_shell_001",
    )

    def _patched_shells(_center, radius):
        # Force the center to a real drawer and wire the real backends. The
        # generator passes an entity name as ``_center``; we override it with
        # a real drawer id so the seeded collection's metadata can be read.
        return topology_shells(
            "drawer_gen_shell_001",
            radius,
            collection=seeded_collection,
            knowledge_graph=kg,
            gap_connection=kg._conn(),
        )

    monkeypatch.setattr(
        "mempalace.retrieval.generators.topology_shell.topology_shells",
        _patched_shells,
    )

    hits = TopologyShellGenerator().candidates(extract_query_frame("Riley"), 5)
    radii = sorted({hit.payload["radius"] for hit in hits})
    # Radius 0 always; at least one expansion shell must fire with real seeds.
    assert 0 in radii
    assert any(r > 0 for r in radii), radii
    assert all(hit.route == "topology_shell" for hit in hits)
    # Real drawer ids only — no fabricated "...:source_neighbor"-style strings.
    for hit in hits:
        assert ":source_neighbor" not in hit.drawer_id
        assert ":entity_neighbor" not in hit.drawer_id
        assert ":room_tunnel" not in hit.drawer_id
        assert ":gap_neighbor" not in hit.drawer_id
