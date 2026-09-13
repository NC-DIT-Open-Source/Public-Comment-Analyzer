# Adopting the portable edition

The HTTP workflow and file format remain compatible, but the public repository's deployment ownership changes. Preserve the previous cloud application in a private operator repository before switching development to this edition. Keep the existing production service running throughout evaluation.

1. Preserve the tracked main commit and history. Verify the copy's visibility and exact commit. Disable Actions on a new copy until its deployment identity, secrets, environment protection and trust policy are configured.
2. Repository copies do not transfer secrets, OIDC trust, branch protection, environments or cloud resources. Configure these independently through your secret manager and hosting controls. Do not write the values to git, PRs or logs.
3. Validate the preserved deployment against existing resources. A copied workflow's OIDC subject uses a different repository name; narrowly add the new subject and validate before removing the old one. Do not rotate the application's access secret as a side effect.
4. Test the portable edition in a separate data directory/container using synthetic data. Check upload, preview, confirmation, downloads, summaries, charts and the intended provider/model. Preserve your classification examples and compare outputs.
5. Cut over traffic only after the operator approves the concrete deployment. Keep a rollback path to the original service. This PR does not perform that cutover.

Do not point a fresh Terraform configuration at live CloudFormation-managed resources and assume ownership transfers. Terraform here manages a new container on a pre-existing host. Storage migration requires a separate verified export/import with preserved object keys, job records, retention, permissions and backups.

The portable runtime stores its data on a mounted volume. Run that container on any compatible host; provider-specific identity, ingress, volumes and backups remain operator configuration. The public application has no cloud SDK dependency outside optional LangChain model integrations.
