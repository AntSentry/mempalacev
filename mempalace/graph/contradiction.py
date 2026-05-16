"""Conservative contradiction detection for knowledge-graph triples."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List, Optional

from .gap_graph import GapEvent, deterministic_gap_id


@dataclass(frozen=True)
class Contradiction:
    first_triple_id: str
    second_triple_id: str
    subject: str
    predicate: str
    first_object: str
    second_object: str
    first_polarity: Optional[int] = None
    second_polarity: Optional[int] = None


SINGLE_VALUE_PREDICATES = {
    "current_location",
    "current_role",
    "current_status",
    "primary_email",
    "preferred_name",
}

OPPOSING_PREDICATES = {
    "prefers": "opposes",
    "opposes": "prefers",
}


def find_contradictions_for_triple(
    conn: sqlite3.Connection,
    triple_id: str,
    subject_id: str,
    predicate: str,
    object_id: str,
    valid_from: Optional[str] = None,
    valid_to: Optional[str] = None,
) -> List[GapEvent]:
    """Return conservative contradiction gaps for a newly inserted triple."""
    gaps: List[GapEvent] = []
    pred = predicate.lower().replace(" ", "_")
    if pred in SINGLE_VALUE_PREDICATES:
        rows = conn.execute(
            """
            SELECT id, object FROM triples
            WHERE subject=? AND predicate=? AND object<>? AND valid_to IS NULL AND id<>?
            """,
            (subject_id, pred, object_id, triple_id),
        ).fetchall()
        for row in rows:
            gaps.append(
                GapEvent(
                    id=deterministic_gap_id(
                        "single_value_conflict", subject_id, pred, object_id, triple_id, row["id"]
                    ),
                    gap_type="single_value_conflict",
                    status="open",
                    subject=subject_id,
                    predicate=pred,
                    object=object_id,
                    triple_id=triple_id,
                    conflicting_triple_id=row["id"],
                    details={"conflicting_object": row["object"]},
                )
            )
    opposite = OPPOSING_PREDICATES.get(pred)
    if opposite:
        rows = conn.execute(
            """
            SELECT id FROM triples
            WHERE subject=? AND predicate=? AND object=? AND valid_to IS NULL AND id<>?
            """,
            (subject_id, opposite, object_id, triple_id),
        ).fetchall()
        for row in rows:
            gaps.append(
                GapEvent(
                    id=deterministic_gap_id(
                        "opposing_predicate_conflict", subject_id, pred, object_id, triple_id, row["id"]
                    ),
                    gap_type="opposing_predicate_conflict",
                    status="open",
                    subject=subject_id,
                    predicate=pred,
                    object=object_id,
                    triple_id=triple_id,
                    conflicting_triple_id=row["id"],
                    details={"opposing_predicate": opposite},
                )
            )
    return gaps


def find_contradictions(
    conn: sqlite3.Connection,
    wing: Optional[str] = None,
    polarity_required: bool = True,
) -> List[Contradiction]:
    """Find current-time contradictions across triples.

    ``wing`` is accepted for the Phase 2 API, but only applies when callers have
    joined drawer metadata into the triples schema in a later phase. In the base
    KG schema this function scans current triples globally.
    """
    _ensure_triple_columns(conn)
    if polarity_required:
        comparator = "COALESCE(t1.polarity, 1) <> COALESCE(t2.polarity, 1)"
    else:
        comparator = "t1.object <> t2.object"
    rows = conn.execute(
        f"""
        SELECT
            t1.id AS first_triple_id,
            t2.id AS second_triple_id,
            t1.subject AS subject,
            t1.predicate AS predicate,
            t1.object AS first_object,
            t2.object AS second_object,
            t1.polarity AS first_polarity,
            t2.polarity AS second_polarity
        FROM triples t1
        JOIN triples t2
          ON t1.subject = t2.subject
         AND t1.predicate = t2.predicate
         AND t1.valid_to IS NULL
         AND t2.valid_to IS NULL
         AND t1.id < t2.id
        WHERE {comparator}
        ORDER BY t1.subject, t1.predicate, t1.id, t2.id
        """
    ).fetchall()
    return [Contradiction(**dict(row)) for row in rows]


def _ensure_triple_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(triples)").fetchall()}
    if "polarity" not in existing:
        conn.execute("ALTER TABLE triples ADD COLUMN polarity INTEGER DEFAULT 1")
