"""Tests for the nine-slot balanced wake-up (Phase 6 / spec §6.11).

These tests build a full mini-palace fixture: knowledge graph triples, a
gap event in the ``open`` state, a gap event in the ``superseded`` state, a
diary drawer, a decision-tagged drawer, and a cross-wing tunnel (a room name
shared by two wings). Each slot is then asserted to surface its seeded data
or — when the source is intentionally empty — the friendly empty placeholder.

The runner's budget and priority-truncation semantics are exercised on the
same fixture so the budget tests reflect real slot sizes, not stubs.
"""

from __future__ import annotations

import sqlite3

import chromadb
import pytest

from mempalace.graph.gap_graph import (
    ensure_gap_schema,
    open_gap_event,
)
from mempalace.knowledge_graph import KnowledgeGraph
from mempalace.memory_stack.l1_balanced_wakeup import (
    SLOT_LIMITS,
    SLOT_ORDER,
    balanced_wakeup,
)


@pytest.fixture
def palace_kg_paths(tmp_path):
    """Return a (palace_path, identity_path, kg_path) triple, all empty."""
    palace = tmp_path / "palace"
    palace.mkdir()
    identity = tmp_path / "identity.txt"
    kg_db = tmp_path / "kg.sqlite3"
    return str(palace), str(identity), str(kg_db)


@pytest.fixture
def seeded_wakeup(palace_kg_paths):
    """Seed every slot's data source so balanced_wakeup has something to find.

    Returns the (palace_path, identity_path, kg_path) triple along with the
    seeded gap event ids so tests can transition state without re-querying.
    """
    palace_path, identity_path, kg_path = palace_kg_paths

    # L0 identity — the source slot_identity_anchor reads.
    with open(identity_path, "w", encoding="utf-8") as fh:
        fh.write(
            "I am Atlas, working memory for the principal.\n"
            "Wing: research. Style: direct, verbatim, local-first.\n"
        )

    # Knowledge-graph triples covering active_projects, current_preferences,
    # current_constraints. Each predicate populates its own slot.
    kg = KnowledgeGraph(db_path=kg_path)
    kg.add_triple("principal", "works_on", "MemPalaceV", valid_from="2026-01-01")
    kg.add_triple("principal", "works_on", "Topology Layer", valid_from="2026-03-01")
    kg.add_triple("principal", "prefers", "TypeScript over Python", valid_from="2026-01-01")
    kg.add_triple("principal", "prefers", "verbatim storage", valid_from="2026-02-01")
    kg.add_triple("principal", "constrained_by", "local-first only", valid_from="2026-01-01")
    kg.close()

    # Gap events — one open, one superseded. open_gap_event writes the
    # supersession row; we then transition the second one to ``superseded``
    # so stale_to_avoid surfaces it.
    conn = sqlite3.connect(kg_path)
    conn.row_factory = sqlite3.Row
    ensure_gap_schema(conn)
    # Seed a triple row so foreign-key checks pass and gap_event has a
    # triggering triple to point at.
    conn.execute(
        "INSERT OR IGNORE INTO triples (id, subject, predicate, object, valid_from) "
        "VALUES (?, 'principal', 'current_role', 'engineer', '2025-01-01')",
        ("t_role_old",),
    )
    conn.execute(
        "INSERT OR IGNORE INTO triples (id, subject, predicate, object, valid_from) "
        "VALUES (?, 'principal', 'current_role', 'staff_engineer', '2026-04-01')",
        ("t_role_new",),
    )
    open_id = open_gap_event(
        conn,
        subject_id="principal",
        predicate="lives_in",
        old_object="boston",
        new_object="austin",
        old_drawer_id="drawer_loc_old",
        new_drawer_id="drawer_loc_new",
        triggered_by_triple_id="t_role_new",
        detected_by="test_fixture",
        valid_from="2026-04-01",
    )
    superseded_id = open_gap_event(
        conn,
        subject_id="principal",
        predicate="current_role",
        old_object="engineer",
        new_object="staff_engineer",
        old_drawer_id="drawer_role_old",
        new_drawer_id="drawer_role_new",
        triggered_by_triple_id="t_role_new",
        detected_by="test_fixture",
        valid_from="2026-04-01",
    )
    conn.commit()
    conn.close()

    # Transition the second one to 'superseded' (via the seeded state machine
    # — the 'open -> resolved -> superseded' path requires evidence).
    conn = sqlite3.connect(kg_path)
    conn.row_factory = sqlite3.Row
    ensure_gap_schema(conn)
    # Manual update — the state machine doesn't expose a direct
    # open->superseded transition, but the slot only reads ``status`` so we
    # write it directly. Production transitions ride through
    # transition_gap_event; the slot's contract is "read superseded rows".
    conn.execute(
        "UPDATE gap_events SET status='superseded' WHERE id=?", (superseded_id,)
    )
    conn.commit()
    conn.close()

    # Palace drawers — decision-tagged drawer, diary drawer, and a tunnel
    # (two wings sharing a room name).
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat()
    client = chromadb.PersistentClient(path=palace_path)
    col = client.get_or_create_collection(
        "mempalace_drawers", metadata={"hnsw:space": "cosine"}
    )
    # Pass explicit dummy embeddings so chromadb does NOT invoke its default
    # ONNX embedder — onnxruntime is not always installed in test envs.
    # Slot logic only reads documents/metadatas, never embeddings, so the
    # vector values are irrelevant; they just need to be present.
    docs = [
        "Decided to ship Phase 6 wake-up before Phase 7 ablations. Rationale: gates 7.",
        "Today: wrote balanced wake-up. Tomorrow: ablations.",
        "Promoted to staff engineer effective 2026-04-01.",
        "Planning the topology paper sections.",
        "Planning the personal journal entries for April.",
    ]
    col.add(
        ids=[
            "drawer_decision_1",
            "drawer_diary_today",
            "drawer_role_new",
            "drawer_research_planning",
            "drawer_journal_planning",
        ],
        documents=docs,
        embeddings=[[float(i + 1) * 0.1, 0.2, 0.3] for i in range(len(docs))],
        metadatas=[
            {
                "wing": "research",
                "room": "decisions",
                "source_file": "decisions.md",
                "filed_at": now_iso,
            },
            {
                "wing": "diary",
                "room": "daily",
                "source_file": "2026-05-15.md",
                "filed_at": now_iso,
                "date": "2026-05-15",
            },
            {
                "wing": "principal",
                "room": "roles",
                "source_file": "roles.md",
                "filed_at": now_iso,
            },
            {
                "wing": "research",
                "room": "planning",
                "source_file": "research_plan.md",
                "filed_at": now_iso,
            },
            {
                "wing": "journal",
                "room": "planning",
                "source_file": "journal_plan.md",
                "filed_at": now_iso,
            },
        ],
    )
    # palace_graph caches build results — invalidate so the test sees the
    # freshly-seeded tunnels.
    from mempalace.palace_graph import invalidate_graph_cache

    invalidate_graph_cache()
    del client

    yield {
        "palace_path": palace_path,
        "identity_path": identity_path,
        "kg_path": kg_path,
        "open_gap_id": open_id,
        "superseded_gap_id": superseded_id,
    }


