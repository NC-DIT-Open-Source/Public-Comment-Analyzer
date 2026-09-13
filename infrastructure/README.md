# Portable deployment

Use [Docker Compose or Terraform](../docs/deployment.md) to run the same application image on a host of your choice. Terraform examples live in `terraform/docker/` and configure an existing Docker host.

Cloud-native storage and task backends are adapter concerns; the default container uses a persistent volume and SQLite. Existing cloud deployments must follow the [migration guidance](../docs/migration.md) before changing ownership or state.
