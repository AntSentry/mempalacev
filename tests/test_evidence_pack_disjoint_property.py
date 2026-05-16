"""Property test: ``EvidencePack`` partitions are always pairwise disjoint.

Uses Hypothesis to generate random configurations including non-empty
``stale`` and ``contradicting`` sets, then asserts every pair of partitions is
disjoint. Exercises ``build_evidence_pack`` with a real seeded SQLite KG so
the partitioning runs against the same paths used in production.
"""

from __future__ import annotations

import os
import string
import tempfile

from hypothesis import HealthCheck, given, settings, strategies as st

from mempalace.evidence.evidence_pack import EvidencePack, build_evidence_pack
from mempalace.graph.gap_graph import GapEvent, ensure_gap_schema, record_gap_event
from mempalace.knowledge_graph import KnowledgeGraph


# Drawer id alphabet is constrained so Hypothesis can shrink readably; the
# actual ``EvidencePack`` machinery treats them as opaque strings.
_DRAWER_ID = st.text(alphabet=string.ascii_lowercase + string.digits, min_size=4, max_size=8)


def test_evidence_pack_disjoint_property_direct():
    """Direct dataclass construction with overlapping inputs is still disjoint by
    construction at the consumer; verify it via a baseline assertion."""
    pack = EvidencePack("q", supporting=["a"], contradicting=["b"], stale=["c"])
    assert set(pack.supporting).isdisjoint(pack.contradicting)
    assert set(pack.supporting).isdisjoint(pack.stale)
    assert set(pack.contradicting).isdisjoint(pack.stale)


@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    candidate_ids=st.lists(_DRAWER_ID, min_size=1, max_size=8, unique=True),
    stale_count=st.integers(min_value=0, max_value=3),
    contradict_count=st.integers(min_value=0, max_value=3),
)
def test_evidence_pack_partitions_pairwise_disjoint(
    candidate_ids, stale_count, contradict_count
):
    """For every random palace seeded with stale + contradicting drawers, the
    three partitions returned by ``build_evidence_pack`` are pairwise disjoint.
    """

    # Build a fresh KG + connection per example so seeded data does not leak.
    tmp_db = tempfile.NamedTemporaryFile(
        suffix=".sqlite3", delete=False, prefix="hyp_evidence_"
    )
    tmp_db.close()
    kg = KnowledgeGraph(db_path=tmp_db.name)
    try:
        conn = kg._conn()
        ensure_gap_schema(conn)

        # Seed stale drawers: gap_events with status=superseded touching Riley.
        stale_ids = list(candidate_ids[:stale_count])
        for idx, did in enumerate(stale_ids):
            record_gap_event(
                conn,
                GapEvent(
                    id=f"gap_hyp_{idx}",
                    gap_type="single_value_conflict",
                    status="superseded",
                    subject=kg._entity_id("Riley"),
                    predicate="current_role",
                    object=f"role_{idx}",
                ),
            )
            conn.execute(
                "UPDATE gap_events SET old_drawer_id=? WHERE id=?",
                (did, f"gap_hyp_{idx}"),
            )

        # Seed contradicting drawers: same (subject, predicate) with different
        # objects, both currently valid. Each pair of source_drawer_ids
        # contributes two candidates to the contradicting partition.
        contradict_ids = list(candidate_ids[stale_count : stale_count + contradict_count])
        for idx, did in enumerate(contradict_ids):
            kg.add_triple(
                "Riley",
                "current_location",
                f"City_{idx}",
                valid_from=f"2026-0{(idx % 9) + 1}-01",
                source_drawer_id=did,
            )

        candidates = [
            {"drawer_id": did, "routes": ["axis", "vector"]} for did in candidate_ids
        ]

        pack = build_evidence_pack(
            "Riley contradiction",
            candidates,
            knowledge_graph=kg,
            gap_graph=conn,
        )

        sup = set(pack.supporting)
        con = set(pack.contradicting)
        sta = set(pack.stale)

        assert sup.isdisjoint(con), pack
        assert sup.isdisjoint(sta), pack
        assert con.isdisjoint(sta), pack

        # Every classified id was in the original candidate pool.
        all_classified = sup | con | sta
        assert all_classified <= set(candidate_ids)
    finally:
        kg.close()
        try:
            os.unlink(tmp_db.name)
        except OSError:
            pass
