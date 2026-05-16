"""Tests for the RFC T3c learned RRF route weights.

Covers:
- ``fit_route_weights`` on synthetic data: one perfect route + one noisy
  route — the perfect route's weight should converge above the noisy
  route's.
- Weights bounded ``[0.1, 5.0]``.
- save/load round-trip.
- Loader returns uniform (``{}``) when the file is missing or the flag
  is off.
"""

from __future__ import annotations

import json

from mempalace.retrieval.fusion import (
    WEIGHT_BOUND_HIGH,
    WEIGHT_BOUND_LOW,
    fit_route_weights,
)
from mempalace.retrieval.weight_loader import (
    load_route_weights,
    save_route_weights,
)


def _perfect_route(query: str) -> list[str]:
    # Always ranks the relevant doc first. No actively-misleading entries.
    return [f"zrel_{query}", "filler_a", "filler_b"]


def _noisy_route(query: str) -> list[str]:
    # Lies — always ranks a wrong doc first. Note: ``a_wrong`` sorts
    # alphabetically BEFORE ``zrel_qN`` so at uniform RRF weights the
    # wrong doc wins the score-tie via the drawer_id tiebreaker. The
    # fitter must learn to up-weight perfect to break that tie.
    return [f"a_wrong_{query}", "filler_c", "filler_d"]


def test_fit_perfect_route_wins_over_noisy_route(monkeypatch):
    # Flag does NOT need to be on for the fitter itself — only for the
    # loader. The fitter is a pure function.
    train_pairs = [
        (f"q{i}", {f"zrel_q{i}"}) for i in range(8)
    ]
    routes = {"perfect": _perfect_route, "noisy": _noisy_route}
    weights = fit_route_weights(train_pairs, routes, n_iter=10, k_recall=1)
    # At uniform weights both routes score the same; "a_wrong_qN" sorts
    # before "zrel_qN" so recall@1 starts at 0. The fitter must shift
    # weight toward perfect (or away from noisy) to surface the relevant
    # doc above the lie.
    assert weights["perfect"] > weights["noisy"], weights


def test_fit_respects_weight_bounds():
    train_pairs = [("q1", {"rel_q1"}), ("q2", {"rel_q2"})]
    routes = {"perfect": _perfect_route, "noisy": _noisy_route}
    weights = fit_route_weights(train_pairs, routes, n_iter=20)
    for route, weight in weights.items():
        assert WEIGHT_BOUND_LOW <= weight <= WEIGHT_BOUND_HIGH, (route, weight)


def test_fit_empty_pairs_returns_uniform():
    routes = {"a": _perfect_route, "b": _noisy_route}
    weights = fit_route_weights([], routes, n_iter=5)
    assert weights == {"a": 1.0, "b": 1.0}


def test_fit_empty_routes_returns_empty():
    weights = fit_route_weights([("q1", {"r1"})], {}, n_iter=5)
    assert weights == {}


def test_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMPALACE_USE_LEARNED_WEIGHTS", "1")
    path = tmp_path / "rrf_weights.json"
    save_route_weights(
        {"vector": 1.5, "bm25": 0.8},
        path=path,
        train_pair_count=42,
        n_iter_used=3,
    )
    assert path.exists()
    loaded = load_route_weights(path=path)
    assert loaded == {"vector": 1.5, "bm25": 0.8}
    # File contains expected metadata.
    payload = json.loads(path.read_text())
    assert payload["train_pair_count"] == 42
    assert payload["n_iter_used"] == 3
    assert "fitted_at" in payload


def test_loader_returns_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMPALACE_USE_LEARNED_WEIGHTS", "1")
    missing = tmp_path / "does_not_exist.json"
    assert load_route_weights(path=missing) == {}


def test_loader_returns_empty_when_flag_off(tmp_path, monkeypatch):
    monkeypatch.delenv("MEMPALACE_USE_LEARNED_WEIGHTS", raising=False)
    path = tmp_path / "rrf_weights.json"
    save_route_weights({"vector": 2.0}, path=path)
    # Flag is off — loader returns {} even when file exists.
    assert load_route_weights(path=path) == {}


def test_loader_handles_malformed_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMPALACE_USE_LEARNED_WEIGHTS", "1")
    path = tmp_path / "rrf_weights.json"
    path.write_text("{not valid json")
    assert load_route_weights(path=path) == {}


def test_loader_skips_non_numeric_weights(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMPALACE_USE_LEARNED_WEIGHTS", "1")
    path = tmp_path / "rrf_weights.json"
    path.write_text(json.dumps({"weights": {"vector": "oops", "bm25": 1.5}}))
    out = load_route_weights(path=path)
    assert out == {"bm25": 1.5}
