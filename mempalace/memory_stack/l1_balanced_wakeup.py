"""Nine-slot balanced wake-up context.

Phase 6 of MEMPALACE_TOPOLOGY_SPEC.md §6.11. Each slot is sourced from a real
subsystem (L0 identity file, knowledge graph, gap graph, palace_graph tunnels,
or diary drawers). When a source is empty or unavailable, the slot returns a
friendly "no <slot_name>" string rather than raising — wake-up must always
return a complete output, even on a brand-new palace.

The slot order in ``SLOT_ORDER`` is the priority order. Slots are packed into
``budget_tokens`` in priority order (priority 1 = identity_anchor first); when
remaining budget cannot fit a slot's full text, the slot is truncated to fit.
When a slot's remaining budget is zero, it is dropped and recorded in
``truncated_slots``. This implements "drop in reverse priority order".

Token accounting uses the project-wide 4-char-per-token heuristic; see
``_tokens`` and ``_truncate``. Slot text comes from real data sources so the
wake-up output reflects the user's actual palace state, not a hardcoded
placeholder.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional


SLOT_ORDER = [
    "identity_anchor",
    "active_projects",
    "current_preferences",
    "current_constraints",
    "recent_decisions",
    "open_gaps",
    "stale_to_avoid",
    "cross_wing_analogies",
    "agent_diary_summaries",
]

# Per-slot (min_tokens, max_tokens) from spec §6.11. Priority is implicit in
# SLOT_ORDER (index + 1). min_tokens is the floor at which the slot still
# carries useful signal; below that we drop the slot. max_tokens is the soft
# ceiling on the slot's rendered text before global budget enforcement.
SLOT_LIMITS: Dict[str, tuple[int, int]] = {
    "identity_anchor": (50, 100),
    "active_projects": (80, 100),
    "current_preferences": (100, 120),
    "current_constraints": (60, 80),
    "recent_decisions": (100, 120),
    "open_gaps": (100, 150),
    "stale_to_avoid": (50, 80),
    "cross_wing_analogies": (30, 50),
    "agent_diary_summaries": (60, 100),
}


@dataclass(frozen=True)
class WakeUpOutput:
    slots: Dict[str, str] = field(default_factory=dict)
    tokens_used: int = 0
    truncated_slots: List[str] = field(default_factory=list)


def _tokens(text: str) -> int:
    """Project-wide 4-char-per-token heuristic, with a 1-token floor."""
    return max(1, len(text) // 4) if text else 0


def _truncate(text: str, max_tokens: int) -> str:
    """Hard-truncate text to fit within ``max_tokens`` (×4 chars)."""
    if max_tokens <= 0:
        return ""
    return text[: max_tokens * 4]


def _empty(slot_name: str, hint: str = "") -> str:
    """Friendly empty-slot placeholder. Never raises; never logs."""
    base = f"no {slot_name}"
    return f"{base} — {hint}" if hint else base


# ---------------------------------------------------------------------------
# Slot data sources
# ---------------------------------------------------------------------------


def _default_palace_path() -> str:
    from ..config import MempalaceConfig

    return MempalaceConfig().palace_path


def _default_identity_path() -> str:
    return os.path.expanduser("~/.mempalace/identity.txt")


def _default_kg_path(palace_path: Optional[str]) -> str:
    """Match mcp_server's resolution: palace-local KG when palace_path is set."""
    if palace_path:
        return os.path.join(palace_path, "knowledge_graph.sqlite3")
    from ..knowledge_graph import DEFAULT_KG_PATH

    return DEFAULT_KG_PATH


def slot_identity_anchor(
    wing: Optional[str] = None,
    *,
    identity_path: Optional[str] = None,
) -> str:
    """Read ``~/.mempalace/identity.txt`` (or a configured override).

    Identity is wing-agnostic — it anchors the agent across all wings, so the
    ``wing`` argument is accepted for interface uniformity but unused.
    """
    path = identity_path or _default_identity_path()
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, FileNotFoundError):
        return _empty("identity_anchor", f"create {path}")
    if not text:
        return _empty("identity_anchor", f"create {path}")
    return text


