# Contributing

Thanks for your interest in improving the Public Comment Analyzer. This is a prototype maintained by NC DIT's Office of AI & Policy. We welcome bug fixes, security hardening, accessibility improvements, and feature work.

## Ground rules

- Open an issue (or pick one off the tracker) before starting non-trivial work, so we can align on approach.
- Keep PRs focused. One logical change per PR is ideal.
- Every change must pass the existing tests; add tests for new behavior.
- The deployed app must remain WCAG 2.1 AA compliant.
- Do **not** open a public issue for a security vulnerability — see [SECURITY.md](./SECURITY.md).

## Workflow

1. Fork the repo and create a branch off `main`.
   - External contributors: `feature/short-description` or `fix/short-description`
   - NC DIT contributors: `feature/OAIP-<ticket>-short-description`
2. Make your change locally and verify tests pass (see below).
3. Open a PR against `main`. The PR title should follow the commit prefix convention.
4. CI runs backend pytest, frontend Karma, and CDK synth. All checks must pass before merge.
5. Maintainers review and merge. **Merging to `main` triggers automatic deployment to NC's AWS account.** Forks deploy to their own accounts via their own GitHub Actions secrets.

## Commit messages

Prefix the subject with the change type and (for NC contributors) a ticket number:

- `feat: ...` — new user-facing capability
- `fix: ...` — bug fix
- `vuln: ...` — security fix (use this for non-public security work; for embargoed CVEs follow [SECURITY.md](./SECURITY.md))
- `chore: ...` — tooling, deps, infra plumbing
- `docs: ...` — documentation only
- `test: ...` — tests only
- `refactor: ...` — internal restructuring with no behavior change

Examples:
- `feat: add column re-ordering to results viewer`
- `fix(OAIP-101): handle CSV files with BOM`

Focus the message on the **why**, not the what. The diff already shows what.

## Local development

You'll need Python 3.12+, Node 20+, and Docker (for SAM local). See [README.md](./README.md#local-development) for the full SAM setup. Quick path:

```bash
# Backend deps (per Lambda dir as needed)
python -m venv .venv
source .venv/bin/activate
cd backend/shared && pip install -r requirements.txt && cd ../..

# Frontend deps + Husky pre-push hook
cd frontend && npm install && cd ..

# Local API + frontend
bash scripts/start-local.sh        # terminal 1 — SAM local
cd frontend && npm start           # terminal 2 — Angular dev server
```

## Tests

Pre-push runs the same suite CI runs. To trigger it manually:

```bash
# Backend (run for each Lambda directory you touched)
cd backend/shared && python -m pytest -v
cd backend/upload_handler && python -m pytest -v
cd backend/row_processor && python -m pytest -v
cd backend/aggregate_analyzer && python -m pytest -v
cd backend/status_handler && python -m pytest -v

# Frontend
cd frontend && npm test -- --watch=false --browsers=ChromeHeadless
```

The pre-push hook (`frontend/.husky/pre-push`) runs all of the above when you `git push`. If you genuinely need to bypass it (e.g. pushing a WIP branch), use `--no-verify` sparingly and never on PRs you intend to merge.

## Style

- Python: PEP 8, 4-space indent. No need to add type hints to existing code that doesn't have them; do add them to new code.
- TypeScript/Angular: follow the patterns already in `frontend/src/app/components/`.
- Don't write comments that explain *what* the code does — well-named identifiers cover that. Comments are for *why*.

## Pull request review

- Reviewers will check: tests pass, no regressions, no new secrets/credentials in tracked files, no widening of IAM scope without justification, accessibility preserved.
- For UI changes, attach a screenshot or short screen recording.
- For security-sensitive changes (auth, CORS, input validation, IAM, prompt construction), expect deeper review.

## License

By contributing, you agree your contributions are licensed under the [Apache License 2.0](./LICENSE).
