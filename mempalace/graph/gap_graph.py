"""Gap-event lifecycle APIs for the topology-layer knowledge graph."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional
import uuid


GAP_GRAPH_FLAG = "MEMPALACE_ENABLE_GAP_GRAPH"
OPEN = "open"
RESOLVED = "resolved"
DISMISSED = "dismissed"
SUPERSEDED = "superseded"


@dataclass(frozen=True)
class GapEvent:
    id: str
    gap_type: str
    status: str
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    triple_id: Optional[str] = None
    conflicting_triple_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


def gap_graph_enabled(env: Optional[dict] = None) -> bool:
    """Return true when gap graph writes should run."""
    value = (env or os.environ).get(GAP_GRAPH_FLAG, "")
    return value.lower() in {"1", "true", "yes", "on"}


def ensure_gap_schema(conn: sqlite3.Connection) -> None:
    """Create a compatible gap schema when migrations have not run yet."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS gap_event_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_status TEXT NOT NULL,
            to_status TEXT NOT NULL,
            actor TEXT DEFAULT 'system',
            allowed INTEGER NOT NULL DEFAULT 1,
            requires_evidence INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(from_status, to_status, actor)
        );
        INSERT OR IGNORE INTO gap_event_transitions (from_status, to_status, actor, allowed, requires_evidence) VALUES
        ('open', 'resolved', 'system', 1, 1),
        ('open', 'dismissed', 'system', 1, 0),
        ('open', 'resolved', 'user', 1, 1),
        ('open', 'dismissed', 'user', 1, 0),
        ('resolved', 'open', 'user', 1, 0),
        ('dismissed', 'open', 'user', 1, 0);

        CREATE TABLE IF NOT EXISTS gap_events (
            id TEXT PRIMARY KEY,
            gap_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            subject TEXT,
            predicate TEXT,
            object TEXT,
            old_object TEXT,
            new_object TEXT,
            old_drawer_id TEXT,
            new_drawer_id TEXT,
            triple_id TEXT,
            conflicting_triple_id TEXT,
            triggered_by_triple_id TEXT,
            detected_by TEXT,
            confidence REAL DEFAULT 1.0,
            supersession_chain_id TEXT,
            details TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT,
            resolution_note TEXT,
            evidence_drawer_id TEXT,
            rationale TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_gap_events_status ON gap_events(status);
        CREATE INDEX IF NOT EXISTS idx_gap_events_subject_predicate ON gap_events(subject, predicate);
        CREATE INDEX IF NOT EXISTS idx_gap_events_type ON gap_events(gap_type);
        CREATE INDEX IF NOT EXISTS idx_gap_events_chain ON gap_events(supersession_chain_id);
        """
    )
    _ensure_columns(conn, "triples", {
        "relation_class": "TEXT",
        "polarity": "INTEGER DEFAULT 1",
        "supersedes_triple_id": "TEXT",
        "supersession_chain_id": "TEXT",
    })


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: Dict[str, str]) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def deterministic_gap_id(
    gap_type: str,
    subject: Optional[str],
    predicate: Optional[str],
    obj: Optional[str],
    triple_id: Optional[str] = None,
    conflicting_triple_id: Optional[str] = None,
) -> str:
    material = "\0".join(
        [gap_type, subject or "", predicate or "", obj or "", triple_id or "", conflicting_triple_id or ""]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"gap_{digest}"


def _canonical_gap_id(subject_id: str, predicate: str, valid_from: Optional[str], triggered_by_triple_id: str) -> str:
    payload = json.dumps(
        {
            "subject_id": subject_id,
            "predicate": predicate,
            "valid_from": valid_from,
            "triggered_by_triple_id": triggered_by_triple_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"gap_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _chain_id_for(conn: sqlite3.Connection, subject_id: str, predicate: str) -> str:
    row = conn.execute(
        """
        SELECT supersession_chain_id FROM gap_events
        WHERE subject=? AND predicate=? AND supersession_chain_id IS NOT NULL
        ORDER BY created_at ASC LIMIT 1
        """,
        (subject_id, predicate),
    ).fetchone()
    if row and row["supersession_chain_id"]:
        return row["supersession_chain_id"]
    row = conn.execute(
        """
        SELECT supersession_chain_id FROM triples
        WHERE subject=? AND predicate=? AND supersession_chain_id IS NOT NULL
        ORDER BY valid_from ASC, extracted_at ASC, id ASC LIMIT 1
        """,
        (subject_id, predicate),
    ).fetchone()
    if row and row["supersession_chain_id"]:
        return row["supersession_chain_id"]
    return f"chain_{uuid.uuid4().hex}"


def open_gap_event(
    conn: sqlite3.Connection,
    subject_id: str,
    predicate: str,
    old_object: str,
    new_object: str,
    old_drawer_id: Optional[str],
    new_drawer_id: Optional[str],
    triggered_by_triple_id: str,
    detected_by: str,
    confidence: float = 1.0,
    conflicting_triple_id: Optional[str] = None,
    valid_from: Optional[str] = None,
) -> str:
    """Open a supersession gap event and return its deterministic event id."""
    ensure_gap_schema(conn)
    pred = predicate.lower().replace(" ", "_")
    chain_id = _chain_id_for(conn, subject_id, pred)
    event_id = _canonical_gap_id(subject_id, pred, valid_from, triggered_by_triple_id)
    details = json.dumps({"old_object": old_object, "new_object": new_object}, sort_keys=True)
    conn.execute(
        """
        INSERT OR IGNORE INTO gap_events (
            id, gap_type, status, subject, predicate, object, old_object, new_object,
            old_drawer_id, new_drawer_id, triple_id, conflicting_triple_id,
            triggered_by_triple_id, detected_by, confidence, supersession_chain_id, details
        ) VALUES (?, 'supersession_conflict', 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            subject_id,
            pred,
            new_object,
            old_object,
            new_object,
            old_drawer_id,
            new_drawer_id,
            triggered_by_triple_id,
            conflicting_triple_id,
            triggered_by_triple_id,
            detected_by,
            confidence,
            chain_id,
            details,
        ),
    )
    return event_id


