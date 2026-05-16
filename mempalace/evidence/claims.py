"""Claim ledger loading, validation, and audit utilities.

This module implements the Phase 1 claim-discipline foundation from
``MEMPALACE_TOPOLOGY_SPEC.md`` while staying compatible with the project's
current Python 3.9 baseline and dependency set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml


CLAIM_STATUSES = {
    "proven",
    "mathematically_proven",
    "source",
    "source_supported",
    "impl",
    "implementation_supported",
    "benchmark",
    "benchmark_supported",
    "experimental",
}
EVIDENCE_TYPES = {"proof", "source_repo", "unit_test", "integration_test", "benchmark", "none"}
DEFAULT_CLAIMS_PATH = Path(__file__).with_name("claims.yaml")
DEFAULT_FORBIDDEN_PHRASES_PATH = Path(__file__).with_name("forbidden_phrases.txt")
PUBLIC_SURFACE_NAMES = {"README.md", "CHANGELOG.md"}
PUBLIC_SURFACE_DIR_PARTS = {"docs", "public", "landing"}
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


@dataclass(frozen=True)
class Evidence:
    """One evidence reference attached to a claim."""

    type: str
    reference: str


@dataclass(frozen=True)
class Claim:
    """Machine-readable public-claim ledger entry."""

    id: str
    text: str
    status: str
    evidence: List[Evidence]
    publishable: bool
    notes: Optional[str] = None


@dataclass
class AuditReport:
    """Result from a repository claim audit."""

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    claims_checked: int = 0
    files_scanned: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def _coerce_evidence(raw: Any) -> Evidence:
    if not isinstance(raw, dict):
        raise ValueError("evidence entry must be a mapping")
    ev_type = raw.get("type")
    reference = raw.get("reference")
    if ev_type is None and len(raw) == 1:
        ev_type, reference = next(iter(raw.items()))
    if not isinstance(ev_type, str) or not isinstance(reference, str):
        raise ValueError("evidence entry requires string type and reference")
    return Evidence(type=ev_type, reference=reference)


def _coerce_claim(raw: Any) -> Claim:
    if not isinstance(raw, dict):
        raise ValueError("claim entry must be a mapping")
    evidence = [_coerce_evidence(item) for item in raw.get("evidence", [])]
    return Claim(
        id=str(raw.get("id", "")),
        text=str(raw.get("text", "")),
        status=str(raw.get("status", "")),
        evidence=evidence,
        publishable=bool(raw.get("publishable", False)),
        notes=raw.get("notes"),
    )


def _claim_to_dict(claim: Claim) -> Dict[str, Any]:
    data = {
        "id": claim.id,
        "text": claim.text,
        "status": claim.status,
        "evidence": [{"type": ev.type, "reference": ev.reference} for ev in claim.evidence],
        "publishable": claim.publishable,
    }
    if claim.notes is not None:
        data["notes"] = claim.notes
    return data


def load_claims(path: Path = DEFAULT_CLAIMS_PATH) -> List[Claim]:
    """Load ``claims.yaml`` and return typed claim records."""

    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        raise ValueError("claims ledger root must be a list")
    return [_coerce_claim(item) for item in data]


def save_claims(claims: Iterable[Claim], path: Path = DEFAULT_CLAIMS_PATH) -> None:
    """Write claim records to YAML using the canonical ledger shape."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump([_claim_to_dict(claim) for claim in claims], sort_keys=False),
        encoding="utf-8",
    )


def validate_claim(claim: Claim) -> List[str]:
    """Return validation errors for one claim."""

    errors = []
    if not claim.id or not re.match(r"^[a-z0-9_\-]+$", claim.id):
        errors.append(f"{claim.id or '<missing>'}: id must be stable snake/kebab case")
    if not claim.text.strip():
        errors.append(f"{claim.id}: text is required")
    if claim.status not in CLAIM_STATUSES:
        errors.append(f"{claim.id}: unknown status {claim.status!r}")
    if claim.publishable and claim.status == "experimental":
        errors.append(f"{claim.id}: experimental claims cannot be publishable")
    if not claim.evidence:
        errors.append(f"{claim.id}: evidence list is required")
    for ev in claim.evidence:
        if ev.type not in EVIDENCE_TYPES:
            errors.append(f"{claim.id}: unknown evidence type {ev.type!r}")
        if claim.publishable and ev.type == "none":
            errors.append(f"{claim.id}: publishable claims cannot use evidence type 'none'")
        if not ev.reference.strip():
            errors.append(f"{claim.id}: evidence reference is required")
    return errors


def _public_surface_files(repo_root: Path) -> Iterable[Path]:
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.name in PUBLIC_SURFACE_NAMES or any(
            part in PUBLIC_SURFACE_DIR_PARTS for part in rel.parts[:-1]
        ):
            yield path


def _load_forbidden_patterns(path: Path) -> List[re.Pattern]:
    if not path.exists():
        return []
    patterns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        patterns.append(re.compile(stripped))
    return patterns


def _evidence_reference_resolves(repo_root: Path, ev: Evidence) -> bool:
    if ev.type in {"none", "proof", "benchmark"}:
        return True
    ref = ev.reference.split("::", 1)[0].strip()
    if not ref:
        return False
    return (repo_root / ref).exists()


def audit_claims(repo_root: Path) -> AuditReport:
    """Audit the claim ledger and public surfaces for forbidden claims."""

    report = AuditReport()
    repo_root = repo_root.resolve()
    claims_path = repo_root / "mempalace" / "evidence" / "claims.yaml"
    forbidden_path = repo_root / "mempalace" / "evidence" / "forbidden_phrases.txt"
    claims = load_claims(claims_path)
    report.claims_checked = len(claims)

    seen_ids = set()
    for claim in claims:
        if claim.id in seen_ids:
            report.errors.append(f"duplicate claim id: {claim.id}")
        seen_ids.add(claim.id)
        report.errors.extend(validate_claim(claim))
        if claim.publishable:
            for ev in claim.evidence:
                if not _evidence_reference_resolves(repo_root, ev):
                    report.errors.append(
                        f"{claim.id}: evidence reference does not resolve: {ev.reference}"
                    )

    patterns = _load_forbidden_patterns(forbidden_path)
    for path in _public_surface_files(repo_root):
        report.files_scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            report.warnings.append(f"could not read {path}: {exc}")
            continue
        rel = path.relative_to(repo_root)
        for pattern in patterns:
            if pattern.search(text):
                report.errors.append(f"forbidden phrase {pattern.pattern!r} found in {rel}")

    return report


