# Developer setup

This page covers local environment setup plus the pre-commit gates that
guard public-claim discipline.

## One-time setup

```bash
uv sync --extra dev          # recommended
# or: pip install -e ".[dev]"
```

## Pre-commit hooks

MemPalace ships a pre-commit hook that runs three fast gates before a
commit lands:

1. `mempalace claims audit` — verifies the claim ledger is well-formed
   and that no forbidden phrase (see
   `mempalace/evidence/forbidden_phrases.txt`) appears in any
   public-facing file (README, CHANGELOG, `docs/`, `landing/`, `public/`).
2. `ruff check .` — lint.
3. A fast pytest subset — `tests/test_claims.py`,
   `tests/test_ablation_runner.py`,
   `tests/test_benchmark_adapters.py`, `tests/test_signoff.py`.

### Install the hook

```bash
scripts/install_git_hooks.sh
```

The installer symlinks every file in `.git-hooks/` into `.git/hooks/`.
It refuses to overwrite a hand-written hook that is not already a
symlink — remove the real file first if you want the MemPalace hook in
its place.

### Skip in an emergency

```bash
git commit --no-verify
```

Use this sparingly. The claims audit is the gate that keeps unsupported
public claims out of the repository; bypassing it should be a
deliberate, one-off choice, not a habit. If you bypass it, the next
maintainer is responsible for running `mempalace claims audit` and
fixing whatever the bypass let through.

## Adding a public claim

The full protocol lives in `MEMPALACE_TOPOLOGY_SPEC.md` §20.4. Short
version:

1. Add the claim to `mempalace/evidence/claims.yaml` with a stable id,
   status, and evidence references.
2. Reference the claim id in the public-facing file (README, CHANGELOG,
   `docs/release/*`, etc.).
3. Generate a sign-off:

   ```bash
   mempalace claims signoff <claim_id> \
       --surface <path/to/public/file> \
       --reviewer "<your name>"
   ```

4. Run the strict audit:

   ```bash
   mempalace claims audit --require-signoffs
   ```

Claims with status `experimental` or `publishable: false` cannot be
signed off — promote them to `source_supported`, `impl`, or
`benchmark_supported` first, with the corresponding evidence committed.

## Sealed evaluation runs

See `docs/PHASE_8_9_10_GATES.md` for the full protocol. The runner
enforces these protections by default:

- `--seal` only valid for `--set test`.
- A prior contamination-log entry on the same dataset SHA + commit SHA
  refuses the run.
- `--unseal-emergency <reason>` allows an override only with a reason
  string of at least 40 characters; the reason is recorded in
  `mempalace/evidence/contamination_log.yaml`.