def transition_gap_event(
    conn: sqlite3.Connection,
    event_id: str,
    to_status: str,
    evidence_drawer_id: Optional[str] = None,
    rationale: Optional[str] = None,
    actor: str = "user",
) -> bool:
    """Transition a gap event using the seeded state machine."""
    ensure_gap_schema(conn)
    event = conn.execute("SELECT status FROM gap_events WHERE id=?", (event_id,)).fetchone()
    if event is None:
        return False
    transition = conn.execute(
        """
        SELECT requires_evidence FROM gap_event_transitions
        WHERE from_status=? AND to_status=? AND actor=? AND allowed=1
        """,
        (event["status"], to_status, actor),
    ).fetchone()
    if transition is None and actor != "system":
        transition = conn.execute(
            """
            SELECT requires_evidence FROM gap_event_transitions
            WHERE from_status=? AND to_status=? AND actor='system' AND allowed=1
            """,
            (event["status"], to_status),
        ).fetchone()
    if transition is None:
        raise ValueError(f"illegal gap transition: {event['status']} -> {to_status}")
    if int(transition["requires_evidence"] or 0) and not evidence_drawer_id:
        raise ValueError("evidence_drawer_id is required for this gap transition")
    conn.execute(
        """
        UPDATE gap_events
        SET status=?, updated_at=CURRENT_TIMESTAMP,
            resolved_at=CASE WHEN ? = 'open' THEN NULL ELSE CURRENT_TIMESTAMP END,
            evidence_drawer_id=?, rationale=?, resolution_note=?
        WHERE id=?
        """,
        (to_status, to_status, evidence_drawer_id, rationale, rationale, event_id),
    )
    return True


