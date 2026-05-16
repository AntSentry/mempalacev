"""Canonical 18-term topology word and pure helper functions."""

from __future__ import annotations

import math
from typing import List, Tuple


NEXUS_WORD: Tuple[int, ...] = (1, 6, 5, 2, 9, 7, 4, 3, 8, 8, 3, 4, 7, 9, 2, 5, 6, 1)
PERIOD = 18


def nexus_label(q: int) -> int:
    """Return the digit at position ``q`` modulo 18."""

    return NEXUS_WORD[q % PERIOD]


def family(label: int) -> int:
    """Return the mod-3 family for labels 1 through 9."""

    if label not in range(1, 10):
        raise ValueError("label must be in 1..9")
    if label in {1, 4, 7}:
        return 1
    if label in {2, 5, 8}:
        return 2
    return 3


def polarity(q: int) -> int:
    """Return +1 for positions 0..8 and -1 for positions 9..17."""

    return 1 if q % PERIOD < 9 else -1


def step_period(step: int) -> int:
    """Return deterministic cycle coverage: ``18 / gcd(18, step)``."""

    return PERIOD // math.gcd(PERIOD, step)


def decimation(start: int, step: int, n: int) -> List[int]:
    """Sample ``NEXUS_WORD`` starting at ``start`` by ``step`` for ``n`` terms."""

    if n < 0:
        raise ValueError("n must be non-negative")
    return [nexus_label(start + i * step) for i in range(n)]

