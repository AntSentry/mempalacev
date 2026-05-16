"""LongMemEval adapter (scaffold).

Expected JSONL schema (one object per line) — based on the public
LongMemEval format (Wu et al., 2024) and the project's local
``benchmarks/data/dev_split.jsonl`` shape:

.. code-block:: json

    {
      "id": "lme-001",
      "question": "What is the user's current role at Acme?",
      "expected_drawer_ids": ["drawer_alex_staff"],
      "metadata": {
        "category": "single_session_user",
        "session_id": "s_42",
        "difficulty": "easy"
      }
    }

LongMemEval categories: ``single_session_user``, ``single_session_assistant``,
``multi_session``, ``temporal_reasoning``, ``knowledge_update``,
``abstention``. The category is preserved in ``metadata`` so downstream
analyses can stratify recall by category — the per-question metric dict
exposes ``recall_at_5`` and ``mrr``.
"""

from __future__ import annotations

from typing import Dict, Iterable, Sequence

from ..metrics import mrr, recall_at_k
from .base import BenchmarkAdapter, BenchmarkQuestion, iter_jsonl, normalize_drawer_ids


class LongMemEvalAdapter(BenchmarkAdapter):
    """Adapter for the LongMemEval public benchmark."""

    name = "longmemeval"

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
