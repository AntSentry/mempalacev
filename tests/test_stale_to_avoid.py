"""Tests that the stale_to_avoid slot is in lockstep with the gap-state machine.

Spec §6.11 exit criterion: ``stale_to_avoid`` never surfaces facts whose
corresponding gap_event is still ``open``. The pair of tests here flip a
single gap from open -> superseded and assert that the subject migrates
between the two slots (open_gaps ↔ stale_to_avoid) accordingly.
"""

from __future__ import annotations

import sqlite3

import pytest

from mempalace.graph.gap_graph import ensure_gap_schema, open_gap_event
from mempalace.knowledge_graph import KnowledgeGraph
from mempalace.memory_stack.l1_balanced_wakeup import balanced_wakeup


@pytest.fixture
def palace_kg_paths(tmp_path):
    palace = tmp_path / "palace"
    palace.mkdir()
    identity = tmp_path / "identity.txt"
    identity.write_text("test identity", encoding="utf-8")
    kg_db = tmp_path / "kg.sqlite3"
    return str(palace), str(identity), str(kg_db)


def _seed_open_gap(kg_path: str) -> str:
    """Seed a single open gap on ``principal lives_in boston -> austin``."""
    # KnowledgeGraph creates the triples schema; gap_graph's column
    # ALTERs in ensure_gap_schema assume that table already exists.
    KnowledgeGraph(db_path=kg_path).close()

    conn = sqlite3.connect(kg_path)
    conn.row_factory = sqlite3.Row
    ensure_gap_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO triples (id, subject, predicate, object, valid_from) "
        "VALUES ('t_loc_new', 'principal', 'lives_in', 'austin', '2026-04-01')"
    )
    gap_id = open_gap_event(
        conn,
        subject_id="principal",
        predicate="lives_in",
        old_object="boston",
        new_object="austin",
        old_drawer_id="drawer_loc_old",
        new_drawer_id="drawer_loc_new",
        triggered_by_triple_id="t_loc_new",
        detected_by="test",
        valid_from="2026-04-01",
    )
    conn.commit()
    conn.close()
    return gap_id


def _set_gap_status(kg_path: str, gap_id: str, status: str) -> None:
    conn = sqlite3.connect(kg_path)
    conn.execute("UPDATE gap_events SET status=? WHERE id=?", (status, gap_id))
    conn.commit()
    conn.close()


def test_open_gap_appears_in_open_gaps_slot_only(palace_kg_paths):
    palace_path, identity_path, kg_path = palace_kg_paths
    _seed_open_gap(kg_path)

    output = balanced_wakeup(
        budget_tokens=2000,
        palace_path=palace_path,
        identity_path=identity_path,
        kg_path=kg_path,
    )

    assert "lives_in" in output.slots["open_gaps"]
    assert "boston" in output.slots["open_gaps"] or "austin" in output.slots["open_gaps"]
    # The same subject must NOT appear in stale_to_avoid while open.
    assert "lives_in" not in output.slots["stale_to_avoid"]


def test_superseded_gap_migrates_from_open_to_stale_slot(palace_kg_paths):
    palace_path, identity_path, kg_path = palace_kg_paths
    gap_id = _seed_open_gap(kg_path)

    # Transition to superseded; the slot must move in lockstep.
    _set_gap_status(kg_path, gap_id, "superseded")

    output = balanced_wakeup(
        budget_tokens=2000,
        palace_path=palace_path,
        identity_path=identity_path,
        kg_path=kg_path,
    )

    assert "lives_in" in output.slots["stale_to_avoid"]
    assert "austin" in output.slots["stale_to_avoid"]
    # And the open_gaps slot must no longer mention the same gap.
    assert "lives_in" not in output.slots["open_gaps"]
