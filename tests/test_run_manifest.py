from eval.run_manifest import build_manifest


def test_run_manifest_contains_required_fields():
    manifest = build_manifest(configuration={"row": "A0"})
    assert {"timestamp", "git_sha", "dataset_sha", "configuration", "env_flags"} <= set(manifest)
