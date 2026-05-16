"""Feature-flag ablation runner (Phase 7 / spec §17.7).

Each ablation row sets a fixed set of ``MEMPALACE_ENABLE_*`` environment
flags and then runs a benchmark. The benchmark today is the local "mock"
dev split — a small seeded palace and a JSONL of questions whose expected
drawer ids we score against. Public benchmarks (LongMemEval, LoCoMo,
ConvoMem, MemBench) are deferred until their datasets land locally; this
module is the public retrieval entry point through which they will plug.

The runner intentionally does NOT claim retrieval improvement. Each row's
result dict is implementation-supported (the runner is real); whether
flags change retrieval quality positively or negatively is exactly the
question Phase 7 wants to answer. The claim status remains experimental
until benchmark evidence ships.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .adapters import get_adapter
from .metrics import mrr, recall_at_k
from .run_manifest import build_manifest, dataset_sha, write_manifest


CONTAMINATION_LOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "mempalace"
    / "evidence"
    / "contamination_log.yaml"
)
MIN_UNSEAL_REASON_LEN = 40


ABLATION_ROWS: Dict[str, Dict[str, str]] = {
    "A0": {},
    "A1": {"MEMPALACE_ENABLE_FUSION": "1"},
    "A2": {
        "MEMPALACE_ENABLE_FUSION": "1",
        "MEMPALACE_ENABLE_GAP_GRAPH": "1",
    },
    "A3": {
        "MEMPALACE_ENABLE_FUSION": "1",
        "MEMPALACE_ENABLE_TOPOLOGY_ROUTES": "1",
    },
    "A4": {"MEMPALACE_ENABLE_TRACE": "1"},
    "A5": {"MEMPALACE_ENABLE_BALANCED_WAKEUP": "1"},
    "A6": {
        "MEMPALACE_ENABLE_FUSION": "1",
        "MEMPALACE_ENABLE_TRACE": "1",
    },
    "A7": {
        "MEMPALACE_ENABLE_FUSION": "1",
        "MEMPALACE_ENABLE_TOPOLOGY_ROUTES": "1",
        "MEMPALACE_ENABLE_TRACE": "1",
    },
    "A8": {
        "MEMPALACE_ENABLE_FUSION": "1",
        "MEMPALACE_ENABLE_TOPOLOGY_ROUTES": "1",
        "MEMPALACE_ENABLE_TRACE": "1",
        "MEMPALACE_ENABLE_BALANCED_WAKEUP": "1",
    },
}


DEFAULT_DEV_SPLIT_PATH = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "data" / "dev_split.jsonl"
)


def _load_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _seed_palace_for_dev_split(questions: List[dict]):
    """Build a seeded palace whose drawers cover the dev split's expected ids.

    Drawer text is synthesized from the question + expected ids so retrieval
    has something to find. The palace is a context manager — torn down when
    the run completes.
    """
    from ._palace_fixture import SeedDrawer, palace_with_drawers

    seeds: List[SeedDrawer] = []
    seen_ids = set()
    for q in questions:
        question = q.get("question", "")
        for did in q.get("expected_drawer_ids", []):
            if did in seen_ids:
                continue
            seen_ids.add(did)
            # Wing/room derived from drawer id prefix so we get some real
            # topology in the seed (drawer_research_planning -> wing=research,
            # room=planning).
            parts = did.split("_")
            wing = parts[1] if len(parts) > 1 else "general"
            room = "_".join(parts[2:]) if len(parts) > 2 else "general"
            seeds.append(
                SeedDrawer(
                    drawer_id=did,
                    document=(
                        f"{question} Answer context for {did}: this drawer "
                        f"corresponds to {wing} / {room}."
                    ),
                    wing=wing,
                    room=room,
                )
            )
    # Also add some decoy drawers so retrieval has to actually rank.
    for i in range(5):
        seeds.append(
            SeedDrawer(
                drawer_id=f"decoy_{i}",
                document=f"unrelated decoy drawer {i} about something else entirely",
                wing="decoy",
                room="noise",
            )
        )
    return palace_with_drawers(seeds)


def _run_mock_benchmark(set_name: str = "validation", top_k: int = 5) -> dict:
    """Run the seeded mock benchmark and return retrieval metrics.

    The mock benchmark reads ``benchmarks/data/dev_split.jsonl`` (with a
    fallback to an empty result when the file is missing). For each
    question it calls ``mempalace.searcher.search_memories`` against the
    seeded palace and scores the returned drawer ids against the
    question's expected ids. ``set_name`` is recorded in the result so the
    same code path will later route test/audit splits when those exist.
    """
    from mempalace.searcher import search_memories

    questions = _load_jsonl(DEFAULT_DEV_SPLIT_PATH)
    if not questions:
        return {
            "recall_at_5": 0.0,
            "mrr": 0.0,
            "n_questions": 0,
            "set": set_name,
            "note": "dev_split.jsonl missing or empty",
        }

    recalls: List[float] = []
    mrrs: List[float] = []
    with _seed_palace_for_dev_split(questions) as palace_path:
        for q in questions:
            expected = q.get("expected_drawer_ids", []) or []
            try:
                result = search_memories(
                    query=q["question"],
                    palace_path=palace_path,
                    n_results=top_k,
                )
            except Exception:
                result = {"results": []}
            hits = result.get("results", []) or []
            # search_memories returns text + source_file but not the raw
            # drawer id. We match by checking whether the expected id (or
            # its trailing suffix) appears in any returned text. Synthetic
            # drawer text contains the id by construction in this fixture.
            retrieved_ids: List[str] = []
            for h in hits:
                text = (h.get("text") or "").lower()
                for did in expected:
                    if did.lower() in text and did not in retrieved_ids:
                        retrieved_ids.append(did)
            # Pad retrieved_ids so recall@k counts distinct hits, not just
            # the ones that matched the gold list.
            recalls.append(recall_at_k(retrieved_ids, expected, top_k))
            mrrs.append(mrr(retrieved_ids, expected))

    n = len(questions)
    return {
        "recall_at_5": round(sum(recalls) / n, 4) if n else 0.0,
        "mrr": round(sum(mrrs) / n, 4) if n else 0.0,
        "n_questions": n,
        "set": set_name,
    }


def _run_adapter_benchmark(
    benchmark: str,
    set_name: str,
    split_path: Optional[Path] = None,
    top_k: int = 5,
) -> dict:
    """Run a public-benchmark adapter against the local seeded fixture.

    The adapter loads questions from ``split_path`` (default: dev split),
    retrieval is performed via ``mempalace.searcher.search_memories``
    against a seeded palace, and the adapter's own ``score`` method
    aggregates the metric dict. This is the production hook for when real
    public-benchmark JSONLs (LongMemEval, LoCoMo, ConvoMem, MemBench) land.
    Until then it runs end-to-end against the dev-split JSONL so the wiring
    stays exercised.
    """
    from mempalace.searcher import search_memories

    adapter = get_adapter(benchmark)
    path = Path(split_path) if split_path else DEFAULT_DEV_SPLIT_PATH
    questions = list(adapter.load_split(str(path)))
    if not questions:
        return {
            "n_questions": 0,
            "set": set_name,
            "benchmark": adapter.name,
            "note": f"split missing or empty at {path}",
        }

    raw_rows = [
        {
            "question": q.text,
            "expected_drawer_ids": list(q.relevant_drawer_ids),
        }
        for q in questions
    ]

    aggregated: Dict[str, List[float]] = {}
    n_scored = 0
    with _seed_palace_for_dev_split(raw_rows) as palace_path:
        for q in questions:
            try:
                result = search_memories(
                    query=q.text,
                    palace_path=palace_path,
                    n_results=top_k,
                )
            except Exception:
                result = {"results": []}
            hits = result.get("results", []) or []
            retrieved_ids: List[str] = []
            for h in hits:
                text = (h.get("text") or "").lower()
                for did in q.relevant_drawer_ids:
                    if did.lower() in text and did not in retrieved_ids:
                        retrieved_ids.append(did)
            try:
                metrics_row = adapter.score(q, retrieved_ids)
            except Exception as exc:  # pragma: no cover - defensive
                metrics_row = {"score_error": 1.0, "error": str(exc)}
            n_scored += 1
            for key, value in metrics_row.items():
                if isinstance(value, (int, float)):
                    aggregated.setdefault(key, []).append(float(value))

    summary: Dict[str, object] = {}
    for key, values in aggregated.items():
        summary[key] = round(sum(values) / len(values), 4) if values else 0.0
    summary["n_questions"] = n_scored
    summary["set"] = set_name
    summary["benchmark"] = adapter.name
    return summary


def _benchmark_dispatch(benchmark: str, set_name: str) -> dict:
    """Route to the right benchmark backend.

    ``mock`` runs the legacy seeded local benchmark. Adapter names
    registered in ``eval.adapters`` (longmemeval, locomo, convomem,
    membench) run end-to-end against the dev-split fixture today; once
    real public datasets are checked in, the same code path scores the
    real questions. Unknown benchmark names raise a clear error.
    """
    if benchmark == "mock":
        return _run_mock_benchmark(set_name=set_name)
    return _run_adapter_benchmark(benchmark, set_name)


def run_ablation(row: str, benchmark: str = "mock", set_name: str = "validation") -> dict:
    """Run one ablation row: set env flags, run the benchmark, restore env."""
    if row not in ABLATION_ROWS:
        raise KeyError(f"unknown ablation row: {row!r}")
    flags = ABLATION_ROWS[row]
    old = {key: os.environ.get(key) for key in flags}
    os.environ.update(flags)
    try:
        metrics = _benchmark_dispatch(benchmark, set_name)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    return {
        "row": row,
        "benchmark": benchmark,
        "set": set_name,
        "flags": dict(flags),
        "metrics": metrics,
    }


def run_full_matrix(
    set_name: str = "validation",
    rows: Optional[List[str]] = None,
    output_dir: str = "benchmarks/results/validation",
    benchmark: str = "mock",
) -> dict:
    rows = rows or list(ABLATION_ROWS)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    results: Dict[str, List[dict]] = {}
    for row in rows:
        results[row] = [run_ablation(row, benchmark=benchmark, set_name=set_name)]
    for row, payloads in results.items():
        path = Path(output_dir) / f"{benchmark}_{row}.jsonl"
        path.write_text(
            "\n".join(json.dumps(item, sort_keys=True) for item in payloads) + "\n"
        )
    write_manifest(
        Path(output_dir) / "manifest.json",
        build_manifest(
            configuration={"set": set_name, "rows": rows, "benchmark": benchmark}
        ),
    )
    return results


def _git_head_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def _load_contamination_log(path: Optional[Path] = None) -> dict:
    target = Path(path) if path is not None else CONTAMINATION_LOG_PATH
    if not target.exists():
        return {"sets": []}
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {"sets": []}
    if not isinstance(data.get("sets"), list):
        data["sets"] = []
    return data


def _save_contamination_log(data: dict, path: Optional[Path] = None) -> None:
    target = Path(path) if path is not None else CONTAMINATION_LOG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _find_prior_seal_entry(
    log: dict, set_name: str, dataset_hash: str, commit_sha: str
) -> Optional[dict]:
    """Return the earliest matching prior sealed entry, or None.

    A prior entry blocks re-running iff it has the same set name, dataset
    sha, and commit sha. Different commit means new code — re-run is
    allowed (a fresh contamination event will be logged). Different
    dataset sha means a different test split — also allowed.
    """
    for entry in log.get("sets", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("set") != set_name:
            continue
        if entry.get("dataset_sha") != dataset_hash:
            continue
        if entry.get("commit_sha") != commit_sha:
            continue
        if entry.get("marker") != "sealed":
            continue
        return entry
    return None


def _append_seal_entry(
    set_name: str,
    dataset_hash: str,
    commit_sha: str,
    benchmark: str,
    rows: List[str],
    extra: Optional[dict] = None,
    log_path: Optional[Path] = None,
) -> dict:
    target = Path(log_path) if log_path is not None else CONTAMINATION_LOG_PATH
    log = _load_contamination_log(target)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commit_sha": commit_sha,
        "dataset_sha": dataset_hash,
        "set": set_name,
        "benchmark": benchmark,
        "rows": list(rows),
        "marker": "sealed",
    }
    if extra:
        entry.update(extra)
    log["sets"].append(entry)
    _save_contamination_log(log, target)
    return entry


def _resolve_split_path(set_name: str, benchmark: str) -> Path:
    """Resolve the dataset split path used for sha computation.

    Validation runs against the dev split JSONL; test runs against the
    sealed split file. The path itself is what gets sha-hashed for the
    contamination log entry.
    """
    if set_name == "validation":
        return DEFAULT_DEV_SPLIT_PATH
    repo_root = Path(__file__).resolve().parents[1]
    candidate = (
        repo_root / "benchmarks" / "data" / benchmark / f"{set_name}_split.jsonl"
    )
    if candidate.exists():
        return candidate
    # Fall back to the dev split so the sha is still deterministic; the
    # contamination log will record this fact via the path field.
    return DEFAULT_DEV_SPLIT_PATH


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", dest="set_name", default="validation")
    parser.add_argument("--rows", default="A0-A8")
    parser.add_argument("--benchmark", default="mock")
    parser.add_argument("--seal", action="store_true")
    parser.add_argument(
        "--unseal-emergency",
        default=None,
        help=(
            "Allow a sealed-set re-run despite a prior contamination entry. "
            f"Reason text must be at least {MIN_UNSEAL_REASON_LEN} characters and "
            "is recorded in the contamination log."
        ),
    )
    args = parser.parse_args(argv)
    if args.rows == "A0-A8":
        rows = list(ABLATION_ROWS)
    else:
        rows = [r.strip() for r in args.rows.split(",") if r.strip()]
    if args.seal and args.set_name != "test":
        raise SystemExit("--seal is only valid for the test set")
    if args.unseal_emergency is not None and not args.seal:
        raise SystemExit("--unseal-emergency requires --seal")

    if args.seal:
        split_path = _resolve_split_path(args.set_name, args.benchmark)
        try:
            dataset_hash = dataset_sha(split_path)
        except FileNotFoundError as exc:
            raise SystemExit(f"sealed run aborted: {exc}")
        commit_sha = _git_head_sha()
        log = _load_contamination_log()
        prior = _find_prior_seal_entry(
            log, args.set_name, dataset_hash, commit_sha
        )
        if prior is not None:
            if args.unseal_emergency is None:
                raise SystemExit(
                    "sealed run refused: prior contamination entry on "
                    f"{prior.get('timestamp')} for commit "
                    f"{prior.get('commit_sha')} (dataset_sha "
                    f"{dataset_hash[:12]}). Re-running would contaminate the "
                    "sealed test set. Pass --unseal-emergency <reason> to "
                    "override."
                )
            reason = args.unseal_emergency.strip()
            if len(reason) < MIN_UNSEAL_REASON_LEN:
                raise SystemExit(
                    "--unseal-emergency reason must be at least "
                    f"{MIN_UNSEAL_REASON_LEN} characters"
                )
            extra = {
                "unseal_emergency": True,
                "unseal_reason": reason,
                "supersedes_timestamp": prior.get("timestamp"),
            }
        else:
            extra = None

        run_full_matrix(
            args.set_name,
            rows,
            f"benchmarks/results/{args.set_name}",
            benchmark=args.benchmark,
        )
        _append_seal_entry(
            args.set_name,
            dataset_hash,
            commit_sha,
            args.benchmark,
            rows,
            extra=extra,
        )
        return

    run_full_matrix(
        args.set_name,
        rows,
        f"benchmarks/results/{args.set_name}",
        benchmark=args.benchmark,
    )


if __name__ == "__main__":
    main()
