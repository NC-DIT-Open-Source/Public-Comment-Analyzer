## Summary

<!-- One or two sentences on what changes and why. Focus on the why; the diff shows the what. -->

## Test plan

<!-- Bullet list of what you ran or checked. Be specific (test files, commands, manual steps). -->

- [ ] Backend: `cd backend/<lambda> && python -m pytest -v`
- [ ] Frontend: `cd frontend && npm test -- --watch=false --browsers=ChromeHeadless`
- [ ] Manual: <!-- e.g., "uploaded 50-row CSV, confirmed preview, downloaded results" -->

## Checklist

- [ ] No new secrets, credentials, account IDs, ARNs, or internal URLs in tracked files
- [ ] No widening of IAM scope (or justified in the description)
- [ ] WCAG 2.1 AA preserved for any UI changes
- [ ] Linked Jira ticket (NC contributors) or referenced issue (external contributors): #
