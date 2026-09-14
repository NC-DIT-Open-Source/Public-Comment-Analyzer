# Agent guide — Public Comment Analyzer

This public edition is provider-neutral. The Angular frontend and Python handlers preserve the established HTTP workflow. LangChain/LangGraph handle model access; `backend/shared/runtime.py` defines storage, job and task interfaces. The shipped FastAPI runtime uses SQLite and local files on any compatible host. Additional persistence adapters require implementation and contract tests.

## Development

- Use Python 3.12 with `uv sync --frozen --extra providers`; never use system Python to install dependencies.
- Use Node 24.15+ in 24.x, 22.22.3+ in 22.x or 26.x. Preserve concurrent dependency updates and the lockfiles.
- Run `uv run --frozen --extra providers python scripts/test-backend.py`; handler suites intentionally run in separate processes because legacy modules share the name `handler`.
- Run frontend tests, production build and any relevant container/Terraform validation.
- Define a concrete outcome and test real dependency boundaries before claiming success. Never represent demo tests as proof of model quality or cloud deployment.

## Compatibility and security

- Preserve `/api/auth/validate`, upload, process, status, preview-confirm, results and dashboard contracts.
- Preserve preview/confirmation, input row/column order, empty values, category examples, partial errors and downloads while summary generation is pending or failed.
- Credentials stay outside git and the browser. Shared access password is memory-only in AuthService. Authentication fails closed; never add a disabled-auth mode as a shortcut.
- No hardcoded model identifiers, production hosts, account IDs, passwords, credential hashes or private comment data in code or examples. Local `.env`, `.secrets`, `.data`, Terraform state/plans and test evidence are not source files.
- Only operators choose provider/model/endpoints. Never accept tools, callbacks, arbitrary code or provider configuration from an API request or uploaded content.
- Treat comments and model output as untrusted. Preserve system/data separation, strict output validation, spreadsheet formula guards (including headers), Angular sanitization, CSP and bounded work.
- Keep persistent conservative budgets, finite retries, bounded concurrency and the kill switch. Missing prices/limits must never allow unbounded paid inference.
- Run one local app process per data directory. Interrupted paid jobs fail visibly rather than being automatically replayed.
- Treat WCAG 2.1 AA as a release requirement; model output is a draft for human review.
- Do not put real vulnerability findings in git or public PR text. Use private security advisories.

## Deployment

The public repository validates changes; it does not deploy into a maintainer-owned cloud account. Use the documented Docker/Terraform path. Existing cloud deployments and their secrets/state belong to a separately maintained operator repository. Never destroy/import cloud resources or activate a copied deployment workflow as an incidental part of a refactor.