def _kg_predicate_lines(
    predicate: str,
    *,
    kg_path: Optional[str],
    wing: Optional[str],
    limit: int = 8,
) -> List[str]:
    """Pull current-time triples for ``predicate`` from the knowledge graph.

    Wing is currently advisory — the base triples schema does not carry a
    wing column, so the slot returns matching triples globally. When a wing
    filter would matter, a later phase can join drawer metadata.
    """
    from ..knowledge_graph import KnowledgeGraph

    path = kg_path or _default_kg_path(None)
    try:
        kg = KnowledgeGraph(db_path=path)
    except (sqlite3.Error, OSError):
        return []
    try:
        triples = kg.query_relationship(predicate)
    except (sqlite3.Error, ValueError):
        triples = []
    finally:
        kg.close()
    lines = []
    for triple in triples:
        if not triple.get("current"):
            continue
        subject = triple.get("subject", "?")
        obj = triple.get("object", "?")
        lines.append(f"- {subject} {predicate} {obj}")
        if len(lines) >= limit:
            break
    return lines


def slot_active_projects(
    wing: Optional[str] = None,
    *,
    kg_path: Optional[str] = None,
) -> str:
    """``works_on`` triples with ``valid_to IS NULL`` from the KG."""
    lines = _kg_predicate_lines("works_on", kg_path=kg_path, wing=wing)
    if not lines:
        return _empty("active_projects", "no current works_on triples")
    return "Active projects:\n" + "\n".join(lines)


def slot_current_preferences(
    wing: Optional[str] = None,
    *,
    kg_path: Optional[str] = None,
) -> str:
    """``prefers`` triples with ``valid_to IS NULL`` from the KG."""
    lines = _kg_predicate_lines("prefers", kg_path=kg_path, wing=wing)
    if not lines:
        return _empty("current_preferences", "no current prefers triples")
    return "Current preferences:\n" + "\n".join(lines)


def slot_current_constraints(
    wing: Optional[str] = None,
    *,
    kg_path: Optional[str] = None,
) -> str:
    """``constrained_by`` triples with ``valid_to IS NULL`` from the KG."""
    lines = _kg_predicate_lines("constrained_by", kg_path=kg_path, wing=wing)
    if not lines:
        return _empty("current_constraints", "no current constrained_by triples")
    return "Current constraints:\n" + "\n".join(lines)


def _query_drawers_by_metadata(
    palace_path: str,
    *,
    where: Optional[dict] = None,
    limit: int = 50,
) -> List[dict]:
    """Return drawer rows matching ``where`` from the palace collection.

    Returns the chroma rows shape ``[{"document": str, "metadata": dict}, ...]``.
    Errors are swallowed (missing palace, schema mismatch) — wake-up must not
    fail because a downstream collection is unavailable on a fresh palace.
    """
    try:
        from ..palace import get_collection

        col = get_collection(palace_path, create=False)
    except Exception:
        return []
    try:
        kwargs: dict = {"include": ["documents", "metadatas"], "limit": int(limit)}
        if where:
            kwargs["where"] = where
        result = col.get(**kwargs)
    except Exception:
        return []
    docs = result.get("documents", []) or []
    metas = result.get("metadatas", []) or []
    rows = []
    for doc, meta in zip(docs, metas):
        rows.append({"document": doc or "", "metadata": meta or {}})
    return rows


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _row_is_recent(meta: dict, *, since_iso: str) -> bool:
    filed = meta.get("filed_at") or meta.get("date") or ""
    if not filed:
        return False
    return str(filed) >= since_iso


