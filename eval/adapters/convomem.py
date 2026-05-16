"""ConvoMem adapter (scaffold).

Expected JSONL schema:

.. code-block:: json

    {
      "id": "cm-001",
      "question": "What restaurant did the user say they liked?",
      "expected_drawer_ids": ["drawer_food_pref_sushi"],
      "metadata": {
        "category": "preference",
        "turn_id": 14
      }
    }

ConvoMem groups questions by a small set of conversational categories
(``preference``, ``persona``, ``event``, ``commitment``). The score
dict reports ``recall_at_5`` plus a per-category recall stamp so the
aggregator in :mod:`eval.ablations` can stratify when needed; here the
category is encoded by the metric key suffix (e.g. ``recall_preference``).
"""

from __future__ import annotations

from typing import Dict, Iterable, Sequence

from ..metrics import mrr, recall_at_k
from .base import BenchmarkAdapter, BenchmarkQuestion, iter_jsonl, normalize_drawer_ids


class ConvoMemAdapter(BenchmarkAdapter):
    """Adapter for the ConvoMem conversational memory benchmark."""

    name = "convomem"

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
        recall = float(recall_at_k(retrieved_list, relevant, 5))
        category = (question.metadata or {}).get("category") or "uncategorized"
        # Sanitize category to a metric-safe key segment.
        safe = "".join(c if (c.isalnum() or c == "_") else "_" for c in str(category))
        return {
            "recall_at_5": recall,
            "mrr": float(mrr(retrieved_list, relevant)),
            f"recall_{safe}": recall,
        }