def _wakeup(seeded):
    return balanced_wakeup(
        wing=None,
        budget_tokens=2000,  # generous so every slot fits
        palace_path=seeded["palace_path"],
        identity_path=seeded["identity_path"],
        kg_path=seeded["kg_path"],
    )


def test_budget_enforced():
    """Budget cap is honored even with no seeded data sources."""
    output = balanced_wakeup(budget_tokens=20)
    assert output.tokens_used <= 20


def test_priority_truncation_drops_lowest_priority_first(seeded_wakeup):
    """Spec §6.11 priority semantics: budget pressure drops the lowest-priority
    slot first. With a budget that runs out mid-traversal, the *prefix* of
    SLOT_ORDER is kept and the *suffix* is dropped — never the other way."""
    output = balanced_wakeup(
        budget_tokens=50,
        palace_path=seeded_wakeup["palace_path"],
        identity_path=seeded_wakeup["identity_path"],
        kg_path=seeded_wakeup["kg_path"],
    )
    assert "identity_anchor" in output.slots
    assert output.tokens_used <= 50
    # The retained slots must form a prefix of SLOT_ORDER (no out-of-order
    # keeps). Once a slot is dropped, every lower-priority slot must also be
    # dropped.
    retained = [name for name in SLOT_ORDER if name in output.slots]
    expected_prefix = SLOT_ORDER[: len(retained)]
    assert retained == expected_prefix, (
        f"retained slots {retained} are not a prefix of SLOT_ORDER"
    )
    # And the lowest-priority slots are guaranteed in truncated_slots.
    assert "agent_diary_summaries" in output.truncated_slots
    assert "cross_wing_analogies" in output.truncated_slots


