from unittest.mock import patch

from mempalace import searcher


def test_topology_never_drops_baseline(monkeypatch):
    monkeypatch.setenv("MEMPALACE_ENABLE_FUSION", "1")
    baseline = {
        "query": "Riley",
        "filters": {"wing": None, "room": None},
        "total_before_filter": 2,
        "results": [
            {"drawer_id": "d1", "source_file": "a.md", "text": "one", "similarity": 0.9},
            {"drawer_id": "d2", "source_file": "b.md", "text": "two", "similarity": 0.8},
        ],
    }
    with patch.object(searcher, "_legacy_search_memories_for_fusion", return_value=baseline):
        fused = searcher.search_memories("Riley", "/tmp/no-palace", n_results=2)
    pool_ids = {item.get("drawer_id") for item in fused["candidate_pool"]}
    assert {"d1", "d2"} <= pool_ids
