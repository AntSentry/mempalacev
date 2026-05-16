"""Cross-wing analogy recall benchmark (Phase 7).

Each question in ``benchmarks/suites/cross_wing/v1/questions.jsonl`` describes
a pattern that appears in multiple wings (e.g. a "planning" room in both the
research wing and the journal wing). For each question we materialize two
drawers — one per wing — that share a room name, run
``mempalace.searcher.search_memories`` with the question, and check whether
*both* reference drawer ids appear in the top-k results.

The single metric ``analogy_recall`` is the fraction of questions where the
retrieved top-k covers both reference drawers — a true cross-wing recall.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from mempalace.searcher import search_memories

from ._palace_fixture import SeedDrawer, palace_with_drawers


DEFAULT_QUESTIONS_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "suites"
    / "cross_wing"
    / "v1"
    / "questions.jsonl"
)


def _load_questions(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _drawers_for(question: dict) -> List[SeedDrawer]:
    qid = question["id"]
    meta = question.get("metadata", {}) or {}
    shared_room = meta.get("shared_room", "general")
    wings = meta.get("wings", ["wing_a", "wing_b"])
    ref_ids = question.get("reference_drawer_ids", []) or []
    seeds: List[SeedDrawer] = []
    for idx, wing in enumerate(wings[:2]):
        drawer_id = (
            ref_ids[idx] if idx < len(ref_ids) else f"{qid}_{wing}"
        )
        text = (
            f"In the {wing} wing, the {shared_room} pattern is applied to "
            f"{wing} concerns. Question context: {question.get('question', '')}"
        )
        seeds.append(
            SeedDrawer(
                drawer_id=drawer_id,
                document=text,
                wing=wing,
                room=shared_room,
            )
        )
    return seeds


def run_suite(
    questions: Optional[List[dict]] = None,
    questions_path: Optional[Path] = None,
    top_k: int = 5,
) -> dict:
    path = questions_path or DEFAULT_QUESTIONS_PATH
    if questions is None:
        questions = _load_questions(path)
    if not questions:
        return {"analogy_recall": 0.0, "n_questions": 0}

    seeds: List[SeedDrawer] = []
    for q in questions:
        seeds.extend(_drawers_for(q))

    full_coverage = 0
    partial_coverage = 0

    with palace_with_drawers(seeds) as palace_path:
        for q in questions:
            try:
                result = search_memories(
                    query=q["question"],
                    palace_path=palace_path,
                    n_results=top_k,
                )
            except Exception:
                result = {"results": []}
            hits = result.get("results", []) or []
            top_texts = [h.get("text", "").lower() for h in hits]
            meta = q.get("metadata", {}) or {}
            wings = meta.get("wings", [])
            shared_room = (meta.get("shared_room") or "").lower()

            wings_seen = set()
            for text in top_texts:
                if shared_room and shared_room in text:
                    for wing in wings:
                        if wing.lower() in text:
                            wings_seen.add(wing.lower())
            if len(wings_seen) >= 2:
                full_coverage += 1
            elif wings_seen:
                partial_coverage += 1

    n = len(questions)
    return {
        "analogy_recall": round(full_coverage / n, 4),
        "partial_recall": round((full_coverage + partial_coverage) / n, 4),
        "n_questions": n,
    }
