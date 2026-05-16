"""LoCoMo adapter (scaffold).

Expected JSONL schema (one object per line) — based on the public
LoCoMo conversational long-memory benchmark (Maharana et al., 2024):

.. code-block:: json

    {
      "id": "loco-001",
      "question": "Where did Alice say she was traveling next month?",
      "expected_drawer_ids": ["drawer_alice_paris", "drawer_alice_april"],
      "metadata": {
        "category": "multi_hop",
        "hops": ["drawer_alice_paris", "drawer_alice_april"],
        "expected_temporal": "2026-04",
        "predicted_temporal": null
      }
    }

LoCoMo emphasises multi-hop reasoning across long sessions and
temporal-reasoning over event timelines. The per-question score dict
includes ``recall_at_5``, ``mrr``, ``multi_hop_success`` (1.0 if every
hop in ``metadata.hops`` appears in the retrieved list, else 0.0), and
``temporal_success`` (1.0 if ``metadata.predicted_temporal`` matches
``metadata.expected_temporal``, else 0.0). Until the real LoCoMo JSONL
is available, the predicted_temporal field is absent and
``temporal_success`` is reported as 0.0.
"""

from __future__ import annotations

from typing import Dict, Iterable, Sequence

from ..metrics import mrr, multi_hop_success, recall_at_k, temporal_success
from .base import BenchmarkAdapter, BenchmarkQuestion, iter_jsonl, normalize_drawer_ids


class LoCoMoAdapter(BenchmarkAdapter):
    """Adapter for the LoCoMo conversational long-memory benchmark."""

    name = "locomo"

    def load_split(self, split_path: str) -> Iterable[BenchmarkQuestion]:
        for row in iter_jsonl(split_path):
            yield BenchmarkQuestion(
                question_id=str(row.get("id") or row.get("question_id") or ""),
                text=str(row.get("question") or row.get("text") or ""),
                relevant_drawer_ids=normalize_drawer_ids(
                    row.get("expected_drawer_ids") or row.get("relevant_drawer_ids")
                ),
                metadata=dict(row.get("metadata") or {}),
            )

    def score(
        self, question: BenchmarkQuestion, retrieved: Sequence[str]
    ) -> Dict[str, float]:
        retrieved_list = list(retrieved)
        relevant = list(question.relevant_drawer_ids)
        meta = question.metadata or {}
        required_hops = list(meta.get("hops") or [])
        # Multi-hop success only meaningful when the question actually
        # specifies a hop chain; otherwise we report 0.0 so the metric
        # has a stable shape across rows.
        if required_hops:
            multi_hop = 1.0 if multi_hop_success(retrieved_list, required_hops) else 0.0
        else:
            multi_hop = 0.0
        expected_temporal = meta.get("expected_temporal")
        predicted_temporal = meta.get("predicted_temporal")
        if expected_temporal is not None and predicted_temporal is not None:
            temporal = (
                1.0
                if temporal_success(predicted_temporal, expected_temporal)
                else 0.0
            )
        else:
            temporal = 0.0
        return {
            "recall_at_5": float(recall_at_k(retrieved_list, relevant, 5)),
            "mrr": float(mrr(retrieved_list, relevant)),
            "multi_hop_success": multi_hop,
            "temporal_success": temporal,
        }
