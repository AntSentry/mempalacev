"""Run-manifest capture for validation and sealed evaluations."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess


def dataset_sha(split_path) -> str:
    """Return the sha256 hex digest of the file at ``split_path``.

    Used by the sealed-evaluation contamination log to track which exact
    test split bytes were evaluated against which commit. Determinism is a
    requirement: identical bytes must produce identical sha. Missing or
    non-file paths raise ``FileNotFoundError`` so callers fail loudly
    rather than silently logging a sha of empty input.
    """
    p = Path(split_path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"dataset split not found: {split_path}")
    sha = hashlib.sha256()
    sha.update(p.read_bytes())
    return sha.hexdigest()


def build_manifest(dataset_paths=None, configuration=None):
    dataset_paths = dataset_paths or []
    sha = hashlib.sha256()
    for path in dataset_paths:
        p = Path(path)
        if p.exists() and p.is_file():
            sha.update(p.read_bytes())
    try:
        git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        git_sha = "unknown"
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha,
        "dataset_sha": sha.hexdigest(),
        "configuration": configuration or {},
        "env_flags": {key: value for key, value in os.environ.items() if key.startswith("MEMPALACE_ENABLE_")},
    }


def write_manifest(path, manifest):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(manifest, indent=2, sort_keys=True))
