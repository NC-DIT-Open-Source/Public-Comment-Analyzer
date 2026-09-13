# Contributing

Thanks for helping improve Public Comment Analyzer. Keep changes focused and explain the user problem they solve.

1. Fork the repository and create a branch.
2. Follow the local setup in the README. Use Python 3.12 through uv and a supported Node version.
3. Preserve API field names, preview confirmation, input order, empty values, safe spreadsheet exports and authentication. Add meaningful regression coverage when behavior changes.
4. Run `uv run --frozen python scripts/test-backend.py`, frontend tests and the production build. For container changes, validate Terraform and build/start the container.
5. Open a PR with the problem, resulting behavior and verification evidence. Do not include real comments, personal data, credentials, account identifiers, local state or security findings in git or public issues.

Reviewers should verify the fresh-install workflow and provider boundary, not only mocked business logic. Demo tests prove application behavior, not model quality. Live evaluations must use synthetic or approved data, a named provider/model configuration, small fixed limits and a hard budget.

Treat WCAG 2.1 AA as a release requirement. Preserve keyboard operation, visible focus, labels, status announcements, contrast, and a textual alternative to charts. AI output is always a draft for human review.

Report security concerns privately using SECURITY.md. Merging this public repo runs validation; deployments belong to each operator.
