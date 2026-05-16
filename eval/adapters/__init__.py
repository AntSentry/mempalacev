"""Public benchmark adapters.

Each adapter implements the :class:`BenchmarkAdapter` protocol from
:mod:`eval.adapters.base`. The :func:`get_adapter` factory dispatches a
benchmark name (``longmemeval``, ``locomo``, ``convomem``, ``membench``)
to the corresponding adapter instance.

Real public benchmark datasets are not committed to this repository
(license-restricted). The adapter scaffolds work end-to-end against the
local ``benchmarks/data/dev_split.jsonl`` fixture — when the real
JSONLs land in ``benchmarks/data/<name>/``, the same adapter loads
them. This is the seam that lets Phase 8 run cleanly.
"""

from __future__ import annotations

from typing import Dict

from .base import BenchmarkAdapter, BenchmarkQuestion
from .convomem import ConvoMemAdapter
from .locomo import LoCoMoAdapter
from .longmemeval import LongMemEvalAdapter
from .membench import MemBenchAdapter


_REGISTRY: Dict[str, BenchmarkAdapter] = {
    "longmemeval": LongMemEvalAdapter(),
    "locomo": LoCoMoAdapter(),
    "convomem": ConvoMemAdapter(),
    "membench": MemBenchAdapter(),
}


def get_adapter(name: str) -> BenchmarkAdapter:
    """Return the adapter registered under ``name``.

    Raises :class:`KeyError` with the list of known names so the caller
    can produce a clear error message at the CLI boundary.
    """
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY))
        raise KeyError(
            f"unknown benchmark adapter {name!r}; known adapters: {known}"
        ) from exc


def list_adapters() -> list:
    """Return registered adapter names (sorted) for help text."""
    return sorted(_REGISTRY)


__all__ = [
    "BenchmarkAdapter",
    "BenchmarkQuestion",
    "ConvoMemAdapter",
    "LoCoMoAdapter",
    "LongMemEvalAdapter",
    "MemBenchAdapter",
    "get_adapter",
    "list_adapters",
]
