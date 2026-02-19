
# RAG‑tjenesten – dokumentert flyt og informasjonsstrøm

Dette dokumentet beskriver **hele livsløpet til data og forespørsler** i RAG‑tjenesten:  
fra dokumenter ingestes, via lagring i lokal database, til hvordan kontekst pakkes og brukes i prompten mot LLM – inkludert streaming tilbake til nettleser.

---

## 1. Oversikt (høy‑nivå)

Tjenesten består av fem hovedfaser:

1. **Ingest (offline / batch)**
2. **Persistens (Postgres + pgvector)**
3. **Retrieval (runtime, per spørsmål)**
4. **Context packing & prompt‑bygging**
5. **LLM‑kall + streaming tilbake til klient**

```
PDF/Docx/MD
   ↓
Ingest → Chunking → Embeddings
   ↓
Postgres (documents / chunks / embeddings)
   ↓
HTTP request (/v1/chat/stream)
   ↓
Hybrid retrieval (vector + lexical)
   ↓
pack_context()
   ↓
compose_answer()
   ↓
LLM (OpenAI‑kompatibel API)
   ↓
SSE stream → Browser UI
```

---

## 2. Ingest‑fasen (dokument → database)

### 2.1 Input
- PDF / DOCX / TXT / MD
- Typisk via:
```bash
python -m scripts.ingest_folder --path ../papers --source-type paper
```

### 2.2 Steg i ingest

1. **Fil lastes**
2. **Råtekst ekstraheres**
3. **Tekst renses**
4. **Chunking**
5. **Metadata‑ekstraksjon**
6. **Embedding**
7. **Persistens**

### 2.3 Hva lagres i databasen

#### documents‑tabell
Én rad per dokument:

| Felt | Beskrivelse |
|----|----|
| doc_id | Stabil ID |
| title | Tittel |
| author | Forfatter |
| year | År |
| source_type | paper / report |
| content_hash | Deduplisering |

#### chunks‑tabell
Én rad per chunk:

| Felt | Beskrivelse |
|----|----|
| chunk_id | Unik ID |
| doc_id | Referanse |
| content | Chunk‑tekst |
| content_tsv | Fulltekstindeks |

#### embeddings‑tabell
Én rad per chunk:

| Felt | Beskrivelse |
|----|----|
| chunk_id | FK |
| embedding | pgvector‑vektor |

---

## 3. Runtime‑flyt (spørsmål fra bruker)

### 3.1 HTTP request
Browser sender:
```http
POST /v1/chat/stream
```
Starter en **SSE‑stream**.

---

## 4. Retrieval‑fasen

### 4.1 Query‑forberedelse
- Spørsmål embeddes

### 4.2 Hybrid retrieval
- Vector search (pgvector)
- Lexical search (Postgres FTS)

### 4.3 Sammenslåing
Resultater → `RetrievedChunk`.

---

## 5. Context packing (`pack_context`)

### 5.1 Input
- Liste av `RetrievedChunk`

### 5.2 Output
`PackedContext`:
- `context_text`
- `citations`
- `debug`

### 5.3 Format
```
[1] TITLE: ...
[2] TITLE: ...
```

---

## 6. Prompt‑bygging

- system_persona.md
- answer_template.md
- CONTEXT + SPØRSMÅL

---

## 7. LLM‑kall

- Global throttle
- Retry/backoff

---

## 8. Streaming (SSE)

- citations
- delta
- done
- error

---

## 9. Arkitekturregler

- Ingest ≠ runtime
- pack_context styrer alt som går til LLM
- UI får aldri stacktrace

---

## 10. Hvorfor dette er robust

- Sporbarhet
- Evaluerbarhet
- Utvidbarhet
