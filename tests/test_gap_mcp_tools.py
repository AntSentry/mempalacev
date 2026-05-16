from unittest.mock import MagicMock, patch

import pytest


def test_mcp_gap_tools_registered():
    import mempalace.mcp_server as mcp_server

    assert "mempalace_gap_list" in mcp_server.TOOLS
    assert "mempalace_gap_resolve" in mcp_server.TOOLS
    assert "mempalace_trace_recall" in mcp_server.TOOLS


def test_mempalace_gap_list_returns_filtered(monkeypatch):
    import mempalace.mcp_server as mcp_server

    monkeypatch.setenv("MEMPALACE_ENABLE_GAP_GRAPH", "1")
    fake_kg = MagicMock()
    fake_conn = MagicMock()
    fake_kg._conn.return_value = fake_conn
    with patch.object(mcp_server, "_call_kg", side_effect=lambda op: op(fake_kg)):
        with patch("mempalace.graph.gap_graph.list_gap_events", return_value=[{"id": "gap_1"}]) as mock_list:
            result = mcp_server.tool_gap_list(subject="riley", status="open", limit=20)
    assert result["count"] == 1
    mock_list.assert_called_once_with(fake_conn, status="open", gap_type=None, limit=20, subject="riley")


def test_mempalace_gap_resolve_legal(monkeypatch):
    import mempalace.mcp_server as mcp_server

    monkeypatch.setenv("MEMPALACE_ENABLE_GAP_GRAPH", "1")
    fake_kg = MagicMock()
    fake_conn = MagicMock()
    fake_kg._conn.return_value = fake_conn
    with patch.object(mcp_server, "_call_kg", side_effect=lambda op: op(fake_kg)):
        with patch("mempalace.graph.gap_graph.transition_gap_event", return_value=True) as mock_transition:
            result = mcp_server.tool_gap_resolve(
                event_id="gap_1",
                to_status="resolved",
                evidence_drawer_id="drawer_1",
                rationale="accepted",
            )
    assert result == {"success": True, "event_id": "gap_1", "status": "resolved"}
    mock_transition.assert_called_once_with(
        fake_conn,
        "gap_1",
        to_status="resolved",
        evidence_drawer_id="drawer_1",
        rationale="accepted",
    )


def test_mempalace_gap_resolve_illegal_returns_error(monkeypatch):
    import mempalace.mcp_server as mcp_server

    monkeypatch.setenv("MEMPALACE_ENABLE_GAP_GRAPH", "1")
    fake_kg = MagicMock()
    fake_conn = MagicMock()
    fake_kg._conn.return_value = fake_conn
    with patch.object(mcp_server, "_call_kg", side_effect=lambda op: op(fake_kg)):
        with patch("mempalace.graph.gap_graph.transition_gap_event", side_effect=ValueError("illegal")):
            result = mcp_server.tool_gap_resolve(event_id="gap_1", to_status="resolved")
    assert result == {"success": False, "event_id": "gap_1", "error": "illegal"}


def test_gap_resolve_current_aliases_remain_supported(monkeypatch):
    import mempalace.mcp_server as mcp_server

    monkeypatch.setenv("MEMPALACE_ENABLE_GAP_GRAPH", "1")
    fake_kg = MagicMock()
    fake_conn = MagicMock()
    fake_kg._conn.return_value = fake_conn
    with patch.object(mcp_server, "_call_kg", side_effect=lambda op: op(fake_kg)):
        with patch("mempalace.graph.gap_graph.transition_gap_event", return_value=True) as mock_transition:
            result = mcp_server.tool_gap_resolve(gap_id="gap_1", status="dismissed", note="duplicate")
    assert result == {"success": True, "event_id": "gap_1", "status": "dismissed"}
    mock_transition.assert_called_once_with(
        fake_conn,
        "gap_1",
        to_status="dismissed",
        evidence_drawer_id=None,
        rationale="duplicate",
    )


def test_mempalace_trace_recall_stub_raises(monkeypatch):
    import mempalace.mcp_server as mcp_server

    monkeypatch.delenv("MEMPALACE_ENABLE_TRACE", raising=False)
    with pytest.raises(NotImplementedError):
        mcp_server.tool_trace_recall(query="x")
