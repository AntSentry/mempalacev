from mempalace.evidence.claims import (
    Claim,
    Evidence,
    audit_claims,
    load_claims,
    save_claims,
    validate_claim,
)


def test_claims_round_trip(tmp_path):
    path = tmp_path / "claims.yaml"
    claim = Claim(
        id="claim_example",
        text="Example claim.",
        status="source_supported",
        evidence=[Evidence(type="source_repo", reference="README.md")],
        publishable=True,
    )
    save_claims([claim], path)
    assert load_claims(path) == [claim]


def test_validate_claim_rejects_publishable_experimental():
    claim = Claim(
        id="claim_bad",
        text="Bad claim.",
        status="experimental",
        evidence=[Evidence(type="none", reference="No evidence yet.")],
        publishable=True,
    )
    errors = validate_claim(claim)
    assert any("experimental" in err for err in errors)
    assert any("evidence type 'none'" in err for err in errors)


def test_audit_finds_forbidden_phrase(tmp_path):
    repo = tmp_path
    evidence_dir = repo / "mempalace" / "evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "claims.yaml").write_text("[]\n", encoding="utf-8")
    (evidence_dir / "forbidden_phrases.txt").write_text("(?i)forbidden phrase\n", encoding="utf-8")
    (repo / "README.md").write_text("This contains a forbidden phrase.\n", encoding="utf-8")

    report = audit_claims(repo)
    assert not report.ok
    assert any("forbidden phrase" in err for err in report.errors)


def test_audit_missing_evidence_reference_fails(tmp_path):
    repo = tmp_path
    evidence_dir = repo / "mempalace" / "evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "claims.yaml").write_text(
        """
- id: claim_missing
  text: Missing file evidence.
  status: source_supported
  evidence:
    - type: source_repo
      reference: missing.md
  publishable: true
""".lstrip(),
        encoding="utf-8",
    )
    (evidence_dir / "forbidden_phrases.txt").write_text("", encoding="utf-8")
    (repo / "README.md").write_text("Clean.\n", encoding="utf-8")

    report = audit_claims(repo)
    assert not report.ok
    assert any("does not resolve" in err for err in report.errors)

