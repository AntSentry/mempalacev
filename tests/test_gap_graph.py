import sqlite3

import pytest

from mempalace.graph.gap_graph import (
    GapEvent,
    deterministic_gap_id,
    find_open_gaps,
    find_supersession_chain,
    gap_graph_enabled,
    list_gap_events,
    open_gap_event,
    record_gap_event,
    resolve_gap_event,
    transition_gap_event,
)
from mempalace.knowledge_graph import KnowledgeGraph


def test_gap_graph_flag_parsing():
    assert gap_graph_enabled({"MEMPALACE_ENABLE_GAP_GRAPH": "1"}) is True
    assert gap_graph_enabled({"MEMPALACE_ENABLE_GAP_GRAPH": "false"}) is False


def test_gap_event_lifecycle():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE triples (
            id TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object TEXT NOT NULL,
            valid_from TEXT,
            valid_to TEXT,
            confidence REAL DEFAULT 1.0,
            source_drawer_id TEXT,
            extracted_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    gap_id = deterministic_gap_id("single_value_conflict", "alice", "current_role", "lead")
    record_gap_event(
        conn,
        GapEvent(
            id=gap_id,
            gap_type="single_value_conflict",
            status="open",
            subject="alice",
            predicate="current_role",
            object="lead",
            details={"why": "test"},
        ),
    )

    gaps = list_gap_events(conn)
    assert len(gaps) == 1
    assert gaps[0]["details"] == {"why": "test"}

    assert resolve_gap_event(conn, gap_id, status="resolved", note="accepted") is True
    assert list_gap_events(conn, status="open") == []
    assert list_gap_events(conn, status="resolved")[0]["resolution_note"] == "accepted"


def test_open_gap_event_inserts_row():
    conn = _gap_conn()
    event_id = open_gap_event(
        conn,
        subject_id="riley",
        predicate="lives_in",
        old_object="boston",
        new_object="austin",
        old_drawer_id="d_old",
        new_drawer_id="d_new",
        triggered_by_triple_id="t_new",
        detected_by="test",
        valid_from="2025-06-01",
    )
    row = conn.execute("SELECT * FROM gap_events WHERE id=?", (event_id,)).fetchone()
    assert row["status"] == "open"
    assert row["supersession_chain_id"].startswith("chain_")


def test_transition_legal_succeeds():
    conn = _gap_conn()
    event_id = open_gap_event(conn, "riley", "lives_in", "boston", "austin", None, None, "t2", "test")
    assert transition_gap_event(conn, event_id, "dismissed", rationale="duplicate") is True
    assert list_gap_events(conn, status="dismissed")[0]["rationale"] == "duplicate"


def test_transition_illegal_rejected():
    conn = _gap_conn()
    event_id = open_gap_event(conn, "riley", "lives_in", "boston", "austin", None, None, "t2", "test")
    transition_gap_event(conn, event_id, "dismissed", rationale="duplicate")
    with pytest.raises(ValueError, match="illegal gap transition"):
        transition_gap_event(conn, event_id, "resolved", evidence_drawer_id="d1", rationale="evidence")


def test_transition_resolved_requires_evidence():
    conn = _gap_conn()
    event_id = open_gap_event(conn, "riley", "lives_in", "boston", "austin", None, None, "t2", "test")
    with pytest.raises(ValueError, match="evidence_drawer_id"):
        transition_gap_event(conn, event_id, "resolved", rationale="accepted")


def test_auto_detection_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMPALACE_ENABLE_GAP_GRAPH", "1")
    kg = KnowledgeGraph(str(tmp_path / "kg.sqlite3"))
    try:
        original = kg.add_triple("Riley", "lives_in", "Boston", valid_from="2024-01-01")
        newer = kg.add_triple("Riley", "lives_in", "Austin", valid_from="2025-06-01")
        conn = kg._conn()
        gaps = find_open_gaps(conn)
        assert len(gaps) == 1
        old_row = conn.execute("SELECT valid_to, supersession_chain_id FROM triples WHERE id=?", (original,)).fetchone()
        new_row = conn.execute(
            "SELECT supersedes_triple_id, supersession_chain_id FROM triples WHERE id=?", (newer,)
        ).fetchone()
        assert old_row["valid_to"] == "2025-06-01"
        assert new_row["supersedes_triple_id"] == original
        assert old_row["supersession_chain_id"] == new_row["supersession_chain_id"]
    finally:
        kg.close()


def test_supersession_chain_three_corrections(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMPALACE_ENABLE_GAP_GRAPH", "1")
    kg = KnowledgeGraph(str(tmp_path / "kg.sqlite3"))
    try:
        kg.add_triple("Riley", "lives_in", "Boston", valid_from="2024-01-01")
        kg.add_triple("Riley", "lives_in", "Austin", valid_from="2025-06-01")
        third = kg.add_triple("Riley", "lives_in", "Chicago", valid_from="2026-01-01")
        conn = kg._conn()
        row = conn.execute("SELECT supersession_chain_id FROM triples WHERE id=?", (third,)).fetchone()
        chain = find_supersession_chain(conn, row["supersession_chain_id"])
        assert [item["object"] for item in chain] == [
            kg._entity_id("Boston"),
            kg._entity_id("Austin"),
            kg._entity_id("Chicago"),
        ]
    finally:
        kg.close()


def _gap_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE triples (
            id TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object TEXT NOT NULL,
            valid_from TEXT,
            valid_to TEXT,
            confidence REAL DEFAULT 1.0,
            source_drawer_id TEXT,
            extracted_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    return conn
