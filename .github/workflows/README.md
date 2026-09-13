# Continuous integration

`ci.yml` validates backend contracts, frontend tests/build, dependency advisories and the portable container/Terraform configuration. It uses read-only repository permissions and synthetic test inputs. No deployment account or model credentials are required for PR validation.

Deployment belongs to the repository operator and is described in `docs/deployment.md`. Real vulnerability reports belong in private security advisories, not public CI artifacts.
