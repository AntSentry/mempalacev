"""Tests for the Phase 7 ablation runner.

The stub runner returned a hardcoded ``recall_at_5: 0.0`` regardless of row.
The real runner sets feature flags per row and invokes a seeded mock
benchmark via ``mempalace.searcher.search_memories``. These tests assert
the runner: (a) covers all nine rows, (b) actually invokes retrieval (so
``n_questions`` is non-zero), (c) produces row-distinct result dicts, and
(d) writes JSONL results + a manifest.

The retrieval-quality numbers may not differ across rows on this tiny dev
split — the goal of this test layer is *infrastructure correctness*, not
benchmark-grade comparison. Quality claims stay ``experimental`` in the
claim ledger until real benchmark evidence ships.
"""

from __future__ import annotations

import json

import pytest
import yaml

from eval import ablations as ablations_mod
from eval.ablations import (
    ABLATION_ROWS,
    main as ablations_main,
    run_ablation,
    run_full_matrix,
)
from eval.run_manifest import dataset_sha


def test_ablation_rows_present():
    assert set(ABLATION_ROWS) == {f"A{i}" for i in range(9)}


def test_run_ablation_returns_result_with_metrics():
    result = run_ablation("A0")
    assert result["row"] == "A0"
    assert "metrics" in result
    metrics = result["metrics"]
    # The mock benchmark must have actually run — n_questions > 0 means the
    # dev split JSONL was found and retrieval was invoked.
    assert metrics.get("n_questions", 0) > 0, (
        "ablation runner did not invoke retrieval; "
        "benchmarks/data/dev_split.jsonl may be missing"
    )


def test_a0_a1_a8_produce_distinct_result_dicts():
    """Each row sets a different flag set; the result dicts must differ.

    The substantive difference is in the ``flags`` field — A0 has no flags,
    A1 has fusion on, A8 has all four flags on. Metrics may coincidentally
    match across rows on this tiny dev split, but the flag dict alone
    guarantees distinct result dicts.
    """
    a0 = run_ablation("A0")
    a1 = run_ablation("A1")
    a8 = run_ablation("A8")
    assert a0["flags"] == {}
    assert a1["flags"] == {"MEMPALACE_ENABLE_FUSION": "1"}
    assert "MEMPALACE_ENABLE_BALANCED_WAKEUP" in a8["flags"]
    assert a0 != a1
    assert a1 != a8
    assert a0 != a8


def test_run_ablation_restores_environment(monkeypatch):
    """Flags set during a row must not leak into the parent environment."""
    monkeypatch.delenv("MEMPALACE_ENABLE_FUSION", raising=False)
    assert "MEMPALACE_ENABLE_FUSION" not in os_env()
    run_ablation("A1")
    assert "MEMPALACE_ENABLE_FUSION" not in os_env()


def test_run_full_matrix_writes_results_and_manifest(tmp_path):
    result = run_full_matrix(rows=["A0", "A1"], output_dir=str(tmp_path))
    assert "A0" in result and "A1" in result
    assert (tmp_path / "mock_A0.jsonl").exists()
    assert (tmp_path / "mock_A1.jsonl").exists()
    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["configuration"]["set"] == "validation"
    assert manifest["configuration"]["rows"] == ["A0", "A1"]


def test_jsonl_row_payload_has_real_metrics(tmp_path):
    run_full_matrix(rows=["A0"], output_dir=str(tmp_path))
    rows = (tmp_path / "mock_A0.jsonl").read_text().splitlines()
    assert rows, "result jsonl should not be empty"
    payload = json.loads(rows[0])
    assert payload["row"] == "A0"
    metrics = payload["metrics"]
    assert metrics["n_questions"] > 0
    # recall_at_5 may be 0.0 on this tiny seeded palace; we only require
    # the metric to be present (real, not a stub).
    assert "recall_at_5" in metrics
    assert "mrr" in metrics


def os_env():
    """Helper — separated so it stays a function (monkeypatch resets env)."""
    import os

    return os.environ


