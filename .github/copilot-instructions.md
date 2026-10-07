# Repository instructions for Copilot

This repository contains `rag_service`, a FastAPI/PostgreSQL/pgvector RAG service.

When asked to use the RAG functionality:

- Start with `docs/COPILOT_RAG_USAGE.md`.
- Prefer `python -m scripts.rag_cli ... retrieve` when you need source context without generation.
- Use `python -m scripts.rag_runtime_check ...` before assuming a deployed runtime matches the working tree.
- Do not invent corpus contents. Check case status first.
- For CellProtocol/Binding/CellScaffold questions, prefer the `dimy_docs` case.
- For cell composition/workspace/prompt questions, prefer the `dimy_prompts` case.
- If `status` reports missing source types, empty corpus, or legacy schema warnings, report that clearly before proposing implementation work.

Important local files:

- `config/rag_cases.yml`: active RAG cases.
- `docs/RAG_CELLPROTOCOL_ACCESSIBILITY_REPORT.md`: current integration assessment.
- `docs/COPILOT_RAG_USAGE.md`: practical RAG usage for agents.
- `docs/RAG_SERVICE_API_ENDPUNKTER.md`: route inventory.
- `app/api/routes_chat.py`, `app/api/routes_cell.py`, `app/api/routes_research.py`: consumer APIs.
- `app/rag/pipeline.py`: query/retrieve pipeline.
