# Configuration

Configuration belongs to the deployment operator. API requests and uploaded content cannot choose models, integrations, endpoints, credentials or tool capabilities. Use `.env` for non-secret local settings and mounted files or provider-native identity for secrets. Never put model credentials in the browser.

Row and dashboard prompts use the selected comment column and defined analysis columns. Unselected source metadata stays in the original/exported file. Any personal data contained in the selected comments still goes to the configured provider; use data approved for that deployment.

## Hosting, authentication and persistence

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_RUNTIME` | `local` | Persistent filesystem/SQLite runtime, usable on any compatible host |
| `APP_DATA_DIR` | `.data` | Private data directory: uploads, results, job/task state, signing key and budget ledger |
| `APP_STATIC_DIR` | `frontend/dist/public-comment-app/browser` | Built UI directory; container uses `/app/static` |
| `APP_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | Accepted Host names; set the real host before hosting publicly |
| `ALLOWED_ORIGIN` | absent | Optional exact cross-origin browser origin; same-origin setup needs none; wildcard is rejected |
| `ACCESS_PASSWORD_HASH_FILE` | required for normal setup | File holding the bcrypt hash of the shared application password |
| `LOCAL_PASSWORD_HASH` | absent | Compatibility alternative to the file; never commit the value |
| `APP_MAX_STORAGE_BYTES` | 1073741824 | Object-store quota (1 GiB), independent of host disk quota |
| `APP_MAX_ACTIVE_JOBS` | 8 | Bound concurrent/queued/awaiting-preview jobs |
| `APP_JOB_TTL_SECONDS` | 604800 | Expire unfinished jobs after seven days, releasing admission slots; uploaded data is preserved |
| `APP_MAX_REQUEST_BYTES` | 105906176 | HTTP request bound, including multipart overhead; file content limit is 100 MiB |
| `APP_MAX_REQUESTS_PER_MINUTE` | 180 | Requests per client in the app process |
| `APP_MAX_ANALYSES_PER_MINUTE` | 12 | Global expensive request admission |

Authentication is a shared bcrypt password for one workspace; it is not per-user authorization. Put a hosted deployment behind TLS and your identity-aware ingress. Configure its identity provider outside this application, and keep the application's password in place. Do not expose the application and then disable authentication to make an ingress work.

The runtime implements `ObjectStore`, `JobStore` and `TaskRuntime` protocols. Its shipped implementation uses a mounted filesystem and SQLite; it does not pretend an environment variable provisions a different cloud database. Deploy the container using your cloud's persistent volume. Replacing persistence with managed services is a separate adapter implementation and contract-testing task.

Run one application process per data directory. Startup recovery fails interrupted paid work visibly instead of replaying it. A preview can be canceled through `POST /api/process/{jobId}/cancel`; the interface uses this when you cancel and revise. Expired/canceled jobs keep original files until your retention process removes them. Plan backup and retention for the entire private data directory, including the budget ledger.

## Model selection

Set `LLM_PROVIDER` explicitly. `demo` performs no AI inference and labels placeholder outputs. Real providers require `LLM_MODEL`; `ROW_MODEL`, `SUMMARY_MODEL`, and `DASHBOARD_MODEL` can select different model/deployment identifiers for each role.

Use `LLM_API_KEY_FILE` for a mounted API key, or `LLM_API_KEY` when your host injects environment secrets. Do not set both. An empty mounted file means no API key (useful for demo, local servers or workload identity); a configured missing/unreadable file is an error. Provider-native credential environment variables and workload identities are handled by the integration.

`LLM_PROVIDER_OPTIONS` accepts an allowlist of connection and identity settings. Examples:

```dotenv
# OpenAI-compatible local server; install the openai extra.
LLM_PROVIDER=openai
LLM_PROVIDER_OPTIONS={"base_url":"http://127.0.0.1:8080/v1"}

# Azure deployment; also supply your approved endpoint/API version.
# LLM_PROVIDER=azure_openai
# LLM_PROVIDER_OPTIONS={"azure_endpoint":"https://YOUR-RESOURCE.openai.azure.com","azure_deployment":"YOUR-DEPLOYMENT","api_version":"YOUR-SUPPORTED-VERSION"}

# Ollama; pull your chosen model separately and set LLM_MODEL to its identifier.
# LLM_PROVIDER=ollama
# LLM_PROVIDER_OPTIONS={"base_url":"http://127.0.0.1:11434"}
```

