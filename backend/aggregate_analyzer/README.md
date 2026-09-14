# Aggregate analysis

Reads completed row results through the configured object store, summarizes bounded chunks with the configured LangChain model, and saves the draft summary through the job store. `SUMMARY_MODEL` can override the default model. API behavior remains `/api/results/{jobId}` with `downloadUrl` and nullable `aggregateAnalysis`; `analysisStatus` reports `generating` or `failed` while row downloads remain available.

See the root README for installation, configuration and tests.
