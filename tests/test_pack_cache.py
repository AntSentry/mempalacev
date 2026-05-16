"""Tests for ``mempalace.evidence.pack_cache`` (RFC T3a).

Covers:
- cache hit returns the same pack instance
- cache miss after palace_write_seq changes
- LRU eviction at MAX_ENTRIES
- disk persistence round-trip when env flag set
- build_evidence_pack honors cache when both cache + seq are passed
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mempalace.evidence.evidence_pack import EvidencePack, build_evidence_pack
from mempalace.evidence.pack_cache import (
    DEFAULT_MAX_ENTRIES,
    EvidencePackCache,
    fingerprint_query,
)


def _make_pack(query: str = "q", supporting=None) -> EvidencePack:
    return EvidencePack(
        query=query,
        supporting=list(supporting or ["d1"]),
        contradicting=[],
        stale=[],
        route_count_for_top=2,
    )


def test_fingerprint_normalizes_query():
    fp1 = fingerprint_query("Hello   World", 7)
    fp2 = fingerprint_query("hello world", 7)
    assert fp1 == fp2


def test_fingerprint_changes_with_seq():
    assert fingerprint_query("q", 1) != fingerprint_query("q", 2)


def test_cache_hit_returns_same_instance():
    cache = EvidencePackCache(max_entries=4)
    pack = _make_pack()
    cache.set("query one", 5, pack)
    out = cache.get("query one", 5)
    assert out is pack


def test_cache_miss_after_seq_changes():
    cache = EvidencePackCache(max_entries=4)
    pack = _make_pack()
    cache.set("q", 1, pack)
    assert cache.get("q", 1) is pack
    # Bumping the version invalidates the cached entry on read. The
    # fingerprint is keyed on (query, seq) so the new seq lands at a
    # different slot — the old slot is unreachable but still present
    # until LRU eviction. What matters: get("q", 2) returns None.
    assert cache.get("q", 2) is None
    # Re-querying at the new seq stores a fresh slot.
    fresh = _make_pack()
    cache.set("q", 2, fresh)
    assert cache.get("q", 2) is fresh
    # The old (seq=1) entry is no longer accessible by the new seq.
    assert cache.get("q", 1) is pack  # still reachable at its original seq


def test_same_query_different_seq_uses_different_slots():
    cache = EvidencePackCache(max_entries=4)
    pack_old = _make_pack(supporting=["old"])
    pack_new = _make_pack(supporting=["new"])
    cache.set("q", 1, pack_old)
    cache.set("q", 2, pack_new)
    assert cache.get("q", 1).supporting == ["old"]
    assert cache.get("q", 2).supporting == ["new"]


def test_lru_eviction_at_max_entries():
    cache = EvidencePackCache(max_entries=3)
    packs = {f"q{i}": _make_pack(f"q{i}") for i in range(4)}
    for i in range(4):
        cache.set(f"q{i}", 1, packs[f"q{i}"])
    # Cache is at the cap.
    assert len(cache) == 3
    # The first inserted entry was evicted (LRU).
    assert cache.get("q0", 1) is None
    # Later entries survived.
    assert cache.get("q3", 1) is packs["q3"]


def test_lru_promotes_on_access():
    cache = EvidencePackCache(max_entries=3)
    for i in range(3):
        cache.set(f"q{i}", 1, _make_pack(f"q{i}"))
    # Touch q0 to promote it.
    assert cache.get("q0", 1) is not None
    # Now insert one more — q1 should be the LRU and get evicted, not q0.
    cache.set("q3", 1, _make_pack("q3"))
    assert cache.get("q1", 1) is None
    assert cache.get("q0", 1) is not None


def test_default_max_entries_uses_constant():
    cache = EvidencePackCache()
    assert cache.max_entries == DEFAULT_MAX_ENTRIES


def test_disk_persistence_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMPALACE_EVIDENCE_CACHE_DISK", "1")
    disk_dir = tmp_path / "epacks"
    cache_a = EvidencePackCache(max_entries=4, disk_dir=disk_dir)
    pack = _make_pack(supporting=["d_disk"])
    cache_a.set("disk query", 11, pack)
    # New cache instance — in-memory layer is empty, must come back from disk.
    cache_b = EvidencePackCache(max_entries=4, disk_dir=disk_dir)
    out = cache_b.get("disk query", 11)
    assert out is not None
    assert out.supporting == ["d_disk"]
    # File written under the deterministic fingerprint name.
    fp = fingerprint_query("disk query", 11)
    assert (disk_dir / f"{fp}.json").exists()


def test_disk_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("MEMPALACE_EVIDENCE_CACHE_DISK", raising=False)
    disk_dir = tmp_path / "epacks_off"
    cache_a = EvidencePackCache(max_entries=4, disk_dir=disk_dir)
    cache_a.set("q", 1, _make_pack())
    cache_b = EvidencePackCache(max_entries=4, disk_dir=disk_dir)
    # No disk fallback — flag is off.
    assert cache_b.get("q", 1) is None
    # And nothing was ever written.
    assert not disk_dir.exists() or not any(disk_dir.iterdir())


def test_build_evidence_pack_uses_cache_when_provided():
    cache = EvidencePackCache(max_entries=4)
    candidates = [{"drawer_id": "d1", "routes": ["a", "b"]}]
    first = build_evidence_pack("query", candidates, cache=cache, palace_write_seq=42)
    # Same call again should hit the cache and return the SAME instance.
    second = build_evidence_pack("query", candidates, cache=cache, palace_write_seq=42)
    assert first is second
    # Different seq → cache miss → new instance.
    third = build_evidence_pack("query", candidates, cache=cache, palace_write_seq=43)
    assert third is not first


def test_build_evidence_pack_unchanged_when_cache_omitted():
    candidates = [{"drawer_id": "d1", "routes": ["a", "b"]}]
    pack = build_evidence_pack("query", candidates)
    assert pack.supporting == ["d1"]


def test_max_entries_env_override(monkeypatch):
    monkeypatch.setenv("MEMPALACE_EVIDENCE_CACHE_SIZE", "2")
    cache = EvidencePackCache()
    assert cache.max_entries == 2
