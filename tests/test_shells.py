"""Tests for ``mempalace.topology.shells.topology_shells``.

The ``topology_shells`` API exposes a real-backend expansion described in
MEMPALACE_TOPOLOGY_SPEC §6.5. These tests cover three layers:

1. Argument validation (``test_shell_hard_cap``) — the radius is bounded
   ``[0, 4]``.
2. Center-only fallback (``test_shell_radius_semantics_without_backends``) —
   when no backends are wired the function returns only the center drawer
   rather than fabricating synthetic ids.
3. Real-backend behavior (``test_shell_radius_semantics_with_real_backends``)
   — a seeded palace with multiple source chunks, a triple, a tunnel, and an
   open gap_event produces real ``drawer_id`` values at every radius.
"""

from __future__ import annotations

import pytest

from mempalace.graph.gap_graph import GapEvent, ensure_gap_schema, record_gap_event
from mempalace.palace_graph import create_tunnel
from mempalace.topology.shells import topology_shells


def test_shell_radius_semantics_without_backends():
    """Without backends, radius 0 returns center; higher radii do NOT add ids."""
    assert len(topology_shells("d1", 0)) == 1
    # No synthetic neighbors when no backend is wired — this is the F4 rule.
    out = topology_shells("d1", 4)
    assert len(out) == 1
    assert out[0].drawer_id == "d1"
    assert out[0].radius == 0


def test_shell_hard_cap():
    with pytest.raises(ValueError):
        topology_shells("d1", 5)


def test_shell_radius_semantics_with_real_backends(
    palace_path, seeded_collection, kg, tmp_dir, monkeypatch
):
    """Seed real chunks + triple + tunnel + gap event; assert real drawer_ids."""

    # ── Radius 1: seed three same-source chunks. ────────────────────────
    seeded_collection.add(
        ids=[
            "drawer_center_001",
            "drawer_center_002",
            "drawer_center_003",
        ],
        documents=[
            "Chunk 0 about Riley's project.",
            "Chunk 1 about Riley's project.",
            "Chunk 2 about Riley's project.",
        ],
        metadatas=[
            {
                "wing": "project",
                "room": "backend",
                "source_file": "riley.md",
                "chunk_index": 0,
                "primary_entity": "Riley",
                "filed_at": "2026-01-01T00:00:00",
            },
            {
                "wing": "project",
                "room": "backend",
                "source_file": "riley.md",
                "chunk_index": 1,
                "primary_entity": "Riley",
                "filed_at": "2026-01-01T00:00:01",
            },
            {
                "wing": "project",
                "room": "backend",
                "source_file": "riley.md",
                "chunk_index": 2,
                "primary_entity": "Riley",
                "filed_at": "2026-01-01T00:00:02",
            },
        ],
    )

    # ── Radius 2: triple linking Riley → topic, with a source_drawer_id. ─
    kg.add_triple(
        "Riley",
        "works_on",
        "TopologyLayer",
        valid_from="2025-12-01",
        source_drawer_id="drawer_kg_001",
    )

    # ── Radius 3: cross-wing tunnel pinned to a real drawer. ────────────
    # Use a HOME override so explicit-tunnel storage lands inside tmp_dir.
    monkeypatch.setenv("HOME", tmp_dir)
    seeded_collection.add(
        ids=["drawer_tunnel_001"],
        documents=["Tunnel target drawer."],
        metadatas=[
            {
                "wing": "research",
                "room": "backend",
                "source_file": "research.md",
                "chunk_index": 0,
            }
        ],
    )
    create_tunnel(
        source_wing="project",
        source_room="backend",
        target_wing="research",
        target_room="backend",
        label="topology relation",
        target_drawer_id="drawer_tunnel_001",
    )

    # ── Radius 4: open gap event whose subject matches the center entity. ─
    conn = kg._conn()
    ensure_gap_schema(conn)
    record_gap_event(
        conn,
        GapEvent(
            id="gap_test_001",
            gap_type="opposing_predicate_conflict",
            status="open",
            subject=kg._entity_id("Riley"),
            predicate="prefers",
            object="vector_routes",
        ),
    )
    # ``record_gap_event`` inserts a row with NULL drawer ids; back-fill the
    # ones the seeded palace actually contains so radius-4 has something to
    # emit.
    conn.execute(
        "UPDATE gap_events SET old_drawer_id=?, new_drawer_id=? WHERE id=?",
        ("drawer_gap_old", "drawer_gap_new", "gap_test_001"),
    )

    # ── Drive the expansion. ────────────────────────────────────────────
    results = topology_shells(
        "drawer_center_001",
        radius=4,
        collection=seeded_collection,
        knowledge_graph=kg,
        gap_connection=conn,
        palace_path=palace_path,
    )

    by_radius: dict = {}
    for item in results:
        by_radius.setdefault(item.radius, []).append(item.drawer_id)

    # Radius 0 — exactly the center.
    assert by_radius[0] == ["drawer_center_001"]

    # Radius 1 — at least one same-source neighbor (chunk_index 1 or 2).
    assert by_radius.get(1), "radius 1 must surface same-source neighbors"
    assert any(d in by_radius[1] for d in ("drawer_center_002", "drawer_center_003"))

    # Radius 2 — the KG-anchored drawer.
    assert "drawer_kg_001" in by_radius.get(2, []), by_radius

    # Radius 3 — the tunnel target.
    assert "drawer_tunnel_001" in by_radius.get(3, []), by_radius

    # Radius 4 — gap drawers (old or new).
    radius_four = set(by_radius.get(4, []))
    assert radius_four & {"drawer_gap_old", "drawer_gap_new"}, by_radius

    # No fabricated ``center:source_neighbor``-style strings.
    for item in results:
        assert ":source_neighbor" not in item.drawer_id
        assert ":entity_neighbor" not in item.drawer_id
        assert ":room_tunnel" not in item.drawer_id
        assert ":gap_neighbor" not in item.drawer_id


def test_shells_returns_only_center_when_collection_missing(kg):
    """Without a collection, even a real KG can't yield neighbors at r>=1."""
    # Sanity: KG alone (no collection) returns only the center drawer.
    out = topology_shells("d1", 4, knowledge_graph=kg)
    assert [item.drawer_id for item in out] == ["d1"]
