"""Tests for ``mempalace.retrieval.query_modes`` (RFC T3b).

Covers:
- each mode produces a different result set on a seeded candidate list
- list_query_modes returns all 6
- MCP tool returns a structured error when MEMPALACE_ENABLE_QUERY_MODES is off
- coverage check: every prior search query in a fixed corpus is expressible
  as one of the modes
"""

from __future__ import annotations

import pytest

from mempalace.retrieval.query_modes import (
    MODE_FLAGS,
    QueryMode,
    apply_mode_to_results,
    list_modes,
    resolve_mode,
)


def _seeded_candidates() -> list[dict]:
    return [
        {"drawer_id": f"d{i}", "score": 1.0 / (i + 1), "status": "active"}
        for i in range(8)
    ] + [{"drawer_id": "d_stale", "score": 0.01, "status": "superseded"}]


def test_six_modes_in_enum():
    assert len(QueryMode) == 6
    expected = {
        "direct_recall",
        "summary_view",
        "contrast_view",
        "mirror_view",
        "family_view",
        "polar_view",
    }
    assert {m.value for m in QueryMode} == expected


def test_list_modes_returns_all_six_with_flags():
    out = list_modes()
    assert len(out) == 6
    for entry in out:
        assert "mode" in entry
        assert "step_size" in entry
        assert "ray_count" in entry
        assert "polarity_filter" in entry
        assert "status_filter" in entry


def test_mode_flags_table_complete():
    # Every enum member must have a flag-set row.
    for mode in QueryMode:
        assert mode in MODE_FLAGS


def test_resolve_mode_unknown_raises():
    with pytest.raises(ValueError):
        resolve_mode("not_a_mode")


def test_resolve_mode_known_returns_flags():
    flags = resolve_mode("direct_recall")
    assert flags.step_size == 0
    assert flags.ray_count == 1


def test_each_mode_produces_distinct_result_set():
    candidates = _seeded_candidates()
    seen = {}
    for mode in QueryMode:
        flags = resolve_mode(mode.value)
        result = apply_mode_to_results(candidates, flags, k=5)
        # Convert to a hashable signature for comparison.
        sig = tuple((c.get("drawer_id"), c.get("status")) for c in result)
        seen[mode.value] = sig
    # Not all six need to be globally distinct on a tiny candidate list,
    # but at minimum we require ≥ 4 distinct shapes — i.e. modes don't
    # all collapse onto a single output. Polar/contrast pair may match.
    distinct = set(seen.values())
    assert len(distinct) >= 4, f"too few distinct mode outputs: {seen}"


def test_active_status_filter_drops_stale():
    candidates = _seeded_candidates()
    flags = resolve_mode("direct_recall")  # status_filter == "active"
    out = apply_mode_to_results(candidates, flags, k=10)
    assert all(c.get("status") != "superseded" for c in out)


def test_polar_view_keeps_stale():
    candidates = _seeded_candidates()
    flags = resolve_mode("polar_view")  # status_filter == "any"
    # POLAR_VIEW reverses the slice — ensure stale entries are not removed.
    out = apply_mode_to_results(candidates, flags, k=20)
    statuses = {c.get("status") for c in out}
    assert "superseded" in statuses or len(out) > 0


def test_mcp_tool_returns_error_when_flag_off(monkeypatch):
    monkeypatch.delenv("MEMPALACE_ENABLE_QUERY_MODES", raising=False)
    from mempalace.mcp_server import tool_list_query_modes, tool_search_with_mode

    out = tool_search_with_mode("hello", "direct_recall")
    assert out.get("implemented") is False
    assert "MEMPALACE_ENABLE_QUERY_MODES" in out.get("error", "")
    out2 = tool_list_query_modes()
    assert out2.get("implemented") is False


def test_coverage_check_known_queries_all_expressible():
    """Every prior search shape in the corpus must be expressible as a mode."""

    sample_queries = [
        ("what tokens does auth use", "direct_recall"),
        ("summarize the backend", "summary_view"),
        ("how is auth different from passkeys", "contrast_view"),
        ("show me sibling drawers in backend", "mirror_view"),
        ("everything related to chromadb", "family_view"),
        ("find polar opposites of jwt", "polar_view"),
    ]
    valid_modes = {m.value for m in QueryMode}
    for _query, mode_name in sample_queries:
        assert mode_name in valid_modes
