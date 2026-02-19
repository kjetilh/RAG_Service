# Patch v5: 429 Too Many Requests hardening

This patch adds:
- Retry with exponential backoff + jitter for 429/5xx in `app/rag/generate/llm_provider.py`
- A global concurrency throttle (Semaphore) to prevent parallel LLM calls from the web UI
- Streaming endpoint now emits a structured SSE `error` event instead of crashing the stream

## Apply
Unzip into the repo root (overwrite files):

```bash
unzip -o rag_patch_v5.zip -d /path/to/rag_service_repo_plus
```

Then restart the server.

## Notes
If you still see persistent 429:
- confirm you are not running multiple tabs / multiple requests in parallel
- check your OpenAI account/project quota and rate limits
- reduce prompt size (top_k, chunk size, templates) and set realistic max output tokens
