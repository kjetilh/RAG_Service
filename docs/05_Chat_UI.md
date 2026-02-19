# Chat UI (streaming)

Når serveren kjører, åpne:

- Chat-side: `http://localhost:8000/`
- Swagger UI: `http://localhost:8000/docs`

Chat-siden bruker `POST /v1/chat/stream` og parser SSE-events:
- `citations` (JSON array)
- `delta` (JSON {"delta":"..."})
- `done`

Statisk fil ligger i `app/static/chat.html` og serveres via `app/api/routes_ui.py`.
