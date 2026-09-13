# Run and deploy the portable application

The application is one HTTP service: the Angular frontend and `/api` share an
origin. It runs on Docker on your machine, an existing server, or a cloud VM.
The Terraform example manages that same container on an existing Docker host;
it does not require a particular cloud or provision a cloud account.

One application process owns the durable job worker and SQLite database. Keep
one replica and one persistent data volume. A load balancer with multiple
replicas requires a shared database and queue implementation first.

## Local Docker setup

Install Docker with Compose and [uv](https://docs.astral.sh/uv/getting-started/installation/).
The image builds the frontend itself, so Node is not required on your host.

From the repository root:

```sh
uv sync --frozen
uv run python scripts/setup-local.py
docker compose up --build -d
docker compose ps
```

Open [the local application](http://127.0.0.1:8000). The setup utility creates a
private password hash file and local settings. The explicitly selected `demo`
provider produces synthetic output to test the application without a model
account or usage charges. Select a real provider before analyzing real comments.

The container includes the `providers` dependency extra. To build a smaller
image, set `PROVIDER_EXTRAS` to one named integration extra from `pyproject.toml`
and rebuild. This chooses installed integrations; it does not choose your model.

## Select a model

Set the non-secret configuration in `.env`:

| Setting | Purpose |
| --- | --- |
| `LLM_PROVIDER` | Integration name supported by the model adapter. |
| `LLM_MODEL` | Model identifier selected by the operator. |
| `ROW_MODEL`, `SUMMARY_MODEL`, `DASHBOARD_MODEL` | Optional model overrides for individual analysis stages. |
| `LLM_PROVIDER_OPTIONS` | JSON with non-secret provider options, such as a base URL. |
| `LLM_BUDGET_USD` | Cumulative application budget; Compose defaults to 1 USD. |
| `LLM_INPUT_COST_PER_MILLION` | Operator-supplied input-token price used by the spend guard. |
| `LLM_OUTPUT_COST_PER_MILLION` | Operator-supplied output-token price used by the spend guard. |
| `LLM_MAX_CALLS` | Additional application call limit; Compose defaults to 1,000. |
| `LLM_TEMPERATURE_MODE` | Set `omit` for models that reject a temperature parameter; otherwise use `auto`. |
| `LLM_TIMEOUT_SECONDS`, `LLM_MAX_CONCURRENCY` | Bound each provider call and simultaneous model requests. |
| `LLM_MAX_PROMPT_CHARS`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_MAX_OUTPUT_CHARS` | Application limits; choose limits compatible with the selected model. |
| `APP_MAX_STORAGE_BYTES`, `APP_MAX_ACTIVE_JOBS` | Bound stored objects and active jobs; defaults are 1 GiB and eight jobs. |
| `APP_JOB_TTL_SECONDS` | Expiry for job admission; defaults to seven days. Set a separate file/backups retention policy. |
| `APP_MAX_REQUESTS_PER_MINUTE`, `APP_MAX_ANALYSES_PER_MINUTE`, `APP_MAX_REQUEST_BYTES` | HTTP admission and upload limits. |

Use the provider's current prices, context limits, and data-handling terms for
the chosen model. A local model endpoint still needs explicit configuration.
Inside a container, `localhost` refers to the container itself; use a reachable
model service address, such as another service on a private Docker network.

Write the provider credential into `.secrets/llm_api_key` using your password
manager or a local editor. The file may stay empty for the demo provider. Do not
place credentials in `.env`, image build arguments, Terraform variables, or
`LLM_PROVIDER_OPTIONS`. Compose mounts the password hash and API key as files;
the application reads `ACCESS_PASSWORD_HASH_FILE` and `LLM_API_KEY_FILE`.
Host-file permissions must allow the container's UID 10001 to read them. The
setup utility protects the parent `.secrets` directory with mode `0700`; the
individual files can be readable after Docker mounts them without letting
other host users traverse that private directory. Keep that directory private.
If you use files in a different location, apply an equivalent directory or ACL
restriction and verify the container can read them. Compose cannot remap a
file-backed secret's ownership on every platform.

After changing configuration or credentials:

```sh
docker compose up -d --force-recreate
```

Credential files and data are excluded from the image build context. The
container runs as UID/GID 10001, drops all Linux capabilities, has a read-only
root filesystem, and uses a 4 GiB memory cap, two CPU cores, and bounded process
count and log storage. The only persistent writable application location is
`/data`; `/tmp` is 512 MiB of temporary memory storage so a 100 MB input and its
output can coexist during processing. Make at least 4 GiB available to the
container host; unusually large generated outputs may need additional capacity.

## Stop processing and preserve data

To stop new model calls immediately, create the configured kill-switch file:

```sh
docker compose exec app touch /data/STOP_LLM
```

Already running provider requests can still finish. Remove the file only when
you intend to allow new requests:

```sh
docker compose exec app rm /data/STOP_LLM
```

To stop the entire application:

```sh
docker compose stop
```

`docker compose down` removes the container and network but preserves the named
data volume. **Do not add `--volumes` unless you intend to permanently delete
uploaded files, results, job history, and budget records.** Back up the volume
while the application is stopped, encrypt backups, and restrict access to them.
Apply your organization's retention policy to both live data and backups.

## Terraform on an existing Docker host

Use Terraform 1.5+ and a Docker daemon. Build the image on the destination host
or pull a reviewed release image there first. Compose and Terraform are
alternative owners of an application instance; do not point them at the same
container or volume.

```sh
docker build -t public-comment-analyzer:local .
cd infrastructure/terraform/docker
cp terraform.tfvars.example terraform.tfvars
# Edit password_hash_file to an absolute path on the Docker host.
terraform init
terraform plan
terraform apply
```

If your Docker CLI uses a named context, export
`DOCKER_CONTEXT="$(docker context show)"` before running Terraform so both tools
select the same daemon. For remote SSH connections, use `DOCKER_HOST` instead
and unset `DOCKER_CONTEXT` if it would override the host.

For real model access, add the non-secret model configuration and a credential
file mapping to `terraform.tfvars`:

```hcl
configuration = {
  LLM_PROVIDER                = "your-selected-integration"
  LLM_MODEL                   = "your-selected-model"
  LLM_BUDGET_USD              = "1.00"
  LLM_INPUT_COST_PER_MILLION   = "your-current-input-price"
  LLM_OUTPUT_COST_PER_MILLION  = "your-current-output-price"
  LLM_MAX_CALLS               = "1000"
}

secret_files = {
  LLM_API_KEY_FILE = "/absolute/path/on/docker-host/to/llm_api_key"
}
```

Terraform receives file paths and never reads secret contents. Configuration,
paths, container metadata, and host information can still enter Terraform
state; protect state and saved plans and keep them out of git. The dependency
lock file is committed and safe to share. See [Terraform's sensitive-data
guidance](https://developer.hashicorp.com/terraform/language/manage-sensitive-data).

For a remote host, use an authenticated Docker connection such as
`DOCKER_HOST=ssh://operator@host.example`. Secret-file paths refer to that host,
not the machine running Terraform. Never expose an unauthenticated Docker TCP
socket. Terraform returns a loopback URL on the Docker host; use an SSH tunnel
to reach it from your workstation.

The data volume has `prevent_destroy = true`. A broad `terraform destroy` is
intentionally blocked until an operator explicitly decides how to preserve or
dispose of the data. Stop the container using Docker when you only need to
pause service.

## Expose a hosted instance

The supplied configuration publishes only to `127.0.0.1`. For remote users,
place a trusted HTTPS reverse proxy on the host in front of port 8000. Add the
external hostname to `APP_ALLOWED_HOSTS` in Compose or `allowed_hosts` in
Terraform, retaining `127.0.0.1` for the container health check. Forward the
original `Host` header and preserve the `/api` paths. If the proxy is in a
separate container, use a private Docker network instead of publishing the
application port to the internet.

Terminate TLS at the proxy, enforce request-size limits and authentication
rate limits there, and restrict network access to the intended users. The
shared-password gate grants access to the whole instance; use separate
instances or an identity-aware gateway when groups need isolated datasets.
Never mount the Docker socket or an entire host credential directory. Supply
only the credentials needed to invoke the selected provider, preferably through
supported workload identity or narrowly scoped secret files.

Configure your proxy's upstream timeout for uploads and API requests. Processing
runs asynchronously, so polling requests should stay short. `/health` is the
container readiness endpoint. Raw uploads, results, prompts, and credentials
should not be included in proxy or application request logs.

For releases, build from a reviewed commit, scan the image and locked
dependencies, and deploy by immutable image digest. Test the complete upload,
preview, confirmation, result, and download flow after changing providers.
Provider integrations share an interface; output quality and service-specific
limits still require evaluation with the model you select.

## Existing deployments

Keep an existing deployment and its data under its current infrastructure
manager while validating a new portable instance. This Terraform example does
not import, alter, or delete existing cloud resources. Infrastructure imports
and live-data migrations need a separate plan, backup, reviewed resource
mapping, and a rollback path. Existing HTTP request and response behavior is
the compatibility boundary for this version.
