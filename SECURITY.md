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
- The deployed application code in this repository (backend Lambdas, frontend Angular app, CDK infrastructure).
- The default deployment configuration shipped in `infrastructure/`.

Out of scope:
- Vulnerabilities in third-party dependencies — please report those upstream and let us know via a normal advisory so we can pin/patch.
- Findings that require physical access, social engineering, or compromise of the deploying organization's AWS account.
- Issues in NC DIT's specific deployment (`[REDACTED]`) that are not reproducible against a fresh deploy of this repo. For those, contact NC DIT directly.

## Supported versions

Only the `main` branch is supported. Fixes are not back-ported to earlier tags.

## Safe harbor

Good-faith security research conducted under this policy is welcome. We will not pursue or support legal action against researchers who:
- Make a good-faith effort to avoid privacy violations, data destruction, and service disruption.
- Report through the channel above and give us reasonable time to remediate before public disclosure.
- Do not exploit a vulnerability beyond the minimum necessary to confirm it.
