import sqlite3

from mempalace.graph.contradiction import find_contradictions, find_contradictions_for_triple


def _conn_with_triples():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE triples (
            id TEXT PRIMARY KEY,
            subject TEXT,
            predicate TEXT,
            object TEXT,
            polarity INTEGER DEFAULT 1,
            valid_to TEXT
        );
        """
    )
    return conn


def test_single_value_conflict_detected():
    conn = _conn_with_triples()
    conn.execute(
        "INSERT INTO triples (id, subject, predicate, object, valid_to) VALUES (?, ?, ?, ?, NULL)",
        ("old", "alice", "current_role", "engineer"),
    )
    gaps = find_contradictions_for_triple(conn, "new", "alice", "current_role", "manager")
    assert len(gaps) == 1
    assert gaps[0].gap_type == "single_value_conflict"
    assert gaps[0].conflicting_triple_id == "old"


def test_opposing_predicate_conflict_detected():
    conn = _conn_with_triples()
    conn.execute(
        "INSERT INTO triples (id, subject, predicate, object, valid_to) VALUES (?, ?, ?, ?, NULL)",
        ("old", "alice", "opposes", "dark_mode"),
    )
    gaps = find_contradictions_for_triple(conn, "new", "alice", "prefers", "dark_mode")
    assert len(gaps) == 1
    assert gaps[0].gap_type == "opposing_predicate_conflict"


def test_find_contradictions_polarity_required():
    conn = _conn_with_triples()
    conn.execute(
        "INSERT INTO triples (id, subject, predicate, object, polarity, valid_to) VALUES (?, ?, ?, ?, ?, NULL)",
        ("t1", "alice", "prefers", "dark_mode", 1),
    )
    conn.execute(
        "INSERT INTO triples (id, subject, predicate, object, polarity, valid_to) VALUES (?, ?, ?, ?, ?, NULL)",
        ("t2", "alice", "prefers", "dark_mode", -1),
    )
    contradictions = find_contradictions(conn, polarity_required=True)
    assert len(contradictions) == 1
    assert contradictions[0].first_triple_id == "t1"


def test_find_contradictions_object_diff():
    conn = _conn_with_triples()
    conn.execute(
        "INSERT INTO triples (id, subject, predicate, object, polarity, valid_to) VALUES (?, ?, ?, ?, ?, NULL)",
        ("t1", "alice", "lives_in", "boston", 1),
    )
    conn.execute(
        "INSERT INTO triples (id, subject, predicate, object, polarity, valid_to) VALUES (?, ?, ?, ?, ?, NULL)",
        ("t2", "alice", "lives_in", "austin", 1),
    )
    contradictions = find_contradictions(conn, polarity_required=False)
    assert len(contradictions) == 1
    assert contradictions[0].second_object == "austin"


def test_find_contradictions_returns_empty_on_clean_palace():
    conn = _conn_with_triples()
    conn.execute(
        "INSERT INTO triples (id, subject, predicate, object, polarity, valid_to) VALUES (?, ?, ?, ?, ?, NULL)",
        ("t1", "alice", "lives_in", "boston", 1),
    )
    assert find_contradictions(conn, polarity_required=False) == []
