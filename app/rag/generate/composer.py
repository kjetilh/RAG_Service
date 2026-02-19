from __future__ import annotations
from typing import List, Any
from app.settings import settings
from app.rag.generate.persona import load_persona
from app.rag.generate.prompts import load_answer_template
from app.rag.generate.llm_provider import default_provider, LLMMessage
from app.rag.retrieve.hybrid import RetrievedChunk

def _format_context(context_chunks: List[RetrievedChunk]) -> str:
    # Keep context bounded: include chunk ids and titles for traceability
    blocks = []
    for i, c in enumerate(context_chunks, start=1):
        blocks.append(f"[{i}] TITLE: {c.title} | DOC: {c.doc_id} | CHUNK: {c.chunk_id}\n{c.content}")
    return "\n\n".join(blocks)

def rewrite_query_if_enabled(original_query: str) -> str:
    """Optional query rewrite using LLM to improve retrieval.
    If disabled or failure, returns original.
    """
    if not bool(settings.query_rewrite_enabled):
        return original_query

    provider = default_provider()
    system = (
        "Du er en hjelpsom assistent som omskriver søkespørsmål for bedre dokumentgjenfinning. "
        "Returner KUN den omskrevne spørringen, uten forklaring."
    )
    user = (
        "Omskriv denne spørringen til et presist søkespørsmål med nøkkelbegreper. "
        "Behold språket (norsk hvis norsk).\n\n"
        f"ORIGINAL: {original_query}"
    )
    try:
        out = provider.chat([LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)])
        out = (out or "").strip()
        # Guardrails: keep it short-ish, fallback if it's empty or weird
        if 1 <= len(out) <= 240 and "\n" not in out:
            return out
    except Exception:
        pass
    return original_query

def compose_answer(question: str, context_chunks: Any) -> str:
    persona = load_persona()
    template = load_answer_template()
    provider = default_provider()

    # Support both:
    # - old style: context_chunks is List[RetrievedChunk]
    # - new style: PackedContext with .context_text
    if hasattr(context_chunks, "context_text"):
        context = context_chunks.context_text
    else:
        context = _format_context(context_chunks)

    user_prompt = (
        "Du skal svare ved å bruke KUN informasjonen i CONTEXT.\n"
        "VIKTIG: Hvert avsnitt i svaret skal inneholde minst én kildehenvisning i formen [1], [2], osv. "
        "Bruk tall som matcher kildene i CONTEXT.\n\n"
        f"SPØRSMÅL:\n{question}\n\n"
        f"CONTEXT:\n{context}\n\n"
        "Fyll denne malen (behold overskriftene):\n"
        f"{template}"
    )

    return provider.chat([
        LLMMessage(role="system", content=persona),
        LLMMessage(role="user", content=user_prompt),
    ])
