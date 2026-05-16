"""Contradiction-detection benchmark (Phase 7 / spec §6.10).

For each seed in ``benchmarks/suites/contradiction/v1/seeds.jsonl`` we
materialize the two conflicting triples into a fresh KG sqlite, run
``mempalace/graph/contradiction.py::find_contradictions``, and check whether
the seed pair appears in the returned set. F1 is computed against the gold
contradiction set declared in the seed file.

The suite is dataset-driven — the runner does not bake in any seed data —
so curating new contradiction cases is a JSONL edit, no code change.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional

from mempalace.graph.contradiction import find_contradictions
from mempalace.knowledge_graph import KnowledgeGraph

from .metrics import f1


DEFAULT_SEEDS_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "suites"
    / "contradiction"
    / "v1"
    / "seeds.jsonl"
)


def _load_seeds(path: Path) -> List[dict]:
    if not path.exists():
        return []
    seeds = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        seeds.append(json.loads(line))
    return seeds


def _gold_pair_key(subject: str, predicate: str, objects: Iterable[str]) -> tuple:
    """Canonical (lowercase, sorted) key for a contradictory subject/predicate/objects triple."""
    obj_a, obj_b = sorted(o.lower().replace(" ", "_") for o in objects)
    return (
        subject.lower().replace(" ", "_"),
        predicate.lower().replace(" ", "_"),
        obj_a,
        obj_b,
    )


def _detected_pair_key(contradiction) -> tuple:
    obj_a, obj_b = sorted([contradiction.first_object, contradiction.second_object])
    return (
        contradiction.subject,
        contradiction.predicate,
        obj_a,
        obj_b,
    )


def _materialize_seed(kg_path: str, seed: dict) -> None:
    """Insert both conflicting triples into the KG so find_contradictions sees them."""
    subject = seed["subject"]
    predicate = seed["predicate"]
    objects = seed.get("objects", [])
    meta = seed.get("metadata", {})
    valid_froms = meta.get("valid_from", [None] * len(objects))
    polarities = meta.get("polarity", [1] * len(objects))

    kg = KnowledgeGraph(db_path=kg_path)
    try:
        for obj, vf in zip(objects, valid_froms):
            kg.add_triple(subject, predicate, obj, valid_from=vf)
    finally:
        kg.close()

    # Set polarity directly — KnowledgeGraph.add_triple doesn't accept it,
    # but the contradiction suite needs the raw column populated.
    conn = sqlite3.connect(kg_path)
    try:
        conn.execute("ALTER TABLE triples ADD COLUMN polarity INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        # Column already exists (added by ensure_gap_schema or a prior seed).
        pass
    sub_id = subject.lower().replace(" ", "_")
    pred = predicate.lower().replace(" ", "_")
    for obj, pol in zip(objects, polarities):
        obj_id = obj.lower().replace(" ", "_")
        conn.execute(
            "UPDATE triples SET polarity=? WHERE subject=? AND predicate=? AND object=?",
            (int(pol), sub_id, pred, obj_id),
        )
    conn.commit()
    conn.close()


def run_suite(seeds: Optional[List[dict]] = None, seeds_path: Optional[Path] = None) -> dict:
    """Run the contradiction benchmark and return metric dict.

    Returns: ``{"contradiction_f1": float, "n_seeds": int, "detected": int,
    "missed": int}``. When the seed file is missing or empty, every metric is
    zero — the suite never raises, so the ablation runner can include it in
    every row without conditional checks.
    """
    path = seeds_path or DEFAULT_SEEDS_PATH
    if seeds is None:
        seeds = _load_seeds(path)
    if not seeds:
        return {"contradiction_f1": 0.0, "n_seeds": 0, "detected": 0, "missed": 0}

    gold_keys: List[tuple] = []
    predicted_keys: List[tuple] = []

    for seed in seeds:
        if len(seed.get("objects", [])) < 2:
            continue
        gold_keys.append(
            _gold_pair_key(seed["subject"], seed["predicate"], seed["objects"])
        )

        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as tmp:
            kg_path = tmp.name
        try:
            _materialize_seed(kg_path, seed)
            polarities = seed.get("metadata", {}).get("polarity", [])
            polarity_required = (
                len(polarities) >= 2 and polarities[0] != polarities[1]
            )
            conn = sqlite3.connect(kg_path)
            conn.row_factory = sqlite3.Row
            try:
                contradictions = find_contradictions(
                    conn, polarity_required=polarity_required
                )
            finally:
                conn.close()
        finally:
            Path(kg_path).unlink(missing_ok=True)

        for c in contradictions:
            predicted_keys.append(_detected_pair_key(c))

    score = f1(predicted_keys, gold_keys)
    detected = len(set(predicted_keys) & set(gold_keys))
    missed = len(set(gold_keys) - set(predicted_keys))
    return {
        "contradiction_f1": round(score, 4),
        "n_seeds": len(gold_keys),
        "detected": detected,
        "missed": missed,
    }