def slot_recent_decisions(
    wing: Optional[str] = None,
    *,
    palace_path: Optional[str] = None,
    days: int = 30,
) -> str:
    """Drawers tagged ``decision`` (via room or tags metadata) in the last N days.

    The mempalace drawer schema doesn't reserve a canonical "tags" column, so
    we accept any of three conventions: ``room="decisions"``, a list-shaped
    ``tags`` containing ``"decision"``, or a comma-string ``tags`` field. This
    keeps the slot useful across older palaces while letting tests assert
    against the room-based convention used in seeded fixtures.
    """
    path = palace_path or _default_palace_path()
    since = _iso_days_ago(days)
    candidates: List[str] = []

    # Convention 1: room='decisions' (commonly used by miners + diary).
    where: Optional[dict] = {"room": "decisions"}
    if wing:
        # ChromaDB's where filter requires either a single field or $and.
        where = {"$and": [{"room": "decisions"}, {"wing": wing}]}
    for row in _query_drawers_by_metadata(path, where=where, limit=20):
        if not _row_is_recent(row["metadata"], since_iso=since):
            continue
        snippet = row["document"].strip().splitlines()[0] if row["document"] else ""
        if snippet:
            candidates.append(f"- {snippet[:160]}")

    # Convention 2/3: tags field (list or comma-string). Scan a small recent
    # window since chroma's where filter can't index into list-shaped tags.
    if len(candidates) < 5:
        recent_kwargs_where: Optional[dict] = {"wing": wing} if wing else None
        for row in _query_drawers_by_metadata(path, where=recent_kwargs_where, limit=200):
            meta = row["metadata"]
            tags_val = meta.get("tags")
            if isinstance(tags_val, list):
                has_tag = any(str(t).lower() == "decision" for t in tags_val)
            elif isinstance(tags_val, str):
                has_tag = "decision" in tags_val.lower().split(",")
            else:
                has_tag = False
            if not has_tag:
                continue
            if not _row_is_recent(meta, since_iso=since):
                continue
            snippet = row["document"].strip().splitlines()[0] if row["document"] else ""
            if snippet:
                line = f"- {snippet[:160]}"
                if line not in candidates:
                    candidates.append(line)
            if len(candidates) >= 8:
                break

    if not candidates:
        return _empty("recent_decisions", f"no decision-tagged drawers in last {days} days")
    return "Recent decisions:\n" + "\n".join(candidates[:8])


