# Security Policy

## Reporting a vulnerability

**Do not open a public GitHub issue for a security vulnerability.**

Report it privately via GitHub Security Advisories:

1. Go to the **Security** tab of this repository.
2. Click **Report a vulnerability** (or use the [GitHub-hosted form](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)).
3. Include:
   - A description of the issue and the impact.
   - Steps to reproduce (or a proof-of-concept).
   - The version, branch, or commit you tested against.
   - Your suggested fix, if any.

We aim to acknowledge reports within **5 business days** and provide a status update within **15 business days**. Coordinated disclosure timelines depend on severity and the complexity of the fix; we will work with you on a public-disclosure date.

## Scope

In scope:
- The deployed application code in this repository (Python runtime, Angular frontend, container and Terraform configuration).
- The default deployment configuration shipped in `infrastructure/`.

Out of scope:
- Vulnerabilities in third-party dependencies — please report those upstream and let us know via a normal advisory so we can pin/patch.
- Findings that require physical access, social engineering, or compromise of the deploying organization's hosting account.
- Issues in a specific operator's deployment that are not reproducible against a fresh deploy of this repo. For those, contact the operator of that deployment directly.

## Supported versions

Only the `main` branch is supported. Fixes are not back-ported to earlier tags.

## Safe harbor

Good-faith security research conducted under this policy is welcome. We will not pursue or support legal action against researchers who:
- Make a good-faith effort to avoid privacy violations, data destruction, and service disruption.
- Report through the channel above and give us reasonable time to remediate before public disclosure.
- Do not exploit a vulnerability beyond the minimum necessary to confirm it.

## AI and deployment controls

Model input is untrusted, including comments, examples, context and earlier model output. A separate system policy, bounded workflow and strict output schemas reduce risk; prompt framing cannot guarantee that a model ignores every injected instruction. Models have no tools or credentials in prompts. Tracing is disabled in the inference path. Review generated judgments before consequential use.

The application bounds uploads, expanded workbooks, rows/cells, prompts, outputs, requests, concurrency and model calls. A persistent ledger reserves conservative cost before requests and does not refund uncertain attempts. Stop additional inference with `LLM_ENABLED=false` or the configured kill-switch file. Use provider-side quotas and billing limits as well; operator prices must cover all selected models and charges.

Protect hosted deployments with TLS and an identity-aware access layer. The shared password protects a single shared workspace, not separate users or tenants. Secrets are mounted or supplied by the host; never commit them or bake them into images. Protect persistent data and backups, define retention, and monitor failed jobs and budget exhaustion. Signed downloads are scoped, short-lived capabilities; treat the full URLs as sensitive.

The controls follow the [OWASP guidance on bounded consumption](https://genai.owasp.org/llmrisk/llm102025-unbounded-consumption/) and [LangChain security guidance](https://docs.langchain.com/oss/python/security-policy). Security depends on the selected provider, model, data permissions and deployment configuration; swapping a model requires renewed evaluation.