Inside Docker, loopback points to the container itself. Configure a reachable local model endpoint (for example, the host gateway supported by your Docker installation) or run the model server on a private container network. Use HTTPS for non-local endpoints. No model identifier, API version or hosted endpoint in an example is a claim of current model availability.

`LLM_TEMPERATURE_MODE=auto` preserves zero temperature for categorized analysis and omits it for open text. Use `omit` for models that reject this parameter. Changing provider/model can change classifications: test against your accepted examples before relying on a new configuration. [LangChain's model documentation](https://docs.langchain.com/oss/python/langchain/models) covers the supported integration interfaces.

## Limits, estimates and stopping work

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_BUDGET_USD` | required for real providers | Positive persistent deployment budget; setup example is $1 |
| `LLM_INPUT_COST_PER_MILLION` | required for real providers | Current conservative input USD rate across every selected role model; zero allowed for free/local inference |
| `LLM_OUTPUT_COST_PER_MILLION` | required for real providers | Current conservative output USD rate across every role, including applicable reasoning/other charges |
| `LLM_MAX_CALLS` | 10000; setup 1000 | Persistent call cap across jobs and retries |
| `LLM_MAX_CONCURRENCY` | 4 | 1–32 outstanding model calls, including calls still running after a local timeout |
| `LLM_TIMEOUT_SECONDS` | 120 | Per-call wait/transport limit, maximum 600 seconds |
| `LLM_MAX_PROMPT_CHARS` | 200000 | Reject oversized prompts before inference |
| `LLM_MAX_OUTPUT_TOKENS` | 4096 | Upper bound on requested output tokens |
| `LLM_MAX_OUTPUT_CHARS` | 65536 | Reject oversized returned text |
| `LLM_ENABLED` | true | Set false and restart to disable inference |
| `LLM_KILL_SWITCH_FILE` | configured by setup | Creating this file blocks additional calls immediately |

Startup constructs each distinct role's provider integration without inference, so invalid configuration, missing packages and unresolved identity fail before jobs start. `POST /api/process` parses the uploaded file and calculates the first-pass row reservation from the exact prompts before it creates or queues a job. Its additive `inferenceEstimate` reports those conservative row reservations, a clearly labeled minimum summary reservation, remaining dollars/calls and the maximum call count with retries. A `409 INFERENCE_LIMIT` response rejects a file when the remaining budget cannot cover even the minimum successful pass. The check does not require enough budget for every possible retry. Future summary input is unknown, and concurrent jobs can consume the balance, so the estimate does not guarantee completion or represent a billing quote.

The preflight makes no model requests and returns no comment text, credentials or provider identifiers. During graceful shutdown, a process-local gate stops newly queued or retried provider requests; in-flight calls may still finish. Restart clears this temporary gate but preserves the operator kill switch and budget ledger.

Before each model request, the application estimates a conservative upper reservation from UTF-8 prompt bytes, system-message overhead and requested output, then atomically checks the remaining budget/call limit. Every retry is reserved separately. Failed or uncertain calls are not refunded. `budget_status()` in the inference module reports call count and reserved USD, without prompts or credentials. Reservations are not provider billing measurements.

These limits survive restart in `APP_DATA_DIR`. Deleting the ledger resets the guard; do not reset it to hide usage. Use provider billing controls as well: other apps, an incorrect price, provider-specific tokenization or additional charges can exceed an application estimate. Set rates to cover the most expensive role and all charged token types. A local timeout does not prove that a remote provider canceled the request.

For the local setup, create `.data/STOP_LLM` to stop new requests. In Compose, use `docker compose exec app touch /data/STOP_LLM`. Calls already submitted may finish. Inspect failed jobs and provider billing before removing the switch or starting replacement work.

File parsing also bounds expanded XLSX content to 256 MiB, 50,000 data rows, 1,000 columns and 2,000,000 cells. Duplicate headers and analysis names that would overwrite source columns are rejected so data is not silently lost. Original spreadsheet values and headers retain formula neutralization when exported.
