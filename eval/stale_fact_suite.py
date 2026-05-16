"""Stale-fact accuracy benchmark (Phase 7).

Each question in ``benchmarks/suites/stale_fact/v1/questions.jsonl`` carries
two drawers' worth of information: the *current* answer and the
*historical* answer. We materialize both into an ephemeral palace, query
``mempalace.searcher.search_memories`` with the question, and score the
top-k result against the expected answers.

Three metrics are produced:

* ``current_fact_accuracy`` — fraction of questions whose top hit contains
  the current answer string.
* ``historical_fact_accuracy`` — fraction of questions whose top-k results
  *also* contain the historical answer (it must be retrievable on demand,
  even when the current answer wins the top slot).
* ``stale_served_rate`` — fraction of questions whose top hit is the
  *historical* (stale) answer despite a current answer existing. This is
  the failure mode the gap-graph is supposed to suppress.

The suite is dataset-driven; curating new cases is a JSONL edit. Real
public benchmarks (LongMemEval, LoCoMo) are deferred until their datasets
land locally — those will reuse the same metrics module.
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
    / "stale_fact"
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
    """Two drawers per question — historical first, current second.

    The wing and room are derived from the question's metadata.subject so
    every question's drawers share a logical home, which keeps the palace
    realistic when the cross-wing suite is run on the same fixture.
    """
    qid = question["id"]
    meta = question.get("metadata", {}) or {}
    subj = (meta.get("subject") or "general").lower().replace(" ", "_")
    pred = (meta.get("predicate") or "state").lower().replace(" ", "_")
    ref_ids = question.get("reference_drawer_ids", []) or []
    historical_id = ref_ids[1] if len(ref_ids) > 1 else f"{qid}_historical"
    current_id = ref_ids[0] if len(ref_ids) > 0 else f"{qid}_current"

    historical_text = (
        f"Historical note about {subj}: previously the {pred} was "
        f"{question.get('historical_answer', '')}. "
        f"Context: {question.get('question', '')}"
    )
    current_text = (
        f"Current state of {subj}: the {pred} is now "
        f"{question.get('current_answer', '')}. "
        f"Context: {question.get('question', '')}"
    )
    return [
        SeedDrawer(
            drawer_id=historical_id,
            document=historical_text,
            wing=subj,
            room="history",
            extra_metadata={"is_current": False},
        ),
        SeedDrawer(
            drawer_id=current_id,
            document=current_text,
            wing=subj,
            room="current",
            extra_metadata={"is_current": True},
        ),
    ]


def run_suite(
    questions: Optional[List[dict]] = None,
    questions_path: Optional[Path] = None,
    top_k: int = 5,
) -> dict:
    """Run the stale-fact suite end-to-end and return metrics."""
    path = questions_path or DEFAULT_QUESTIONS_PATH
    if questions is None:
        questions = _load_questions(path)
    if not questions:
        return {
            "current_fact_accuracy": 0.0,
            "historical_fact_accuracy": 0.0,
            "stale_served_rate": 0.0,
            "n_questions": 0,
        }

    seeds: List[SeedDrawer] = []
    for q in questions:
        seeds.extend(_drawers_for(q))

    current_hits = 0
    historical_hits = 0
    stale_served = 0

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
            top_text = (hits[0].get("text", "").lower() if hits else "")
            all_text = " ".join(h.get("text", "").lower() for h in hits)

            current_ans = (q.get("current_answer") or "").lower()
            hist_ans = (q.get("historical_answer") or "").lower()

            if current_ans and current_ans in top_text:
                current_hits += 1
            if hist_ans and hist_ans in all_text:
                historical_hits += 1
            if current_ans and hist_ans and hist_ans in top_text and current_ans not in top_text:
                stale_served += 1

    n = len(questions)
    return {
        "current_fact_accuracy": round(current_hits / n, 4),
        "historical_fact_accuracy": round(historical_hits / n, 4),
        "stale_served_rate": round(stale_served / n, 4),
        "n_questions": n,
    }
