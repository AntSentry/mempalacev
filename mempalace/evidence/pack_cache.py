"""LRU cache for ``EvidencePack`` instances keyed by query fingerprint.

Phase 10 Tier 3 — see ``docs/rfcs/T3a-cached-evidence-packs.md``.

The cache is opt-in. Drawer text is never stored — only the partitioned
drawer-id lists already inside :class:`EvidencePack`. Disk persistence is
behind ``MEMPALACE_EVIDENCE_CACHE_DISK=1``; the in-memory layer is always
on when callers wire it up.

Invalidation rule: any palace write bumps ``palace_write_seq``. Cached
entries whose stored ``palace_write_seq`` does not match the current value
are rejected on read. There is no partial invalidation by design — see
RFC §3.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path
from threading import Lock
from typing import Optional

from .evidence_pack import EvidencePack


DEFAULT_MAX_ENTRIES = 256
_DISK_FLAG_ENV = "MEMPALACE_EVIDENCE_CACHE_DISK"
_SIZE_ENV = "MEMPALACE_EVIDENCE_CACHE_SIZE"
_DISK_DIR_DEFAULT = Path.home() / ".mempalace" / "cache" / "evidence_packs"


def _normalize_query(query: str) -> str:
    """Collapse whitespace + lowercase. See RFC §2."""

    return " ".join((query or "").lower().strip().split())


def fingerprint_query(query: str, palace_write_seq: int) -> str:
    """Compute the cache key per RFC §2: blake2b(normalized_query + \\x00 + seq)."""

    payload = _normalize_query(query).encode("utf-8") + b"\x00" + str(int(palace_write_seq)).encode("utf-8")
    return hashlib.blake2b(payload, digest_size=16).hexdigest()


def _disk_enabled() -> bool:
    return os.environ.get(_DISK_FLAG_ENV, "").lower() in {"1", "true", "yes", "on"}


def _max_entries_from_env(default: int) -> int:
    raw = os.environ.get(_SIZE_ENV)
    if not raw:
        return default
    try:
        n = int(raw)
        return n if n > 0 else default
    except ValueError:
        return default


def _pack_to_dict(pack: EvidencePack) -> dict:
    return asdict(pack)


def _pack_from_dict(data: dict) -> EvidencePack:
    return EvidencePack(
        query=data.get("query", ""),
        supporting=list(data.get("supporting", [])),
        contradicting=list(data.get("contradicting", [])),
        stale=list(data.get("stale", [])),
        route_count_for_top=int(data.get("route_count_for_top", 0)),
    )


class EvidencePackCache:
    """In-memory LRU cache for evidence packs with optional disk persistence."""

    def __init__(
        self,
        max_entries: Optional[int] = None,
        disk_dir: Optional[Path] = None,
    ) -> None:
        self._max_entries = max_entries if max_entries is not None else _max_entries_from_env(DEFAULT_MAX_ENTRIES)
        self._disk_dir = Path(disk_dir) if disk_dir is not None else _DISK_DIR_DEFAULT
        # OrderedDict acts as the LRU; values are (seq, pack).
        self._mem: "OrderedDict[str, tuple[int, EvidencePack]]" = OrderedDict()
        self._lock = Lock()

    # ── core API ────────────────────────────────────────────────────────

    def get(self, query: str, palace_write_seq: int) -> Optional[EvidencePack]:
        """Return the cached pack for (query, seq), or None on miss/version mismatch."""

        fp = fingerprint_query(query, palace_write_seq)
        with self._lock:
            entry = self._mem.get(fp)
            if entry is not None:
                cached_seq, pack = entry
                if cached_seq == int(palace_write_seq):
                    self._mem.move_to_end(fp)
                    return pack
                # Version mismatch — drop the stale slot.
                del self._mem[fp]

        # Disk fallback (opt-in).
        if _disk_enabled():
            disk_pack = self._read_from_disk(fp, int(palace_write_seq))
            if disk_pack is not None:
                # Promote to in-memory tier.
                with self._lock:
                    self._mem[fp] = (int(palace_write_seq), disk_pack)
                    self._mem.move_to_end(fp)
                    self._evict_if_needed()
                return disk_pack
        return None

    def set(self, query: str, palace_write_seq: int, pack: EvidencePack) -> None:
        """Store a pack under (query, seq). Evicts LRU when over MAX_ENTRIES."""

        fp = fingerprint_query(query, palace_write_seq)
        with self._lock:
            self._mem[fp] = (int(palace_write_seq), pack)
            self._mem.move_to_end(fp)
            self._evict_if_needed()

        if _disk_enabled():
            self._write_to_disk(fp, int(palace_write_seq), pack)

    def clear(self) -> None:
        with self._lock:
            self._mem.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._mem)

    @property
    def max_entries(self) -> int:
        return self._max_entries

    # ── internals ───────────────────────────────────────────────────────

    def _evict_if_needed(self) -> None:
        # Caller holds self._lock.
        while len(self._mem) > self._max_entries:
            self._mem.popitem(last=False)

    def _disk_path(self, fingerprint: str) -> Path:
        return self._disk_dir / f"{fingerprint}.json"

    def _write_to_disk(self, fingerprint: str, palace_write_seq: int, pack: EvidencePack) -> None:
        try:
            self._disk_dir.mkdir(parents=True, exist_ok=True)
            path = self._disk_path(fingerprint)
            tmp = path.with_suffix(".json.tmp")
            payload = {"palace_write_seq": int(palace_write_seq), "pack": _pack_to_dict(pack)}
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            # Disk persistence is best-effort. Never break the in-memory path.
            return

    def _read_from_disk(self, fingerprint: str, palace_write_seq: int) -> Optional[EvidencePack]:
        path = self._disk_path(fingerprint)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if int(payload.get("palace_write_seq", -1)) != int(palace_write_seq):
            return None
        try:
            return _pack_from_dict(payload.get("pack") or {})
        except Exception:
            return None
