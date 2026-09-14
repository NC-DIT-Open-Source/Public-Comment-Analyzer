# Public Comment Analyzer

Upload CSV or XLSX comments, define analysis columns, review sample classifications, then download the original data with draft analysis and a summary. The application uses LangChain chat models and a bounded LangGraph workflow. Models have no tools, shell, browser, or access to your job store.

The same Angular interface and API run locally or in a container on a host of your choice. Model provider, model identifiers, credentials, storage runtime, authentication secret, limits and hosting are configured outside the code. No cloud account or paid model is needed to try the workflow.

## Try it locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and supported **Node.js 24.15+ in the 24.x series** (also 22.22.3+ in 22.x or 26.x). uv installs Python 3.12 when necessary.

```sh
git clone https://github.com/NC-DIT-Open-Source/Public-Comment-Analyzer.git
cd Public-Comment-Analyzer
bash scripts/start-local.sh
```

Choose an application password when prompted, then open **http://localhost:8000**. The first run installs locked dependencies and builds the frontend. It creates `.env`, `.secrets/`, and `.data/` locally; these are excluded from git and container build contexts. Subsequent runs preserve your settings and password.

**The initial configuration explicitly selects demo mode.** It returns synthetic sample values to exercise upload, preview, confirmation, download, summary and charts. It does not analyze the meaning of comments. Demo mode is clearly labeled in the interface and output. Try [the synthetic sample](examples/comments.csv); use a categorized column with `Support` and `Concern` as example labels.

For Docker and Terraform, see [deployment](docs/deployment.md). Terraform manages the container on an existing Docker host; it does not provision every cloud's infrastructure for you.

## Use a model

Edit `.env`: set `LLM_PROVIDER` and `LLM_MODEL` to a provider and model/deployment you have access to. Put your API key in `.secrets/llm_api_key` using your editor or secret manager, or configure the provider's workload identity. The shared application password and model API key are different credentials.

| LangChain provider | Install extra | Configuration |
| --- | --- | --- |
| `openai` | `openai` | Model and API key; an OpenAI-compatible endpoint can be set in provider options |
| `azure_openai` | `openai` | Model/deployment, key or configured identity, endpoint and API version |
| `anthropic` | `anthropic` | Model and API key |
| `google_genai` | `google` | Model and key, or the integration's Vertex configuration and application credentials |
| `bedrock_converse` | `bedrock` | Regional model/inference profile and workload identity |
| `ollama` | `ollama` | Locally installed model and local server endpoint |

The startup script and default container include these integrations. Smaller installs can use `uv sync --frozen --extra openai` (substitute the needed extra). The core does not select a provider or model on your behalf. Other `init_chat_model` integrations can be installed and configured without rewriting analysis code, but each provider/model needs its own compatibility and quality evaluation.

`LLM_PROVIDER_OPTIONS` is a JSON object of trusted operator settings, such as `base_url` or `azure_deployment`. It is never accepted from uploaded comments or API callers. See [configuration](docs/configuration.md) for settings, limits and examples without fixed model identifiers.

For real analysis, set `LLM_BUDGET_USD`, `LLM_INPUT_COST_PER_MILLION`, and `LLM_OUTPUT_COST_PER_MILLION` from current provider pricing. Use rates high enough for **every** configured role model. Reservations are conservative and persisted before requests; uncertain calls are still charged against the local cap. Provider-side billing limits remain necessary to cover other applications and pricing/configuration errors.

## Behavior and review

- CSV and first-sheet XLSX input; row and column order are preserved. Existing empty-cell semantics remain unchanged.
- Open-text and categorized columns with examples and category validation.
- Categorized files with at least 50 rows pause after a 20-row preview until a person confirms.
- Row downloads become available before the aggregate summary finishes. Summary failure does not remove successful row results.
- Output is a draft decision aid. Review it before policy, legal or other consequential use; changing models can change classifications even with the same prompt.
- One application password protects one shared workspace. This is not tenant isolation or per-user authorization. Put a hosted deployment behind your identity-aware access layer and TLS.

## Development

```sh
uv sync --frozen --extra providers
uv run --frozen --extra providers python scripts/test-backend.py
cd frontend
npm ci
npm test -- --watch=false --browsers=ChromeHeadless
npm run build:prod
```

To develop the UI, run the backend on port 8000 and `npm start` in `frontend/`; the development server proxies `/api` to the local backend. Production builds use the same origin for UI and API.

The local runtime persists jobs and queued work in SQLite and stores files on disk. Use a **single application process** per data directory. After an interrupted run, paid work is not automatically replayed: the job is marked failed so an operator can decide whether to retry. Back up the entire data directory consistently and apply a retention policy.

## Deployment compatibility

The public edition no longer deploys to a maintainer-owned account when `main` changes. CI validates the portable application. Existing operators should preserve their previous cloud deployment and state in a separately maintained repository before adopting this edition. This is not an in-place CloudFormation-to-Terraform migration, and no existing resources should be destroyed or imported automatically. The [migration guide](docs/migration.md) describes the boundary.

See [security](SECURITY.md), [contributing](CONTRIBUTING.md), [license](LICENSE), and [notice](NOTICE).
