"""Adapter protocol for public retrieval benchmarks.

A ``BenchmarkAdapter`` knows how to (a) load a JSONL split file into a
sequence of :class:`BenchmarkQuestion` records and (b) score a list of
retrieved drawer ids for a single question. The aggregator in
:mod:`eval.ablations` averages the per-question metric dicts.

Splits are JSONL by convention: one JSON object per line. Schemas are
benchmark-specific and live in each adapter module's docstring.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class BenchmarkQuestion:
    """One scoring item from a benchmark split.

    ``relevant_drawer_ids`` is the gold list against which retrieved ids
    are scored. ``metadata`` carries benchmark-specific fields (category,
    multi-hop chain, expected timestamp, etc.) that the adapter's
    ``score`` method may consult.
    """

    question_id: str
    text: str
    relevant_drawer_ids: Sequence[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class BenchmarkAdapter(Protocol):
    """Protocol for public-benchmark adapters."""

    name: str

    def load_split(self, split_path: str) -> Iterable[BenchmarkQuestion]:
        """Yield :class:`BenchmarkQuestion` records from ``split_path``."""

    def score(
        self, question: BenchmarkQuestion, retrieved: Sequence[str]
    ) -> Dict[str, float]:
        """Return a metric dict for one question + retrieved id list."""


def iter_jsonl(split_path: str) -> Iterable[dict]:
    """Yield parsed JSON objects from a JSONL file. Skips blank lines.

    Adapters call this so they all behave identically on whitespace and
    EOF handling. Missing files raise ``FileNotFoundError`` so callers
    fail loudly rather than silently scoring zero questions.
    """
    p = Path(split_path)
    if not p.exists():
        raise FileNotFoundError(f"benchmark split not found: {split_path}")
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        yield json.loads(line)


def normalize_drawer_ids(value: Any) -> List[str]:
    """Coerce a ``relevant_drawer_ids``-like field into ``list[str]``.

    The dev fixture stores a list of strings; some public schemas store
    a single string, a list of dicts with an ``id`` field, or omit the
    field entirely (in which case we return an empty list and the
    question is unscoreable but not fatal).
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for item in value:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict) and "id" in item:
                out.append(str(item["id"]))
        return out
    return []
