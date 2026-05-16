from mempalace.evidence.evidence_pack import EvidencePack
from mempalace.retrieval.trace import build_trace, serialize_trace


def test_trace_correctness():
    fused = [{"drawer_id": "d1", "routes": ["baseline", "bm25"]}]
    trace = build_trace("q", fused, EvidencePack("q", supporting=["d1"], route_count_for_top=2))
    payload = serialize_trace(trace)
    assert payload["top_drawer_id"] == "d1"
    assert [route["route"] for route in payload["routes"]] == ["baseline", "bm25"]
