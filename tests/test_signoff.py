"""Tests for the public-claim sign-off generator + audit hook.

Spec §20.4 requires every public-facing claim to ship with a sign-off
YAML in ``mempalace/evidence/sign_offs/``. The generator refuses to
sign off experimental or non-publishable claims; the audit's
``--require-signoffs`` flag fails when a surface file references a
publishable claim id with no matching sign-off.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import yaml

from mempalace.evidence.signoff import (
    check_signoffs_for_surfaces,
    generate_signoff,
    load_signoffs,
)


PUBLISHABLE_CLAIM_ID = "claim_demo_publishable"
EXPERIMENTAL_CLAIM_ID = "claim_demo_experimental"
NONPUBLISHABLE_CLAIM_ID = "claim_demo_nonpublishable"


@pytest.fixture
def ledger(tmp_path):
    """Write a minimal claims.yaml for sign-off tests."""
    path = tmp_path / "claims.yaml"
    yaml_text = yaml.safe_dump(
        [
            {
                "id": PUBLISHABLE_CLAIM_ID,
                "text": "Demo publishable claim text.",
                "status": "source_supported",
                "evidence": [
                    {"type": "source_repo", "reference": "README.md"},
                ],
                "publishable": True,
            },
            {
                "id": EXPERIMENTAL_CLAIM_ID,
                "text": "Demo experimental claim text.",
                "status": "experimental",
                "evidence": [{"type": "none", "reference": "pending"}],
                "publishable": False,
            },
            {
                "id": NONPUBLISHABLE_CLAIM_ID,
                "text": "Demo non-publishable claim.",
                "status": "impl",
                "evidence": [
                    {"type": "unit_test", "reference": "tests/test_x.py"},
                ],
                "publishable": False,
            },
        ],
        sort_keys=False,
    )
    path.write_text(yaml_text, encoding="utf-8")
    return path


@pytest.fixture
def forbidden(tmp_path):
    path = tmp_path / "forbidden_phrases.txt"
    path.write_text("(?i)dramatically improves\n", encoding="utf-8")
    return path


@pytest.fixture
def surface_file(tmp_path):
    f = tmp_path / "README.md"
    f.write_text(
        f"This README references {PUBLISHABLE_CLAIM_ID} in a benign way.\n",
        encoding="utf-8",
    )
    return f


@pytest.fixture
def signoff_dir(tmp_path):
    return tmp_path / "sign_offs"


def test_generator_refuses_experimental_claim(
    ledger, forbidden, surface_file, signoff_dir
):
    with pytest.raises(ValueError) as exc_info:
        generate_signoff(
            EXPERIMENTAL_CLAIM_ID,
            str(surface_file),
            "Marcus Webb",
            claims_path=ledger,
            forbidden_path=forbidden,
            signoff_dir=signoff_dir,
        )
    assert "experimental" in str(exc_info.value)


def test_generator_refuses_nonpublishable_claim(
    ledger, forbidden, surface_file, signoff_dir
):
    with pytest.raises(ValueError) as exc_info:
        generate_signoff(
            NONPUBLISHABLE_CLAIM_ID,
            str(surface_file),
            "Marcus Webb",
            claims_path=ledger,
            forbidden_path=forbidden,
            signoff_dir=signoff_dir,
        )
    assert "publishable: false" in str(exc_info.value)


def test_generator_writes_valid_yaml(
    ledger, forbidden, surface_file, signoff_dir
):
    out_path = generate_signoff(
        PUBLISHABLE_CLAIM_ID,
        str(surface_file),
        "Marcus Webb",
        claims_path=ledger,
        forbidden_path=forbidden,
        signoff_dir=signoff_dir,
        now=datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert out_path.exists()
    payload = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert payload["claim_ledger_id"] == PUBLISHABLE_CLAIM_ID
    assert payload["surface"] == str(surface_file)
    assert payload["approved_by"] == "Marcus Webb"
    assert payload["status"] == "source_supported"
    assert payload["forbidden_phrase_scan"] == "PASS"
    assert payload["date"] == "2026-05-15"
    assert isinstance(payload["evidence_references"], list)
    assert payload["evidence_references"][0]["type"] == "source_repo"


def test_generator_flags_forbidden_phrase_in_surface(
    ledger, forbidden, tmp_path, signoff_dir
):
    bad_surface = tmp_path / "bad_README.md"
    bad_surface.write_text(
        f"{PUBLISHABLE_CLAIM_ID} dramatically improves everything!\n",
        encoding="utf-8",
    )
    out_path = generate_signoff(
        PUBLISHABLE_CLAIM_ID,
        str(bad_surface),
        "Marcus Webb",
        claims_path=ledger,
        forbidden_path=forbidden,
        signoff_dir=signoff_dir,
    )
    payload = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert payload["forbidden_phrase_scan"].startswith("FAIL")


def test_audit_with_require_signoffs_fails_when_missing(
    ledger, surface_file, signoff_dir
):
    gaps = check_signoffs_for_surfaces(
        [surface_file],
        claims_path=ledger,
        signoff_dir=signoff_dir,
    )
    assert str(surface_file) in gaps
    assert PUBLISHABLE_CLAIM_ID in gaps[str(surface_file)]


def test_audit_with_require_signoffs_passes_when_present(
    ledger, forbidden, surface_file, signoff_dir
):
    generate_signoff(
        PUBLISHABLE_CLAIM_ID,
        str(surface_file),
        "Marcus Webb",
        claims_path=ledger,
        forbidden_path=forbidden,
        signoff_dir=signoff_dir,
    )
    gaps = check_signoffs_for_surfaces(
        [surface_file],
        claims_path=ledger,
        signoff_dir=signoff_dir,
    )
    assert gaps == {}


def test_load_signoffs_returns_records(
    ledger, forbidden, surface_file, signoff_dir
):
    generate_signoff(
        PUBLISHABLE_CLAIM_ID,
        str(surface_file),
        "Marcus Webb",
        claims_path=ledger,
        forbidden_path=forbidden,
        signoff_dir=signoff_dir,
    )
    records = load_signoffs(signoff_dir)
    assert len(records) == 1
    assert records[0].claim_id == PUBLISHABLE_CLAIM_ID
    assert records[0].approved_by == "Marcus Webb"


def test_load_signoffs_missing_dir_returns_empty(tmp_path):
    assert load_signoffs(tmp_path / "nope") == []


def test_unknown_claim_id_raises_keyerror(
    ledger, forbidden, surface_file, signoff_dir
):
    with pytest.raises(KeyError):
        generate_signoff(
            "claim_does_not_exist",
            str(surface_file),
            "Marcus Webb",
            claims_path=ledger,
            forbidden_path=forbidden,
            signoff_dir=signoff_dir,
        )