def _open_gap_rows(
    kg_path: Optional[str],
    *,
    status: str,
    limit: int = 20,
    subject_filter: Optional[str] = None,
) -> List[dict]:
    """Return gap_events rows filtered by status from the KG sqlite db."""
    from ..graph.gap_graph import ensure_gap_schema

    path = kg_path or _default_kg_path(None)
    if not os.path.exists(path):
        return []
    try:
        conn = sqlite3.connect(path)
    except sqlite3.Error:
        return []
    conn.row_factory = sqlite3.Row
    try:
        ensure_gap_schema(conn)
        rows = conn.execute(
            """
            SELECT subject, predicate, object, old_object, new_object, status,
                   new_drawer_id, old_drawer_id, created_at
            FROM gap_events
            WHERE status = ?
              AND (? IS NULL OR subject = ?)
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (status, subject_filter, subject_filter, int(limit)),
        ).fetchall()
    except sqlite3.Error:
        rows = []
    finally:
        conn.close()
    return [dict(r) for r in rows]


def slot_open_gaps(
    wing: Optional[str] = None,
    *,
    kg_path: Optional[str] = None,
) -> str:
    """Open gap events — supersessions or contradictions awaiting resolution."""
    rows = _open_gap_rows(kg_path, status="open")
    if not rows:
        return _empty("open_gaps", "none pending")
    lines = []
    for r in rows[:8]:
        subj = r.get("subject", "?")
        pred = r.get("predicate", "?")
        old = r.get("old_object") or r.get("object") or "?"
        new = r.get("new_object") or "?"
        lines.append(f"- Open gap: {subj} {pred} {old} -> {new}")
    return "Open gaps to resolve:\n" + "\n".join(lines)


def _drawer_text(palace_path: str, drawer_id: str) -> Optional[str]:
    """Look up a drawer by id; return its document text or None on miss."""
    if not drawer_id:
        return None
    try:
        from ..palace import get_collection

        col = get_collection(palace_path, create=False)
    except Exception:
        return None
    try:
        result = col.get(ids=[drawer_id], include=["documents"])
    except Exception:
        return None
    docs = result.get("documents") or []
    if not docs:
        return None
    text = docs[0] or ""
    return text or None


def slot_stale_to_avoid(
    wing: Optional[str] = None,
    *,
    kg_path: Optional[str] = None,
    palace_path: Optional[str] = None,
) -> str:
    """Superseded facts — the *new_object* is surfaced so the agent doesn't
    re-introduce the old one. Never surfaces a fact whose gap is still ``open``;
    the gap-state-machine guarantees a row is in exactly one status at a time.
    """
    rows = _open_gap_rows(kg_path, status="superseded")
    if not rows:
        return _empty("stale_to_avoid", "no superseded facts")
    palace = palace_path or _default_palace_path()
    lines = []
    for r in rows[:8]:
        subj = r.get("subject", "?")
        pred = r.get("predicate", "?")
        new_obj = r.get("new_object") or "?"
        old_obj = r.get("old_object") or "?"
        # Surface the new_object via drawer lookup when we have an id, so the
        # agent sees fresh text rather than a coarse triple slug.
        new_drawer_id = r.get("new_drawer_id")
        new_text = _drawer_text(palace, new_drawer_id) if new_drawer_id else None
        if new_text:
            snippet = new_text.strip().splitlines()[0][:160]
            lines.append(
                f"- Superseded: {subj} {pred} no longer {old_obj}; now {new_obj} ({snippet})"
            )
        else:
            lines.append(
                f"- Superseded: {subj} {pred} no longer {old_obj}; now {new_obj}"
            )
    return "Stale facts to avoid:\n" + "\n".join(lines)


def slot_cross_wing_analogies(
    wing: Optional[str] = None,
    *,
    palace_path: Optional[str] = None,
) -> str:
    """Top tunnels — rooms that appear in more than one wing.

    When ``wing`` is given, returns tunnels touching that wing; otherwise the
    top tunnels palace-wide.
    """
    path = palace_path or _default_palace_path()
    try:
        from ..palace import get_collection
        from ..palace_graph import find_tunnels

        col = get_collection(path, create=False)
    except Exception:
        return _empty("cross_wing_analogies", "no palace available")
    try:
        tunnels = find_tunnels(wing_a=wing, col=col)
    except Exception:
        tunnels = []
    if not tunnels:
        return _empty("cross_wing_analogies", "no shared rooms across wings")
    lines = []
    for tunnel in tunnels[:5]:
        room = tunnel.get("room", "?")
        wings = ", ".join(tunnel.get("wings", []))
        count = tunnel.get("count", 0)
        lines.append(f"- {room} crosses [{wings}] ({count} drawers)")
    return "Cross-wing analogies:\n" + "\n".join(lines)


def slot_agent_diary_summaries(
    wing: Optional[str] = None,
    *,
    palace_path: Optional[str] = None,
    days: int = 7,
) -> str:
    """Recent diary drawers (the ones written by ``diary_ingest``).

    Diary drawers are filed with ``wing='diary'`` and ``room='daily'`` by
    ``mempalace/diary_ingest.py``. We sort by ``filed_at`` and surface the
    first line of each entry — these are the per-day summaries the agent
    writes itself.
    """
    path = palace_path or _default_palace_path()
    since = _iso_days_ago(days)
    rows = _query_drawers_by_metadata(
        path,
        where={"$and": [{"wing": "diary"}, {"room": "daily"}]},
        limit=days * 2,
    )
    if not rows:
        # Fall back to wing-only query for palaces using a different diary wing.
        rows = _query_drawers_by_metadata(
            path,
            where={"room": "daily"},
            limit=days * 2,
        )
    lines = []
    for row in rows:
        meta = row["metadata"]
        if not _row_is_recent(meta, since_iso=since):
            continue
        date = meta.get("date") or meta.get("filed_at", "")[:10] or "?"
        body = row["document"].strip()
        first_line = ""
        for line in body.splitlines():
            stripped = line.strip()
            if stripped:
                first_line = stripped
                break
        if first_line:
            lines.append(f"- {date}: {first_line[:160]}")
        if len(lines) >= 6:
            break
    if not lines:
        return _empty("agent_diary_summaries", f"no diary entries in last {days} days")
    return "Agent diary summaries:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Slot dispatch
# ---------------------------------------------------------------------------


def _build_raw_slots(
    wing: Optional[str],
    *,
    palace_path: Optional[str],
    identity_path: Optional[str],
    kg_path: Optional[str],
) -> Dict[str, str]:
    """Render every slot from its source. Empty sources yield friendly strings.

    Each slot is resolved independently — one failure does not poison the
    rest of the wake-up. Slot functions already swallow OSError/SQLError, so
    the only exceptions that bubble here are programmer-error level; we
    coerce them to the same "no <slot>" placeholder so wake-up still returns.
    """
    palace = palace_path or _default_palace_path()
    kg = kg_path or _default_kg_path(palace)

    def _safe(name: str, fn, *args, **kwargs) -> str:
        try:
            value = fn(*args, **kwargs)
        except Exception:
            return _empty(name, "source unavailable")
        return value or _empty(name)

    return {
        "identity_anchor": _safe(
            "identity_anchor", slot_identity_anchor, wing, identity_path=identity_path
        ),
        "active_projects": _safe(
            "active_projects", slot_active_projects, wing, kg_path=kg
        ),
        "current_preferences": _safe(
            "current_preferences", slot_current_preferences, wing, kg_path=kg
        ),
        "current_constraints": _safe(
            "current_constraints", slot_current_constraints, wing, kg_path=kg
        ),
        "recent_decisions": _safe(
            "recent_decisions", slot_recent_decisions, wing, palace_path=palace
        ),
        "open_gaps": _safe("open_gaps", slot_open_gaps, wing, kg_path=kg),
        "stale_to_avoid": _safe(
            "stale_to_avoid",
            slot_stale_to_avoid,
            wing,
            kg_path=kg,
            palace_path=palace,
        ),
        "cross_wing_analogies": _safe(
            "cross_wing_analogies",
            slot_cross_wing_analogies,
            wing,
            palace_path=palace,
        ),
        "agent_diary_summaries": _safe(
            "agent_diary_summaries",
            slot_agent_diary_summaries,
            wing,
            palace_path=palace,
        ),
    }


def balanced_wakeup(
    wing: Optional[str] = None,
    budget_tokens: int = 900,
    *,
    palace_path: Optional[str] = None,
    identity_path: Optional[str] = None,
    kg_path: Optional[str] = None,
) -> WakeUpOutput:
    """Build a balanced wake-up across nine slots within ``budget_tokens``.

    Slots are packed in priority order (``SLOT_ORDER``). Each slot is first
    capped at its declared ``max_tokens`` from §6.11, then fit into the
    remaining global budget. When the remaining budget cannot hold even the
    slot's ``min_tokens``, the slot is dropped and recorded in
    ``truncated_slots``. When the slot is truncated below its full content,
    it is also recorded in ``truncated_slots`` so callers know the output is
    a budget-constrained view.
    """
    raw = _build_raw_slots(
        wing,
        palace_path=palace_path,
        identity_path=identity_path,
        kg_path=kg_path,
    )

    slots: Dict[str, str] = {}
    truncated: List[str] = []
    used = 0

    for name in SLOT_ORDER:
        text = raw.get(name, "") or ""
        min_tokens, max_tokens = SLOT_LIMITS.get(name, (1, 4096))
        remaining = budget_tokens - used

        # When no budget is left at all, every remaining slot is dropped.
        if remaining <= 0:
            truncated.append(name)
            continue

        # Cap the slot at its declared per-slot max before global budget is
        # applied. This keeps a single slot from monopolizing the budget when
        # the data source emits an enormous string.
        capped = _truncate(text, max_tokens)
        cap_tokens = _tokens(capped)

        if cap_tokens <= remaining:
            # Slot fits; record it whole (modulo per-slot max truncation).
            slots[name] = capped
            used += cap_tokens
            if capped != text:
                truncated.append(name)
            continue

        # Slot does not fit at full size. If the remaining budget is at least
        # the slot's declared min_tokens, keep a truncated version; otherwise
        # drop the slot entirely.
        if remaining >= min_tokens:
            shrunk = _truncate(text, remaining)
            shrunk_tokens = _tokens(shrunk)
            slots[name] = shrunk
            used += shrunk_tokens
            truncated.append(name)
        else:
            truncated.append(name)

    return WakeUpOutput(
        slots=slots,
        tokens_used=min(used, budget_tokens),
        truncated_slots=truncated,
    )


def render_balanced_wakeup(
    wing: Optional[str] = None,
    budget_tokens: int = 900,
    *,
    palace_path: Optional[str] = None,
    identity_path: Optional[str] = None,
    kg_path: Optional[str] = None,
) -> str:
    """Render the wake-up as a markdown-headed concatenation of slots."""
    output = balanced_wakeup(
        wing=wing,
        budget_tokens=budget_tokens,
        palace_path=palace_path,
        identity_path=identity_path,
        kg_path=kg_path,
    )
    return "\n\n".join(f"## {name}\n{text}" for name, text in output.slots.items())
