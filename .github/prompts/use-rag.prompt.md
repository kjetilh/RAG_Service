---
description: Use rag_service safely from Copilot Chat or agent mode
---

You are helping inside the `rag_service` repository.

Use this workflow:

1. Read `docs/COPILOT_RAG_USAGE.md`.
2. Check the target runtime before trusting it:

   ```bash
   python -m scripts.rag_runtime_check http://127.0.0.1:8000
   ```

3. List cases:

   ```bash
   python -m scripts.rag_cli --base-url http://127.0.0.1:8000 list-cases
   ```

4. Check case status before querying:

   ```bash
   python -m scripts.rag_cli --base-url http://127.0.0.1:8000 status dimy_docs
   ```

5. Prefer retrieve-only for source context:

   ```bash
   python -m scripts.rag_cli --base-url http://127.0.0.1:8000 retrieve dimy_docs "<question>" --top-k 8 --max-context-chars 12000
   ```

6. Use generated query only when the service should answer:

   ```bash
   python -m scripts.rag_cli --base-url http://127.0.0.1:8000 query dimy_docs "<question>" --top-k 8
   ```

Rules:

- Do not claim a corpus has content if status says it has zero documents/chunks.
- Do not cite source material unless it appears in `citations`.
- If the runtime contract check fails, say the deployed runtime is stale or incomplete.
- For CellProtocol/Binding/CellScaffold technical questions, start with `dimy_docs`.
- For cell composition and workspace recipe questions, start with `dimy_prompts`.
