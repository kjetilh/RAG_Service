# Prompt for ChatGPT Pro: RAG -> CellProtocol review

Denne prompten er laget for a brukes mot ChatGPT Pro som en kontrollert second opinion pa status og neste steg.

Maalet er ikke a fa generisk RAG-rad, men a fa en streng vurdering av integrasjonsarkitekturen mellom `rag_service`, `CellScaffold` og `CellProtocol`.

## Bruksmate

1. Lim inn prompten under.
2. Lim eventuelt inn korte kodeutdrag fra disse filene hvis modellen trenger det:
   - `app/api/routes_cell.py`
   - `docs/CELLS_EMBEDDING.md`
   - `docs/CELLPROTOCOL_RAG_STATUS.md`
   - `Sources/App/Controllers/VaporRAGMVP.swift`
   - `Sources/CellBase/CellConfiguration/CellConfiguration.swift`
   - `Sources/CellBase/Skeleton/SkeletonDescription.swift`
3. Be modellen holde seg til diff-niva og repo-ansvar, ikke generisk teori.

## Prompt

```text
ROLE: Architecture Review Agent

Objective:
Evaluate the current status of our RAG platform and produce a precise implementation plan for making RAG functionality available through CellProtocol / CellConfiguration / skeleton, without collapsing responsibilities across repositories.

Current status:

1. `rag_service` is already relatively advanced.
It has:
- doc lifecycle/versioning
- strict rag case loader
- deterministic planner and stable trace
- tombstone sync with anti-thrash batching
- evaluation gate
- `/v1/query` plus backward-compatible `/v1/chat`
- cell-aware RBAC endpoints:
  - `GET /v1/cell/cases`
  - `POST /v1/cell/cases/{case_id}/query`
  - `GET /v1/cell/cases/{case_id}/corpus`
  - `GET /v1/cell/cases/{case_id}/links`
  - `GET /v1/cell/cases/{case_id}/documents/{doc_id}/links`
  - members admin endpoints
- interview collective summary is implemented locally but not yet committed

2. `CellScaffold` already has a RAG MVP proxy/web layer.
It can proxy:
- cases
- query
- corpus
- links
- interview collective summary
- members

But this currently lives as app-specific web/proxy code, not as a first-class cell contract loaded through CellConfiguration.

3. `CellProtocol` already has the right primitives:
- `CellConfiguration`
- `CellReference`
- `setKeysAndValues`
- skeleton components such as `Text`, `TextField`, `TextArea`, `Button`, `List`, `Section`, `ScrollView`

What is missing is a standard RAG cell contract, not low-level UI primitives.

Core architectural constraint:
- We do NOT want to move the RAG engine itself into CellProtocol.
- We DO want RAG functionality to be accessible via CellConfiguration with skeleton-driven UI.
- `rag_service` should remain the external backend.
- `CellScaffold` should host the runtime adapter cell(s).
- `CellProtocol` should only absorb reusable contract-level or rendering-level abstractions.

Desired outcome:
Users should be able to load a RAG tool as a normal cell/configuration, not only through a special `/rag-mvp` web page.

Please answer in these sections:

1. Current-state assessment
- Is the architecture direction sound?
- What is already solved?
- What is the real missing layer?

2. Repository responsibility split
- What should stay in `rag_service`?
- What should be implemented in `CellScaffold`?
- What, if anything, belongs in `CellProtocol`?

3. Contract-first proposal
- Propose a minimal `RAGGatewayCell` or alternative cell model
- Define recommended keypaths, request payloads, state payloads, and error behavior
- Keep it compatible with existing CellConfiguration and skeleton concepts

4. Implementation plan
- Produce a surgical diff-level plan
- Group the work into small commits/PRs
- Separate work per repo
- Prefer the smallest viable first iteration

5. Risk review
- What are the main design mistakes we should avoid?
- What should we NOT put in CellProtocol yet?
- Where are we likely to over-engineer?

6. Verification plan
- Unit tests
- contract tests
- smoke tests
- one end-to-end scenario where a user loads and uses the RAG tool from ConfigurationCatalog

Important constraints:
- Do not suggest moving backend retrieval/planner/index code into CellProtocol.
- Do not give a generic “microservices best practices” answer.
- Do not rewrite the backend plan from scratch unless there is a concrete flaw.
- Focus on the integration seam between service, scaffold runtime, and cell contract.
- Be explicit about what is an evidence-based observation from the supplied status versus your own inference.

Deliverable style:
- Concise
- Technically opinionated
- Diff-level where possible
- No fluff
```
