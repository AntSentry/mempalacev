"""MemBench adapter (scaffold).

Expected JSONL schema:

.. code-block:: json

    {
      "id": "mb-001",
      "question": "Which movie did the user mention in session 3?",
      "expected_drawer_ids": ["drawer_movie_inception"],
      "metadata": {
        "category": "movie",
        "session": 3
      }
    }

MemBench scores recall_at_5 as its primary metric. The score dict
returns ``recall_at_5`` and ``mrr`` for parity with the other
adapters; downstream tooling treats ``recall_at_5`` as primary.
"""

from __future__ import annotations

from typing import Dict, Iterable, Sequence

from ..metrics import mrr, recall_at_k
from .base import BenchmarkAdapter, BenchmarkQuestion, iter_jsonl, normalize_drawer_ids


class MemBenchAdapter(BenchmarkAdapter):
    """Adapter for the MemBench memory-retrieval benchmark."""

    name = "membench"

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
        return {
            "recall_at_5": float(recall_at_k(retrieved_list, relevant, 5)),
            "mrr": float(mrr(retrieved_list, relevant)),
        }
