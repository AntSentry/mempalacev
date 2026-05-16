"""Tests for ``mempalace.evidence.evidence_pack``.

Covers three layers:

1. The legacy in-memory partitioning path (synthetic candidates, no KG/gap
   graph). Confirms the dataclass shape and the F4.1 ``is_answerable`` rule.
2. A seeded-palace test that exercises the real partitioning: one supporting
   drawer, one stale drawer via a ``gap_event`` with status ``superseded``,
   and one contradicting drawer via opposite-polarity triples. Asserts the
   three sets are pairwise disjoint AND that each contains the expected id.
"""

from __future__ import annotations

from mempalace.evidence.evidence_pack import (
    EvidencePack,
    build_evidence_pack,
    is_answerable,
)
from mempalace.graph.gap_graph import GapEvent, ensure_gap_schema, record_gap_event


def test_evidence_pack_supporting_from_candidates():
    pack = build_evidence_pack("q", [{"drawer_id": "d1", "routes": ["a", "b"]}])
    assert pack.supporting == ["d1"]


def test_answerable_rule():
    assert is_answerable(EvidencePack("q", supporting=["d1"], route_count_for_top=2))
    assert not is_answerable(
        EvidencePack("q", supporting=[], stale=["d1"], route_count_for_top=2)
    )
    assert not is_answerable(EvidencePack("q", supporting=["d1"], route_count_for_top=1))


def test_evidence_pack_real_partitions_disjoint_with_seeded_palace(kg):
    """Seed real triples + gap events; verify supporting/stale/contradicting partition."""

    # Two currently-valid triples that disagree on the object — Riley lives
    # in Boston AND Austin. ``find_contradictions`` keys on
    # (subject, predicate) with different ``object`` AND/OR different
    # ``polarity``, so this is the canonical "live contradiction" shape.
    kg.add_triple(
        "Riley",
        "current_location",
        "Boston",
        valid_from="2026-01-01",
        source_drawer_id="drawer_contradicting_a",
    )
    kg.add_triple(
        "Riley",
        "current_location",
        "Austin",
        valid_from="2026-02-01",
        source_drawer_id="drawer_contradicting_b",
    )

    # One supporting drawer not implicated by gap events or contradictions.
    kg.add_triple(
        "Riley",
        "wrote",
        "spec",
        valid_from="2026-03-01",
        source_drawer_id="drawer_supporting",
    )

    conn = kg._conn()
    ensure_gap_schema(conn)
    record_gap_event(
        conn,
        GapEvent(
            id="gap_stale_001",
            gap_type="single_value_conflict",
            status="superseded",
            subject=kg._entity_id("Riley"),
            predicate="current_role",
            object="dev",
        ),
    )
    conn.execute(
        "UPDATE gap_events SET old_drawer_id=?, new_drawer_id=? WHERE id=?",
        ("drawer_stale", None, "gap_stale_001"),
    )

    candidates = [
        {"drawer_id": "drawer_supporting", "routes": ["axis", "vector"]},
        {"drawer_id": "drawer_contradicting_a", "routes": ["axis"]},
        {"drawer_id": "drawer_contradicting_b", "routes": ["axis"]},
        {"drawer_id": "drawer_stale", "routes": ["axis"]},
    ]
    pack = build_evidence_pack(
        "Riley axes preferences",
        candidates,
        knowledge_graph=kg,
        gap_graph=conn,
    )

    sup = set(pack.supporting)
    con = set(pack.contradicting)
    sta = set(pack.stale)

    # Each expected drawer landed in the correct bucket.
    assert "drawer_supporting" in sup, pack
    assert "drawer_contradicting_a" in con or "drawer_contradicting_b" in con, pack
    assert "drawer_stale" in sta, pack

    # Pairwise disjoint by construction.
    assert sup.isdisjoint(con)
    assert sup.isdisjoint(sta)
    assert con.isdisjoint(sta)


def test_evidence_pack_resilient_when_kg_unavailable():
    """No KG/gap graph wired ⇒ everything classified as supporting."""
    pack = build_evidence_pack(
        "Riley axes",
        [{"drawer_id": "d1", "routes": ["a", "b"]}, {"drawer_id": "d2", "routes": ["a"]}],
    )
    assert set(pack.supporting) == {"d1", "d2"}
    assert pack.contradicting == []
    assert pack.stale == []