def auto_detect_gap_on_triple_write(
    conn: sqlite3.Connection,
    triple_id: str,
    subject_id: str,
    predicate: str,
    object_id: str,
    valid_from: Optional[str] = None,
    source_drawer_id: Optional[str] = None,
    detected_by: str = "knowledge_graph.add_triple",
) -> Optional[str]:
    """Detect same subject/predicate object changes and maintain supersession metadata."""
    ensure_gap_schema(conn)
    pred = predicate.lower().replace(" ", "_")
    old = conn.execute(
        """
        SELECT id, object, source_drawer_id, supersession_chain_id FROM triples
        WHERE subject=? AND predicate=? AND object<>? AND valid_to IS NULL AND id<>?
        ORDER BY valid_from DESC, extracted_at DESC, id DESC LIMIT 1
        """,
        (subject_id, pred, object_id, triple_id),
    ).fetchone()
    if old is None:
        return None
    event_id = open_gap_event(
        conn,
        subject_id=subject_id,
        predicate=pred,
        old_object=old["object"],
        new_object=object_id,
        old_drawer_id=old["source_drawer_id"],
        new_drawer_id=source_drawer_id,
        triggered_by_triple_id=triple_id,
        detected_by=detected_by,
        conflicting_triple_id=old["id"],
        valid_from=valid_from,
    )
    chain_row = conn.execute("SELECT supersession_chain_id FROM gap_events WHERE id=?", (event_id,)).fetchone()
    chain_id = chain_row["supersession_chain_id"] if chain_row else old["supersession_chain_id"]
    if not chain_id:
        chain_id = f"chain_{uuid.uuid4().hex}"
    conn.execute(
        "UPDATE triples SET valid_to=?, supersession_chain_id=? WHERE id=?",
        (valid_from, chain_id, old["id"]),
    )
    conn.execute(
        "UPDATE triples SET supersedes_triple_id=?, supersession_chain_id=? WHERE id=?",
        (old["id"], chain_id, triple_id),
    )
    return event_id


def record_gap_event(conn: sqlite3.Connection, event: GapEvent) -> str:
    """Insert or keep an existing open gap event; returns the event id."""
    ensure_gap_schema(conn)
    details = json.dumps(event.details or {}, sort_keys=True)
    conn.execute(
        """
        INSERT OR IGNORE INTO gap_events (
            id, gap_type, status, subject, predicate, object,
            triple_id, conflicting_triple_id, triggered_by_triple_id, details
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.id,
            event.gap_type,
            event.status,
            event.subject,
            event.predicate,
            event.object,
            event.triple_id,
            event.conflicting_triple_id,
            event.triple_id,
            details,
        ),
    )
    return event.id


def list_gap_events(
    conn: sqlite3.Connection,
    status: str = OPEN,
    gap_type: Optional[str] = None,
    limit: int = 50,
    subject: Optional[str] = None,
) -> List[dict]:
    """List gap events filtered by status/type/subject."""
    ensure_gap_schema(conn)
    limit = max(1, min(int(limit), 500))
    clauses = []
    params: List[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if gap_type:
        clauses.append("gap_type = ?")
        params.append(gap_type)
    if subject:
        clauses.append("subject = ?")
        params.append(subject)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT * FROM gap_events
        {where}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        params + [limit],
    ).fetchall()
    return [_row_to_gap(row) for row in rows]


def find_open_gaps(conn: sqlite3.Connection, subject_id: Optional[str] = None) -> List[dict]:
    """Return open gap events, optionally filtered by subject id."""
    return list_gap_events(conn, status=OPEN, subject=subject_id)


def find_supersession_chain(conn: sqlite3.Connection, chain_id: str) -> List[dict]:
    """Return triples in one supersession chain in chronological order."""
    ensure_gap_schema(conn)
    rows = conn.execute(
        """
        SELECT * FROM triples
        WHERE supersession_chain_id=?
        ORDER BY valid_from ASC, extracted_at ASC, id ASC
        """,
        (chain_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def resolve_gap_event(
    conn: sqlite3.Connection,
    gap_id: str,
    status: str = RESOLVED,
    note: Optional[str] = None,
) -> bool:
    """Backward-compatible wrapper around ``transition_gap_event``."""
    return transition_gap_event(conn, gap_id, status, evidence_drawer_id="legacy", rationale=note)


def _row_to_gap(row: sqlite3.Row) -> dict:
    data = dict(row)
    try:
        data["details"] = json.loads(data.get("details") or "{}")
    except (TypeError, ValueError):
        data["details"] = {}
    return data
