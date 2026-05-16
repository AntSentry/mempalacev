"""Persist and load learned RRF route weights.

Phase 10 Tier 3 — see ``docs/rfcs/T3c-learned-rrf-weights.md``.

The loader returns ``{}`` (uniform weights) when:
- the env flag ``MEMPALACE_USE_LEARNED_WEIGHTS`` is off, OR
- the saved weights file is missing, OR
- the saved file is malformed.

This means callers can unconditionally pass ``load_route_weights()`` to
:func:`mempalace.retrieval.fusion.rrf_score` — uniform weights restore
the historical default.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


DEFAULT_WEIGHTS_PATH = Path.home() / ".mempalace" / "rrf_weights.json"
_USE_LEARNED_ENV = "MEMPALACE_USE_LEARNED_WEIGHTS"


def _flag_enabled() -> bool:
    return os.environ.get(_USE_LEARNED_ENV, "").lower() in {"1", "true", "yes", "on"}


def load_route_weights(path: Optional[Path] = None) -> Dict[str, float]:
    """Return saved route weights, or ``{}`` if unavailable / flag off.

    When the env flag is off this returns ``{}`` regardless of whether a
    file exists — opt-in is mandatory (RFC §6).
    """

    if not _flag_enabled():
        return {}
    target = Path(path) if path is not None else DEFAULT_WEIGHTS_PATH
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    weights = payload.get("weights") if isinstance(payload, dict) else None
    if not isinstance(weights, dict):
        return {}
    out: Dict[str, float] = {}
    for route, value in weights.items():
        try:
            out[str(route)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def save_route_weights(
    weights: Dict[str, float],
    path: Optional[Path] = None,
    train_pair_count: int = 0,
    n_iter_used: int = 0,
) -> Path:
    """Atomically persist ``weights`` to disk and return the file path."""

    target = Path(path) if path is not None else DEFAULT_WEIGHTS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "weights": {str(r): float(v) for r, v in weights.items()},
        "fitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "train_pair_count": int(train_pair_count),
        "n_iter_used": int(n_iter_used),
    }
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return target
