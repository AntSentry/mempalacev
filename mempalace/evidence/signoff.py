"""Public-claim sign-off generation and verification (spec §20.4).

Every public-facing claim referenced in a public surface (README,
docs/*, CHANGELOG, landing/, public/) must have a corresponding
sign-off YAML in ``mempalace/evidence/sign_offs/``. The sign-off
records the claim id, surface path, evidence references, reviewer,
date, audit commit SHA, and the result of the forbidden-phrase scan
against the surface file at sign-off time.

A sign-off is only valid for claims that are ``publishable: true`` and
whose status is not ``experimental``. Trying to sign off an
experimental claim is the kind of mistake the protocol exists to
prevent — the generator refuses early and loudly.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml

from .claims import (
    DEFAULT_CLAIMS_PATH,
    DEFAULT_FORBIDDEN_PHRASES_PATH,
    Claim,
    _load_forbidden_patterns,
    load_claims,
)


DEFAULT_SIGNOFF_DIR = Path(__file__).with_name("sign_offs")


@dataclass(frozen=True)
class SignOff:
    """Parsed sign-off record."""

    claim_id: str
    claim_text: str
    surface: str
    status: str
    evidence_references: List[str]
    forbidden_phrase_scan: str
    audit_run: str
    approved_by: str
    date: str


def _git_head_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def _find_claim(claim_id: str, claims_path: Path) -> Claim:
    for claim in load_claims(claims_path):
        if claim.id == claim_id:
            return claim
    raise KeyError(f"claim id not found in ledger: {claim_id!r}")


def _scan_surface_for_forbidden(
    surface_path: Path, forbidden_path: Path
) -> str:
    """Return ``PASS`` or a string of matched patterns."""
    if not surface_path.exists():
        raise FileNotFoundError(f"surface file not found: {surface_path}")
    patterns: List[re.Pattern] = _load_forbidden_patterns(forbidden_path)
    if not patterns:
        return "PASS"
    text = surface_path.read_text(encoding="utf-8", errors="replace")
    hits = [p.pattern for p in patterns if p.search(text)]
    return "PASS" if not hits else "FAIL: " + ", ".join(hits)


def generate_signoff(
    claim_id: str,
    surface_path: str,
    reviewer: str,
    *,
    claims_path: Path = DEFAULT_CLAIMS_PATH,
    forbidden_path: Path = DEFAULT_FORBIDDEN_PHRASES_PATH,
    signoff_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> Path:
    """Generate a sign-off YAML for one claim on one public surface.

    Returns the path to the written YAML file. Raises ``ValueError`` if
    the claim is experimental or not publishable.
    """
    claim = _find_claim(claim_id, Path(claims_path))
    if claim.status == "experimental":
        raise ValueError(
            f"refusing to sign off experimental claim {claim_id!r}; "
            "promote to source_supported, impl, or benchmark_supported first"
        )
    if not claim.publishable:
        raise ValueError(
            f"refusing to sign off non-publishable claim {claim_id!r}; "
            "the claim ledger marks publishable: false"
        )

    surface = Path(surface_path)
    scan_result = _scan_surface_for_forbidden(surface, Path(forbidden_path))

    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    date_only = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    target_dir = Path(signoff_dir) if signoff_dir is not None else DEFAULT_SIGNOFF_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"{claim_id}__{timestamp}.yaml"

    payload = {
        "claim_text": claim.text,
        "surface": str(surface),
        "claim_ledger_id": claim.id,
        "status": claim.status,
        "evidence_references": [
            {"type": ev.type, "reference": ev.reference} for ev in claim.evidence
        ],
        "forbidden_phrase_scan": scan_result,
        "audit_run": _git_head_sha(),
        "approved_by": reviewer,
        "date": date_only,
    }
    out_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return out_path


def load_signoffs(signoff_dir: Optional[Path] = None) -> List[SignOff]:
    target_dir = Path(signoff_dir) if signoff_dir is not None else DEFAULT_SIGNOFF_DIR
    if not target_dir.exists():
        return []
    out: List[SignOff] = []
    for path in sorted(target_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        evidence_refs = []
        for ev in data.get("evidence_references") or []:
            if isinstance(ev, dict):
                ref = ev.get("reference")
                if ref:
                    evidence_refs.append(str(ref))
            elif isinstance(ev, str):
                evidence_refs.append(ev)
        out.append(
            SignOff(
                claim_id=str(data.get("claim_ledger_id") or ""),
                claim_text=str(data.get("claim_text") or ""),
                surface=str(data.get("surface") or ""),
                status=str(data.get("status") or ""),
                evidence_references=evidence_refs,
                forbidden_phrase_scan=str(data.get("forbidden_phrase_scan") or ""),
                audit_run=str(data.get("audit_run") or ""),
                approved_by=str(data.get("approved_by") or ""),
                date=str(data.get("date") or ""),
            )
        )
    return out


def find_claims_referenced(
    surface_path: Path, claims: Iterable[Claim]
) -> List[Claim]:
    """Return claims whose id appears as a token in ``surface_path``.

    The match is intentionally simple: the claim id (snake/kebab case)
    appears as a substring of the surface file's text. This is precise
    enough for our use because claim ids are unique strings that don't
    naturally collide with prose.
    """
    if not surface_path.exists():
        return []
    text = surface_path.read_text(encoding="utf-8", errors="replace")
    matched: List[Claim] = []
    for claim in claims:
        if claim.id and claim.id in text:
            matched.append(claim)
    return matched


def check_signoffs_for_surfaces(
    surfaces: Iterable[Path],
    *,
    claims_path: Path = DEFAULT_CLAIMS_PATH,
    signoff_dir: Optional[Path] = None,
) -> Dict[str, List[str]]:
    """Return ``{surface: [missing_claim_ids,...]}`` for surfaces with gaps.

    A surface "needs a sign-off" for every publishable claim id that
    appears in its text. The presence of a sign-off whose
    ``claim_ledger_id`` equals that claim id and whose ``surface``
    equals the surface path (or basename) satisfies the requirement.
    """
    claims = [c for c in load_claims(Path(claims_path)) if c.publishable]
    signoffs = load_signoffs(signoff_dir)
    missing: Dict[str, List[str]] = {}
    for surface in surfaces:
        referenced = find_claims_referenced(surface, claims)
        if not referenced:
            continue
        surface_str = str(surface)
        surface_basename = surface.name
        gaps = []
        for claim in referenced:
            satisfied = any(
                so.claim_id == claim.id
                and (
                    so.surface == surface_str
                    or so.surface.endswith(surface_basename)
                )
                for so in signoffs
            )
            if not satisfied:
                gaps.append(claim.id)
        if gaps:
            missing[surface_str] = gaps
    return missing
