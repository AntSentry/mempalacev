"""Tests for the public benchmark adapter scaffolds.

These adapters are the seam through which Phase 8 will run real public
benchmarks (LongMemEval, LoCoMo, ConvoMem, MemBench). The real datasets
are license-restricted and not committed; the adapters are exercised
end-to-end against a small synthetic JSONL fixture so the wiring stays
correct. Quality numbers from these tests are not retrieval claims —
the claim ledger keeps benchmark-supported claims experimental until
real data lands.
"""

from __future__ import annotations

import json

import pytest

from eval.adapters import (
    BenchmarkQuestion,
    ConvoMemAdapter,
    LoCoMoAdapter,
    LongMemEvalAdapter,
    MemBenchAdapter,
    get_adapter,
    list_adapters,
)


SYNTHETIC_ROWS = [
    {
        "id": "syn-001",
        "question": "What database does the auth service use?",
        "expected_drawer_ids": ["drawer_auth_pg16"],
        "metadata": {"category": "preference"},
    },
    {
        "id": "syn-002",
        "question": "Where did Alice say she was traveling?",
        "expected_drawer_ids": ["drawer_alice_paris", "drawer_alice_april"],
        "metadata": {
            "category": "multi_hop",
            "hops": ["drawer_alice_paris", "drawer_alice_april"],
            "expected_temporal": "2026-04",
            "predicted_temporal": "2026-04",
        },
    },
    {
        "id": "syn-003",
        "question": "Which framework does the frontend use?",
        "expected_drawer_ids": ["drawer_fe_svelte"],
        "metadata": {"category": "event"},
    },
]


@pytest.fixture
def synthetic_split(tmp_path):
    path = tmp_path / "synthetic.jsonl"
    path.write_text(
        "\n".join(json.dumps(row) for row in SYNTHETIC_ROWS) + "\n",
        encoding="utf-8",
    )
    return str(path)


@pytest.mark.parametrize(
    "adapter",
    [
        LongMemEvalAdapter(),
        LoCoMoAdapter(),
        ConvoMemAdapter(),
        MemBenchAdapter(),
    ],
)
def test_adapter_loads_synthetic_jsonl(adapter, synthetic_split):
    questions = list(adapter.load_split(synthetic_split))
    assert len(questions) == 3
    assert all(isinstance(q, BenchmarkQuestion) for q in questions)
    assert questions[0].question_id == "syn-001"
    assert list(questions[0].relevant_drawer_ids) == ["drawer_auth_pg16"]


def test_longmemeval_score_returns_expected_keys(synthetic_split):
    adapter = LongMemEvalAdapter()
    q = next(iter(adapter.load_split(synthetic_split)))
    metrics = adapter.score(q, list(q.relevant_drawer_ids))
    assert set(metrics) == {"recall_at_5", "mrr"}
    for value in metrics.values():
        assert isinstance(value, float)


def test_locomo_score_includes_multi_hop_and_temporal(synthetic_split):
    adapter = LoCoMoAdapter()
    questions = list(adapter.load_split(synthetic_split))
    multi_hop_q = questions[1]
    metrics = adapter.score(multi_hop_q, list(multi_hop_q.relevant_drawer_ids))
    assert {
        "recall_at_5",
        "mrr",
        "multi_hop_success",
        "temporal_success",
    } <= set(metrics)
    # Both hops were retrieved and predicted_temporal == expected_temporal.
    assert metrics["multi_hop_success"] == 1.0
    assert metrics["temporal_success"] == 1.0


def test_locomo_score_handles_missing_temporal_fields(synthetic_split):
    adapter = LoCoMoAdapter()
    q = BenchmarkQuestion(
        question_id="x",
        text="t",
        relevant_drawer_ids=["d1"],
        metadata={},
    )
    metrics = adapter.score(q, ["d1"])
    assert metrics["multi_hop_success"] == 0.0
    assert metrics["temporal_success"] == 0.0


def test_convomem_score_includes_category_recall_key(synthetic_split):
    adapter = ConvoMemAdapter()
    q = next(iter(adapter.load_split(synthetic_split)))
    metrics = adapter.score(q, list(q.relevant_drawer_ids))
    assert "recall_at_5" in metrics
    assert "recall_preference" in metrics
    assert all(isinstance(v, float) for v in metrics.values())


def test_membench_score_returns_recall_and_mrr(synthetic_split):
    adapter = MemBenchAdapter()
    q = next(iter(adapter.load_split(synthetic_split)))
    metrics = adapter.score(q, list(q.relevant_drawer_ids))
    assert set(metrics) == {"recall_at_5", "mrr"}


def test_unknown_adapter_name_raises_clear_error():
    with pytest.raises(KeyError) as exc_info:
        get_adapter("does_not_exist")
    msg = str(exc_info.value)
    assert "does_not_exist" in msg
    assert "known adapters" in msg


def test_list_adapters_contains_four_scaffolds():
    assert set(list_adapters()) == {"longmemeval", "locomo", "convomem", "membench"}