# ---------------------------------------------------------------------------
# Seal protocol + dataset_sha helper (Phase 8 release-readiness scaffolding)
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_seal_env(tmp_path, monkeypatch):
    """Isolate contamination log + test split file from real repo state.

    The seal protocol writes to ``mempalace/evidence/contamination_log.yaml``
    and reads a sealed split path under ``benchmarks/data/<benchmark>/``.
    Tests redirect both into ``tmp_path`` and pin a fake commit SHA so
    runs are reproducible.
    """
    fake_log = tmp_path / "contamination_log.yaml"
    fake_log.write_text("sets: []\n", encoding="utf-8")

    test_split = tmp_path / "test_split.jsonl"
    test_split.write_text(
        '{"id":"t-1","question":"q?","expected_drawer_ids":["drawer_x"],"metadata":{}}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(ablations_mod, "CONTAMINATION_LOG_PATH", fake_log)
    monkeypatch.setattr(ablations_mod, "_git_head_sha", lambda: "deadbeefcafe")
    monkeypatch.setattr(
        ablations_mod, "_resolve_split_path", lambda set_name, benchmark: test_split
    )
    # Avoid actually running the heavyweight matrix in seal tests; the
    # protocol logic is what's under test, not retrieval.
    monkeypatch.setattr(
        ablations_mod, "run_full_matrix", lambda *a, **kw: {"A0": []}
    )
    return {"log": fake_log, "split": test_split}


def test_dataset_sha_deterministic(tmp_path):
    f = tmp_path / "split.jsonl"
    f.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
    assert dataset_sha(f) == dataset_sha(f)
    g = tmp_path / "other.jsonl"
    g.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
    assert dataset_sha(f) == dataset_sha(g)
    g.write_text('{"a":1}\n{"b":3}\n', encoding="utf-8")
    assert dataset_sha(f) != dataset_sha(g)


def test_dataset_sha_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        dataset_sha(tmp_path / "nope.jsonl")


def test_seal_refuses_repeat_with_same_dataset_sha(isolated_seal_env, capsys):
    # First sealed run succeeds and appends a contamination entry.
    ablations_main(["--set", "test", "--rows", "A0", "--seal"])
    log = yaml.safe_load(isolated_seal_env["log"].read_text())
    assert len(log["sets"]) == 1
    entry = log["sets"][0]
    assert entry["marker"] == "sealed"
    assert entry["commit_sha"] == "deadbeefcafe"
    assert entry["set"] == "test"

    # Second run with same commit + same dataset must refuse.
    with pytest.raises(SystemExit) as exc_info:
        ablations_main(["--set", "test", "--rows", "A0", "--seal"])
    msg = str(exc_info.value)
    assert "prior contamination entry" in msg
    assert "deadbeefcafe" in msg


def test_unseal_emergency_requires_long_reason(isolated_seal_env):
    # Seed a prior entry so the override path is exercised.
    ablations_main(["--set", "test", "--rows", "A0", "--seal"])

    # Short reason rejected.
    with pytest.raises(SystemExit) as exc_info:
        ablations_main(
            [
                "--set", "test", "--rows", "A0", "--seal",
                "--unseal-emergency", "too short",
            ]
        )
    assert "at least" in str(exc_info.value)

    # Long reason (>= 40 chars) accepted; entry recorded with reason.
    long_reason = "Operator approved re-run after dataset corruption discovery on 2026-05-15."
    assert len(long_reason) >= 40
    ablations_main(
        [
            "--set", "test", "--rows", "A0", "--seal",
            "--unseal-emergency", long_reason,
        ]
    )
    log = yaml.safe_load(isolated_seal_env["log"].read_text())
    assert len(log["sets"]) == 2
    last = log["sets"][-1]
    assert last["unseal_emergency"] is True
    assert last["unseal_reason"] == long_reason
    assert last["supersedes_timestamp"] == log["sets"][0]["timestamp"]


def test_unseal_emergency_without_seal_rejected(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        ablations_main(
            ["--set", "validation", "--unseal-emergency", "x" * 50]
        )
    assert "requires --seal" in str(exc_info.value)


def test_seal_only_valid_for_test_set(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        ablations_main(["--set", "validation", "--seal"])
    assert "test set" in str(exc_info.value)
