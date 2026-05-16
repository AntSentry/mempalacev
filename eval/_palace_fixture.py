"""Synthetic palace fixture builder for eval suites.

The eval suites (stale_fact, cross_wing, ablation runner) need a real palace
backing real retrieval — but bringing the user's actual palace into eval
would contaminate it and break reproducibility. This module builds an
ephemeral palace under a temp dir, seeds it with drawers matching the suite
data (drawer_id -> document text), and tears it down on context exit.

Embeddings are deterministic and supplied explicitly so chromadb does NOT
invoke its default ONNX embedder — onnxruntime is not always installed in
eval/CI environments. Vector retrieval over these dummy embeddings is
intentionally weak; the suites lean on BM25 + content matching, which is
where the topology layer's experimental contribution lives.
"""

from __future__ import annotations

import hashlib
import math
import tempfile
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

import chromadb
from chromadb.utils import embedding_functions


EMBED_DIM = 16


def _deterministic_embedding(text: str) -> List[float]:
    """A tiny content-derived embedding. Words mapped into a 16-dim space via
    SHA-256-keyed buckets. Deterministic, no external deps, good enough for
    BM25-leaning retrieval where the vector is only a tie-breaker."""
    if not text:
        return [0.0] * EMBED_DIM
    vec = [0.0] * EMBED_DIM
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = digest[0] % EMBED_DIM
        sign = 1.0 if (digest[1] & 1) == 0 else -1.0
        vec[idx] += sign
    # L2 normalize so cosine distance behaves.
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class _DeterministicEmbeddingFunction(embedding_functions.EmbeddingFunction):
    """ChromaDB-compatible EF wrapping ``_deterministic_embedding``.

    Used by the eval suites so retrieval can run without onnxruntime. The
    EF is registered on the chroma collection AND patched onto
    ``mempalace.embedding.get_embedding_function`` so the searcher's get-
    collection path picks up the same function and dimensions match between
    write and read paths.
    """

    def __init__(self):
        pass

    @staticmethod
    def name() -> str:
        # ChromaDB persists EF identity on the collection; using "default"
        # matches mempalace's _MempalaceONNX class name so any existing
        # palace metadata does not reject this reader.
        return "default"

    def __call__(self, input):
        if isinstance(input, str):
            input = [input]
        return [_deterministic_embedding(t) for t in input]


@dataclass
class SeedDrawer:
    drawer_id: str
    document: str
    wing: str
    room: str
    source_file: Optional[str] = None
    extra_metadata: Optional[Dict] = None


@contextmanager
def palace_with_drawers(drawers: Iterable[SeedDrawer], collection_name: str = "mempalace_drawers"):
    """Yield a palace_path containing the given drawers; clean up on exit.

    While the context is active, ``mempalace.embedding.get_embedding_function``
    is patched to return the deterministic eval EF so the searcher reads
    with the same dimensions the seed wrote with. The patch is reverted on
    exit so this fixture cannot leak into other test or production code.
    """
    palace_path = tempfile.mkdtemp(prefix="mempalace_eval_")
    ef = _DeterministicEmbeddingFunction()

    # Patch the mempalace embedding entry point so searcher.search_memories
    # picks up our deterministic EF instead of ONNXMiniLM. We patch in-place
    # and restore on exit; no global state survives the context.
    import mempalace.embedding as _mem_emb

    original_fn = _mem_emb.get_embedding_function
    _mem_emb.get_embedding_function = lambda device=None: ef
    # Invalidate any cached EF so the next get_collection rebuilds with ours.
    cache = getattr(_mem_emb, "_EF_CACHE", None)
    if isinstance(cache, dict):
        cache.clear()

    # The chroma backend caches palace clients keyed by path; clear it so
    # this temp palace starts from a clean cache state.
    try:
        from mempalace.backends.chroma import ChromaBackend
        ChromaBackend._quarantined_paths.clear()
    except (ImportError, AttributeError):
        pass

    try:
        client = chromadb.PersistentClient(path=palace_path)
        col = client.get_or_create_collection(
            collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=ef,
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        ids, docs, embeds, metas = [], [], [], []
        for d in drawers:
            ids.append(d.drawer_id)
            docs.append(d.document)
            embeds.append(_deterministic_embedding(d.document))
            md = {
                "wing": d.wing,
                "room": d.room,
                "source_file": d.source_file or f"{d.drawer_id}.md",
                "filed_at": now_iso,
                "chunk_index": 0,
            }
            if d.extra_metadata:
                md.update(d.extra_metadata)
            metas.append(md)
        if ids:
            col.add(ids=ids, documents=docs, embeddings=embeds, metadatas=metas)
        del client
        yield palace_path
    finally:
        _mem_emb.get_embedding_function = original_fn
        if isinstance(cache, dict):
            cache.clear()
        shutil.rmtree(palace_path, ignore_errors=True)


def drawer_score(retrieved_text: str, expected_id: str, expected_keywords: List[str]) -> float:
    """How well does the retrieved drawer match an expected id's text?

    Used by suites where we can't compare by drawer_id directly (BM25 path
    returns IDs but vector path may return reconstructed text). Score is the
    fraction of expected keywords present (case-insensitive).
    """
    if not retrieved_text or not expected_keywords:
        return 0.0
    text_lower = retrieved_text.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in text_lower)
    return hits / len(expected_keywords)