def test_priority_truncation_with_realistic_budget(seeded_wakeup):
    """A 200-token budget keeps the highest-priority slots and truncates the
    lowest. The exact cut point depends on the seeded data size; the
    invariant we hold is monotonic priority — if slot N is in
    ``truncated_slots``, every slot with priority > N is also truncated."""
    output = balanced_wakeup(
        budget_tokens=200,
        palace_path=seeded_wakeup["palace_path"],
        identity_path=seeded_wakeup["identity_path"],
        kg_path=seeded_wakeup["kg_path"],
    )
    assert "identity_anchor" in output.slots
    assert output.tokens_used <= 200
    # Once a slot is truncated, every lower-priority slot must also be
    # truncated (priority monotonicity).
    truncated_indexes = sorted(
        SLOT_ORDER.index(name) for name in output.truncated_slots
        if name in SLOT_ORDER
    )
    if truncated_indexes:
        first_truncated = truncated_indexes[0]
        for idx in range(first_truncated, len(SLOT_ORDER)):
            assert SLOT_ORDER[idx] in output.truncated_slots, (
                f"slot {SLOT_ORDER[idx]} should also be truncated once "
                f"{SLOT_ORDER[first_truncated]} is"
            )


def test_all_nine_slots_present_with_full_budget(seeded_wakeup):
    output = _wakeup(seeded_wakeup)
    assert list(output.slots) == SLOT_ORDER


def test_slot_identity_anchor_reads_identity_file(seeded_wakeup):
    output = _wakeup(seeded_wakeup)
    assert "Atlas" in output.slots["identity_anchor"]


def test_slot_active_projects_returns_kg_works_on_triples(seeded_wakeup):
    output = _wakeup(seeded_wakeup)
    text = output.slots["active_projects"]
    assert "MemPalaceV" in text
    assert "works_on" in text


def test_slot_current_preferences_returns_kg_prefers_triples(seeded_wakeup):
    output = _wakeup(seeded_wakeup)
    text = output.slots["current_preferences"]
    assert "verbatim storage" in text or "TypeScript over Python" in text


def test_slot_current_constraints_returns_kg_constrained_by_triples(seeded_wakeup):
    output = _wakeup(seeded_wakeup)
    text = output.slots["current_constraints"]
    assert "local-first only" in text


def test_slot_recent_decisions_returns_decision_drawer(seeded_wakeup):
    output = _wakeup(seeded_wakeup)
    text = output.slots["recent_decisions"]
    assert "Phase 6" in text or "ship Phase 6" in text


def test_slot_open_gaps_lists_open_gap_events(seeded_wakeup):
    output = _wakeup(seeded_wakeup)
    text = output.slots["open_gaps"]
    # The lives_in gap is open; current_role is superseded.
    assert "lives_in" in text
    assert "boston" in text or "austin" in text
    assert "current_role" not in text


def test_slot_stale_to_avoid_lists_superseded_gap_events(seeded_wakeup):
    output = _wakeup(seeded_wakeup)
    text = output.slots["stale_to_avoid"]
    assert "current_role" in text
    assert "staff_engineer" in text
    # And does NOT contain the open gap subject pair.
    assert "lives_in" not in text


def test_slot_cross_wing_analogies_returns_tunnel(seeded_wakeup):
    output = _wakeup(seeded_wakeup)
    text = output.slots["cross_wing_analogies"]
    # 'planning' room is shared between 'research' and 'journal' wings.
    assert "planning" in text


def test_slot_agent_diary_summaries_returns_diary_drawer(seeded_wakeup):
    output = _wakeup(seeded_wakeup)
    text = output.slots["agent_diary_summaries"]
    assert "balanced wake-up" in text or "Today" in text


def test_empty_palace_returns_friendly_placeholders(palace_kg_paths):
    """A brand-new palace yields no real data — every slot must still render
    a placeholder so the wake-up always returns the full nine slots."""
    palace_path, identity_path, kg_path = palace_kg_paths
    output = balanced_wakeup(
        budget_tokens=2000,
        palace_path=palace_path,
        identity_path=identity_path,
        kg_path=kg_path,
    )
    assert list(output.slots) == SLOT_ORDER
    for name, text in output.slots.items():
        assert text.startswith("no "), f"slot {name!r} did not return friendly empty: {text!r}"


def test_slot_limits_match_spec():
    """Every slot has spec §6.11 (min_tokens, max_tokens); none missing."""
    assert set(SLOT_LIMITS) == set(SLOT_ORDER)
    for name, (mn, mx) in SLOT_LIMITS.items():
        assert mn > 0 and mx >= mn, f"bad limits for {name}: ({mn}, {mx})"
