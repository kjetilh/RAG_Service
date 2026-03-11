from __future__ import annotations

from typing import Any, Dict, Iterable, Optional
import json
import re
from threading import Semaphore

from sqlalchemy import text

from app.settings import settings
from app.models.schemas import ChatResponse, Citation
from app.rag.index.db import engine
from app.rag.index.embedder import default_embedder
from app.rag.retrieve.hybrid import RetrievedChunk, hybrid_retrieve
from app.rag.planner.answer_modes import sanitize_text_without_citations, trim_excerpt
from app.rag.planner.deterministic import PlanResult, plan_query
from app.rag.retrieve.rerank import default_reranker
from app.rag.retrieve.pack_context import pack_context
from app.rag.generate.composer import compose_answer, rewrite_query_if_enabled
from app.rag.generate.llm_provider import LLMMessage, default_provider
from app.rag.generate.prompt_config_store import resolve_effective_paths
from app.rag.interviews.collective import prepare_question_set
from app.rag.eval.gate import run_evaluation_gate
from app.rag.safety.grounding import strict_grounding_check

# Global throttle to avoid parallel LLM calls from the UI (double-submit / reconnect / multiple tabs).
_LLM_SEM = Semaphore(1)

_QUERY_PLANNER_FALLBACKS = {
    "hybrid": [
        {"label": "litteratur", "source_strategy": "articles"},
        {"label": "intervjuer", "source_strategy": "interviews"},
    ],
    "articles": [{"label": "litteratur", "source_strategy": "articles"}],
    "interviews": [{"label": "intervjuer", "source_strategy": "interviews"}],
}

_STRUCTURED_ITEM_TOP_K = 4
_STRUCTURED_ITEM_MAX_CHUNKS_PER_DOC = 2
_LEADING_Q_RE = re.compile(r"^(?:Q\d+\.\s*)", flags=re.IGNORECASE)
_TIMESTAMP_TOKEN_RE = re.compile(r"\b\d{1,2}:\d{2}")
_BROKEN_SPEAKER_RE = re.compile(r"^(?P<speaker>[A-ZÆØÅ][A-Za-zÆØÅæøå .'\-]{1,60}?):\*\*\s*")
_SPEAKER_RE = re.compile(r"^\*\*(?P<speaker>[A-ZÆØÅ][A-Za-zÆØÅæøå .'\-]{1,60}):\*\*\s*")
_BROKEN_SPEAKER_ANY_RE = re.compile(r"(?<!\*)(?P<speaker>[A-ZÆØÅ][A-Za-zÆØÅæøå .'\-]{1,60}?):\*\*")
_SPEAKER_ANY_RE = re.compile(r"\*\*(?P<speaker>[A-ZÆØÅ][A-Za-zÆØÅæøå .'\-]{1,60}):\*\*")
_HEADERISH_RE = re.compile(r"^(hvordan|hvilke|hva|kan du|hvis du)\b", flags=re.IGNORECASE)


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        stripped = item.strip()
        if stripped:
            out.append(stripped)
    return out


def _map_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    internal: Dict[str, Any] = {}
    if "year" in filters and isinstance(filters["year"], dict) and "gte" in filters["year"]:
        internal["year_gte"] = filters["year"]["gte"]
    if "source_type" in filters and isinstance(filters["source_type"], list):
        internal["source_type"] = filters["source_type"]
    doc_ids = _normalize_string_list(filters.get("doc_id"))
    if doc_ids:
        internal["doc_id"] = doc_ids
    return internal


def _effective_top_k(top_k: Optional[int], retrieval: dict[str, int]) -> int:
    return int(top_k or retrieval.get("top_k_final") or 50)


def _prompt_case_id(plan: PlanResult, prompt_profile_case_id: str | None) -> str | None:
    if prompt_profile_case_id:
        return prompt_profile_case_id
    if plan.answer_mode and plan.answer_mode.default_prompt_case_id:
        return plan.answer_mode.default_prompt_case_id
    return plan.case_id


def _merge_instruction(*parts: str | None) -> str | None:
    values = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
    if not values:
        return None
    return "\n\n".join(values)


def _detail_instruction(plan: PlanResult) -> str | None:
    if not plan.answer_mode or plan.answer_mode.detail_level != "detailed":
        return None
    return (
        "Bruk litt mer plass på de delene som er mest relevante for spørsmålet. "
        "Vær konkret, men ikke gå utover det kildene faktisk dekker."
    )


def _retrieval_message(message: str, plan: PlanResult) -> str:
    hint = plan.answer_mode.retrieval_hint if plan.answer_mode else None
    if not hint:
        return message
    return f"{message}\n\nSOKEFOKUS: {hint}"


def _wants_quotes(message: str) -> bool:
    message_lc = (message or "").lower()
    return "sitat" in message_lc or "sitater" in message_lc or "vis sitater" in message_lc


def _quote_instruction(message: str) -> str | None:
    if not _wants_quotes(message):
        return None
    return (
        "Bruk ikke anførselstegn i løpende tekst med mindre du kopierer ordrett fra CONTEXT. "
        "Hvis brukeren ber om sitater, legg heller ved korte, dokumenterte sitater med kildereferanser i en egen sitatdel."
    )


def _append_documented_quotes(answer: str, citations: list[Citation], limit: int = 3) -> str:
    selected = [citation for citation, _ in _select_display_citations(citations, limit=limit)]
    if not selected:
        return answer
    lines = [answer.rstrip(), "", "## Dokumenterte sitater"]
    for idx, (citation, excerpt) in enumerate(_select_display_citations(selected, limit=limit), start=1):
        lines.append(f'- [{idx}] "{excerpt}" ({citation.title})')
    return "\n".join(lines).strip()


def _collapse_excerpt(text: str) -> str:
    cleaned = sanitize_text_without_citations(text or "")
    cleaned = cleaned.replace("\u00a0", " ")
    cleaned = _BROKEN_SPEAKER_RE.sub(lambda m: f"{m.group('speaker')}: ", cleaned)
    cleaned = _SPEAKER_RE.sub(lambda m: f"{m.group('speaker')}: ", cleaned)
    cleaned = _BROKEN_SPEAKER_ANY_RE.sub(lambda m: f"{m.group('speaker')}: ", cleaned)
    cleaned = _SPEAKER_ANY_RE.sub(lambda m: f"{m.group('speaker')}: ", cleaned)
    cleaned = _TIMESTAMP_TOKEN_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"([.!?])([A-ZÆØÅ])", r"\1 \2", cleaned)
    return cleaned.strip(" -:")


def _strip_question_prefix(text: str, question_text: str | None) -> str:
    if not question_text:
        return text
    candidates = [question_text.strip(), _LEADING_Q_RE.sub("", question_text.strip()).strip()]
    out = text
    for candidate in candidates:
        if not candidate:
            continue
        lowered = out.lower()
        lowered_candidate = candidate.lower()
        if lowered.startswith(lowered_candidate):
            out = out[len(candidate):].lstrip(" :-,")
    return out


def _display_excerpt_text(excerpt: str, *, question_text: str | None = None, limit: int = 220) -> str:
    cleaned = _collapse_excerpt(excerpt)
    cleaned = _strip_question_prefix(cleaned, question_text)
    cleaned = re.sub(r"\b(ja|nei)\s+(ja|nei)\b", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:")
    return trim_excerpt(cleaned, limit=limit)


def _excerpt_quality_score(excerpt: str, *, question_text: str | None = None) -> tuple[int, int, str]:
    display = _display_excerpt_text(excerpt, question_text=question_text, limit=260)
    raw = excerpt or ""
    score = 0
    word_count = len(display.split())
    score += min(word_count, 24)
    if 8 <= word_count <= 40:
        score += 12
    if question_text and not _HEADERISH_RE.match(display):
        score += 8
    if ":" in display[:32]:
        score += 6
    if _TIMESTAMP_TOKEN_RE.search(raw):
        score -= 8
    if "startet transkripsjon" in raw.lower():
        score -= 40
    if _HEADERISH_RE.match(display):
        score -= 18
    if display.lower().startswith("glenns kommentar"):
        score -= 8
    if len(display) < 45:
        score -= 10
    return score, len(display), display


def _select_display_citations(
    citations: list[Citation],
    *,
    limit: int,
    question_text: str | None = None,
) -> list[tuple[Citation, str]]:
    ranked: list[tuple[int, int, int, Citation, str]] = []
    for idx, citation in enumerate(citations):
        if not citation.excerpt:
            continue
        score, display_len, display = _excerpt_quality_score(citation.excerpt, question_text=question_text)
        if not display:
            continue
        ranked.append((score, display_len, idx, citation, display))

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2], item[3].doc_id, item[3].chunk_id))
    selected: list[tuple[Citation, str]] = []
    seen: set[tuple[str, str]] = set()
    for _score, _display_len, _idx, citation, display in ranked:
        key = (citation.doc_id, display.lower())
        if key in seen:
            continue
        seen.add(key)
        selected.append((citation, display))
        if len(selected) >= limit:
            break
    return selected


def _build_query_plan(
    *,
    plan: PlanResult,
    prompt_profile_case_id: str | None,
    prompt_case_id: str | None,
    prompt_system_path: str,
    prompt_answer_path: str,
    prompt_system_source: str,
    prompt_answer_source: str,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    query_plan = dict(plan.trace)
    query_plan["requested_prompt_profile_case_id"] = prompt_profile_case_id
    query_plan["effective_prompt_profile_case_id"] = prompt_case_id
    query_plan["prompt_system_source"] = prompt_system_source
    query_plan["prompt_answer_source"] = prompt_answer_source
    query_plan["prompt_system_path"] = prompt_system_path
    query_plan["prompt_answer_path"] = prompt_answer_path
    if extra_fields:
        query_plan.update(extra_fields)
    return query_plan


def _preview_query_plan(
    *,
    message: str,
    filters: dict[str, Any],
    prompt_profile_case_id: str | None,
) -> dict[str, Any]:
    plan = plan_query(message, filters)
    prompt_case_id = _prompt_case_id(plan, prompt_profile_case_id)
    prompt_system_path, prompt_answer_path, prompt_system_source, prompt_answer_source = resolve_effective_paths(
        case_id=prompt_case_id
    )
    return _build_query_plan(
        plan=plan,
        prompt_profile_case_id=prompt_profile_case_id,
        prompt_case_id=prompt_case_id,
        prompt_system_path=prompt_system_path,
        prompt_answer_path=prompt_answer_path,
        prompt_system_source=prompt_system_source,
        prompt_answer_source=prompt_answer_source,
        extra_fields={"preview_only": True},
    )


def _retrieve_candidates(
    *,
    query: str,
    filters: dict[str, Any],
    retrieval: dict[str, int],
    model_profile: str | None,
    rewrite_query: bool,
    effective_top_k: int,
) -> tuple[list[RetrievedChunk], str]:
    effective_query = rewrite_query_if_enabled(query, model_profile=model_profile) if rewrite_query else query
    embedder = default_embedder()
    query_emb = embedder.embed(effective_query)

    candidates = hybrid_retrieve(
        query=effective_query,
        query_emb=query_emb,
        top_k_vector=max(1, int(retrieval.get("top_k_vector", 10))),
        top_k_lexical=max(1, int(retrieval.get("top_k_lexical", 10))),
        filters=_map_filters(filters),
    )

    if settings.reranker_enabled:
        reranker = default_reranker()
        candidates = reranker.rerank(query, candidates, top_k=effective_top_k)

    return candidates, effective_query


def _render_response(
    *,
    message: str,
    plan: PlanResult,
    candidates: list[RetrievedChunk],
    top_k: int | None,
    model_profile: str | None,
    prompt_profile_case_id: str | None,
    router_instruction: str | None = None,
    answer_contract: str | None = None,
    extra_query_plan: dict[str, Any] | None = None,
) -> ChatResponse:
    effective_top_k = _effective_top_k(top_k, plan.retrieval)
    packed = pack_context(
        candidates,
        effective_top_k,
        max_chunks_per_doc=int(plan.retrieval.get("max_chunks_per_doc", settings.max_chunks_per_doc)),
    )
    if packed.debug is None:
        packed.debug = {}

    prompt_case_id = _prompt_case_id(plan, prompt_profile_case_id)
    prompt_system_path, prompt_answer_path, prompt_system_source, prompt_answer_source = resolve_effective_paths(
        case_id=prompt_case_id
    )
    packed.debug["query_plan"] = _build_query_plan(
        plan=plan,
        prompt_profile_case_id=prompt_profile_case_id,
        prompt_case_id=prompt_case_id,
        prompt_system_path=prompt_system_path,
        prompt_answer_path=prompt_answer_path,
        prompt_system_source=prompt_system_source,
        prompt_answer_source=prompt_answer_source,
        extra_fields=extra_query_plan,
    )

    citations = packed.citations
    if not citations:
        packed.debug["evaluation_gate"] = run_evaluation_gate(citations, plan.evaluation)
        return ChatResponse(
            answer=(
                "Ikke dokumentert i kildene.\n\n"
                "Jeg fant ingen relevante dokumenterte kilder i denne casen for sporsmalet. "
                "Prov a snevre inn sporsmalet, bruk mer konkrete dokumenterte begreper, "
                "eller velg et annet case hvis du forventer svar fra et annet kunnskapsdomene."
            ),
            citations=[],
            retrieval_debug=packed.debug,
        )

    with _LLM_SEM:
        answer = compose_answer(
            message,
            packed,
            model_profile=model_profile,
            router_instruction=router_instruction,
            case_id=prompt_case_id,
            answer_contract=answer_contract,
        )

    if _wants_quotes(message):
        answer = _append_documented_quotes(answer, citations)
    strict_grounding_check(answer, citations)
    evaluation_gate = run_evaluation_gate(citations, plan.evaluation)
    packed.debug["evaluation_gate"] = evaluation_gate
    if evaluation_gate.get("enforced") and not evaluation_gate.get("passed"):
        raise ValueError(
            "Evaluation gate failed: "
            + ", ".join(v.get("rule", "unknown") for v in evaluation_gate.get("violations", []))
        )

    return ChatResponse(answer=answer, citations=citations, retrieval_debug=packed.debug)


def _run_planned_single_pass(
    *,
    message: str,
    plan: PlanResult,
    top_k: int | None,
    model_profile: str | None,
    prompt_profile_case_id: str | None,
    filters_override: dict[str, Any] | None = None,
    answer_contract: str | None = None,
    router_instruction: str | None = None,
    rewrite_query: bool | None = None,
    extra_query_plan: dict[str, Any] | None = None,
) -> ChatResponse:
    effective_filters = dict(filters_override or plan.filters)
    effective_top_k = _effective_top_k(top_k, plan.retrieval)
    retrieval_message = _retrieval_message(message, plan)
    candidates, effective_query = _retrieve_candidates(
        query=retrieval_message,
        filters=effective_filters,
        retrieval=plan.retrieval,
        model_profile=model_profile,
        rewrite_query=plan.answer_mode.rewrite_query if rewrite_query is None and plan.answer_mode else bool(rewrite_query),
        effective_top_k=effective_top_k,
    )

    query_plan_extra = dict(extra_query_plan or {})
    query_plan_extra["retrieval_query_input"] = retrieval_message
    query_plan_extra["effective_query"] = effective_query
    query_plan_extra["effective_filters"] = effective_filters
    return _render_response(
        message=message,
        plan=plan,
        candidates=candidates,
        top_k=top_k,
        model_profile=model_profile,
        prompt_profile_case_id=prompt_profile_case_id,
        router_instruction=_merge_instruction(router_instruction, _quote_instruction(message)),
        answer_contract=answer_contract,
        extra_query_plan=query_plan_extra,
    )


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text_value = (raw or "").strip()
    if not text_value:
        return None
    try:
        payload = json.loads(text_value)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text_value, flags=re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            return None


def _planner_fallback_queries(message: str, source_strategy: str) -> list[dict[str, str]]:
    fallback = _QUERY_PLANNER_FALLBACKS.get(source_strategy) or [{"label": "primær", "source_strategy": source_strategy or "articles"}]
    return [
        {
            "label": item["label"],
            "source_strategy": item["source_strategy"],
            "query": message,
            "planned_by": "fallback",
        }
        for item in fallback
    ]


def _plan_retrieval_queries(message: str, plan: PlanResult, model_profile: str | None) -> tuple[list[dict[str, str]], dict[str, Any]]:
    mode = plan.answer_mode
    if mode is None or not mode.use_subquery_planner:
        return _planner_fallback_queries(message, mode.source_strategy if mode else "articles"), {
            "subquery_planner_used": False,
        }

    provider = default_provider(model_profile=model_profile)
    system = (
        "Du lager bare en retrieval-plan for RAG, ikke et svar til brukeren. "
        "Returner KUN gyldig JSON. Ingen forklaring."
    )
    user = (
        "Lag en kort retrieval-plan for dette spørsmålet.\n"
        f"SPORSMAL: {message}\n"
        f"SVARMODUS: {mode.answer_mode}\n"
        f"KILDESTRATEGI: {mode.source_strategy}\n"
        "Tilgjengelige source_strategy-verdier er articles, interviews eller hybrid.\n"
        "Returner JSON på formen:\n"
        '{"queries":[{"label":"kort navn","source_strategy":"articles|interviews|hybrid","query":"presis søkespørring"}],"final_focus":"kort fokus for slutt-svar"}'
    )

    try:
        with _LLM_SEM:
            raw = provider.chat([
                LLMMessage(role="system", content=system),
                LLMMessage(role="user", content=user),
            ])
        payload = _extract_json_object(raw)
        queries = []
        for item in list(payload.get("queries") or []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            source_strategy = str(item.get("source_strategy") or "").strip().lower()
            if source_strategy not in {"articles", "interviews", "hybrid"}:
                continue
            query = str(item.get("query") or "").strip()
            if not query:
                continue
            queries.append(
                {
                    "label": str(item.get("label") or source_strategy),
                    "source_strategy": source_strategy,
                    "query": query,
                    "planned_by": "llm_planner",
                }
            )
        if not queries:
            raise ValueError("Planner returned no usable queries.")
        return queries, {
            "subquery_planner_used": True,
            "subquery_planner_status": "ok",
            "subquery_final_focus": str(payload.get("final_focus") or "").strip() if isinstance(payload, dict) else "",
        }
    except Exception as exc:
        return _planner_fallback_queries(message, mode.source_strategy), {
            "subquery_planner_used": True,
            "subquery_planner_status": "fallback",
            "subquery_planner_error": str(exc),
        }


def _source_types_for_query(plan: PlanResult, source_strategy: str, explicit_source_types: list[str]) -> list[str]:
    if explicit_source_types:
        return explicit_source_types
    if source_strategy == "interviews":
        return [value for value in plan.filters.get("source_type", []) if "intervju" in value.lower()]
    if source_strategy == "articles":
        return [value for value in plan.filters.get("source_type", []) if "intervju" not in value.lower()]
    if source_strategy == "hybrid":
        return list(plan.filters.get("source_type", []))
    return list(plan.filters.get("source_type", []))


def _merge_candidates(candidate_groups: Iterable[list[RetrievedChunk]]) -> list[RetrievedChunk]:
    best: dict[str, RetrievedChunk] = {}
    for group in candidate_groups:
        for chunk in group:
            prev = best.get(chunk.chunk_id)
            if prev is None or float(chunk.score) > float(prev.score):
                best[chunk.chunk_id] = chunk
                continue
            if prev is not None and float(chunk.score) == float(prev.score):
                if (
                    str(chunk.doc_id),
                    int(chunk.ordinal),
                    str(chunk.chunk_id),
                    str(chunk.channel),
                ) < (
                    str(prev.doc_id),
                    int(prev.ordinal),
                    str(prev.chunk_id),
                    str(prev.channel),
                ):
                    best[chunk.chunk_id] = chunk
    return sorted(
        best.values(),
        key=lambda c: (-float(c.score), str(c.doc_id), int(c.ordinal), str(c.chunk_id), str(c.channel)),
    )


def _collect_citations_registry() -> tuple[list[Citation], dict[tuple[str, str], int]]:
    return [], {}


def _register_citation(citation: Citation, citations: list[Citation], index_by_key: dict[tuple[str, str], int]) -> int:
    key = (citation.doc_id, citation.chunk_id)
    if key in index_by_key:
        return index_by_key[key]
    citations.append(citation)
    idx = len(citations)
    index_by_key[key] = idx
    return idx


def _list_documents(source_types: list[str], limit: int = 24) -> list[dict[str, str]]:
    if not source_types:
        return []
    sql = text(
        """
        SELECT doc_id, title, source_type
        FROM documents
        WHERE source_type = ANY(:source_types)
          AND COALESCE(doc_state, 'active') = 'active'
        ORDER BY title NULLS LAST, doc_id
        LIMIT :limit
        """
    )
    with engine().begin() as conn:
        rows = conn.execute(sql, {"source_types": source_types, "limit": int(limit)}).mappings().all()
    return [dict(row) for row in rows]


def _structured_item_top_k(top_k: int | None) -> int:
    if top_k is None:
        return _STRUCTURED_ITEM_TOP_K
    return max(2, min(int(top_k), _STRUCTURED_ITEM_TOP_K))


def _retrieve_structured_bundle(
    *,
    query: str,
    plan: PlanResult,
    filters: dict[str, Any],
    top_k: int | None,
    model_profile: str | None,
) -> dict[str, Any]:
    candidate_top_k = _structured_item_top_k(top_k)
    candidates, effective_query = _retrieve_candidates(
        query=query,
        filters=filters,
        retrieval=plan.retrieval,
        model_profile=model_profile,
        rewrite_query=False,
        effective_top_k=candidate_top_k,
    )
    packed = pack_context(
        candidates,
        candidate_top_k,
        max_chunks_per_doc=min(
            _STRUCTURED_ITEM_MAX_CHUNKS_PER_DOC,
            int(plan.retrieval.get("max_chunks_per_doc", settings.max_chunks_per_doc)),
        ),
    )
    return {
        "effective_query": effective_query,
        "citations": list(packed.citations),
        "debug": packed.debug or {},
    }


def _fallback_structured_summary(citations: list[Citation]) -> str:
    if not citations:
        return "Grunnlaget er svakt. Det finnes ikke nok tydelige utdrag til å oppsummere dette robust."
    parts = [trim_excerpt(citation.excerpt, limit=180) for citation in citations[:2] if citation.excerpt]
    return " ".join(part for part in parts if part).strip() or "Grunnlaget er svakt og krever manuell kontroll."


def _summarize_structured_items(
    *,
    item_kind: str,
    message: str,
    items: list[dict[str, Any]],
    model_profile: str | None,
) -> dict[str, dict[str, Any]]:
    if not items:
        return {}

    provider = default_provider(model_profile=model_profile)
    prompt_items = [
        {
            "item_id": str(item.get("item_id") or ""),
            "label": str(item.get("label") or ""),
            "evidence": [
                {
                    "title": citation.title,
                    "doc_id": citation.doc_id,
                    "excerpt": trim_excerpt(citation.excerpt, limit=240),
                }
                for citation in list(item.get("citations") or [])[:3]
            ],
        }
        for item in items
    ]
    system = (
        "Du lager korte, nøkterne deloppsummeringer for et bokprosjekt. "
        "Bruk bare evidensen du får. Ikke finn på forklaringer, sitater eller påstander. "
        "Returner KUN gyldig JSON."
    )
    user = (
        f"SPORSMAL_FRA_BRUKER: {message}\n"
        f"ITEM_TYPE: {item_kind}\n"
        "For hvert item skal du returnere en kort oppsummering på 2-4 setninger. "
        "Hvis grunnlaget er svakt, si det eksplisitt. Ikke bruk referanser som [1]. "
        "Sett coverage til high når flere utdrag peker i samme retning, medium når grunnlaget er brukbart men begrenset, "
        "og low bare når evidensen faktisk er tynn eller sprikende.\n"
        "Returner JSON på formen:\n"
        '{"items":[{"item_id":"...","summary":"...","coverage":"high|medium|low","warning":"..."}]}\n\n'
        f"EVIDENS:\n{json.dumps(prompt_items, ensure_ascii=False)}"
    )

    try:
        with _LLM_SEM:
            raw = provider.chat(
                [
                    LLMMessage(role="system", content=system),
                    LLMMessage(role="user", content=user),
                ]
            )
        payload = _extract_json_object(raw)
    except Exception:
        payload = None

    summaries: dict[str, dict[str, Any]] = {}
    for entry in list(payload.get("items") or []) if isinstance(payload, dict) else []:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("item_id") or "").strip()
        if not item_id:
            continue
        summaries[item_id] = {
            "summary": str(entry.get("summary") or "").strip(),
            "coverage": str(entry.get("coverage") or "").strip().lower() or None,
            "warning": str(entry.get("warning") or "").strip() or None,
        }

    for item in items:
        item_id = str(item.get("item_id") or "")
        if item_id in summaries:
            continue
        summaries[item_id] = {
            "summary": _fallback_structured_summary(list(item.get("citations") or [])),
            "coverage": "low" if not item.get("citations") else "medium",
            "warning": "Fallback summary used because structured extraction was incomplete.",
        }
    return summaries


def _render_question_matrix(question_items: list[dict[str, Any]], plan: PlanResult, question_set_id: str) -> ChatResponse:
    citations, index_by_key = _collect_citations_registry()
    lines = ["## Funn per spørsmål"]
    item_debug: list[dict[str, Any]] = []

    for item in question_items:
        lines.append("")
        lines.append(f"### {item['question_id']}. {item['question']}")
        if item.get("warning"):
            lines.append(f"Vurdering av grunnlag: {item['warning']}")

        cleaned_answer = sanitize_text_without_citations(item.get("summary") or "")
        lines.append(cleaned_answer or "Ingen tydelige funn kunne oppsummeres fra materialet.")

        refs: list[int] = []
        quote_lines: list[str] = []
        display_citations = _select_display_citations(
            list(item.get("citations") or []),
            limit=3,
            question_text=item.get("question"),
        )
        for citation, display_excerpt in display_citations:
            ref = _register_citation(citation, citations, index_by_key)
            refs.append(ref)
            quote_lines.append(f'- [{ref}] "{display_excerpt}" ({citation.title})')
        if refs:
            lines.append("Kilder: " + ", ".join(f"[{ref}]" for ref in refs))
            lines.append("Sitater:")
            lines.extend(quote_lines)
        else:
            lines.append("Kilder: Ingen tydelige kildeutdrag valgt for dette spørsmålet.")

        item_debug.append(
            {
                "question_id": item["question_id"],
                "status": item.get("status", "ok"),
                "citation_count": len(item.get("citations") or []),
                "unique_doc_count": len({c.doc_id for c in list(item.get("citations") or []) if c.doc_id}),
                "coverage": item.get("coverage"),
                "effective_query": item.get("effective_query"),
            }
        )

    debug = {
        "query_plan": {
            **dict(plan.trace),
            "structured_item_count": len(question_items),
            "question_set_id": question_set_id,
            "structured_generation_mode": "retrieval_many_llm_one",
        },
        "structured_items": item_debug,
    }
    return ChatResponse(answer="\n".join(lines).strip(), citations=citations, retrieval_debug=debug)


def _collect_question_items(
    *,
    message: str,
    plan: PlanResult,
    top_k: int | None,
    model_profile: str | None,
    prompt_profile_case_id: str | None,
) -> tuple[str, list[dict[str, Any]]]:
    del prompt_profile_case_id
    question_set = prepare_question_set(
        inline_questions=None,
        question_set_path=plan.answer_mode.question_set_path if plan.answer_mode else None,
    )
    question_items: list[dict[str, Any]] = []

    for question in question_set.questions:
        bundle = _retrieve_structured_bundle(
            query=question.text,
            plan=plan,
            filters=dict(plan.filters),
            top_k=top_k,
            model_profile=model_profile,
        )
        question_items.append(
            {
                "item_id": question.question_id,
                "question_id": question.question_id,
                "question": question.text,
                "citations": list(bundle["citations"])[:3],
                "effective_query": bundle["effective_query"],
                "status": "ok" if bundle["citations"] else "weak",
            }
        )

    summaries = _summarize_structured_items(
        item_kind="question",
        message=message,
        items=question_items,
        model_profile=model_profile,
    )
    for item in question_items:
        summary = summaries.get(item["item_id"], {})
        item["summary"] = summary.get("summary")
        item["coverage"] = summary.get("coverage")
        item["warning"] = summary.get("warning")

    return question_set.question_set_id, question_items


def _run_collective_question_mode(
    *,
    message: str,
    plan: PlanResult,
    top_k: int | None,
    model_profile: str | None,
    prompt_profile_case_id: str | None,
) -> ChatResponse:
    question_set_id, question_items = _collect_question_items(
        message=message,
        plan=plan,
        top_k=top_k,
        model_profile=model_profile,
        prompt_profile_case_id=prompt_profile_case_id,
    )
    return _render_question_matrix(question_items, plan, question_set_id)


def _gap_rank(item: dict[str, Any]) -> tuple[int, int, int, str]:
    coverage = str(item.get("coverage") or "").lower()
    coverage_rank = {"low": 0, "medium": 1, "high": 2}.get(coverage, 1)
    unique_doc_count = len({c.doc_id for c in list(item.get("citations") or []) if c.doc_id})
    citation_count = len(list(item.get("citations") or []))
    return (coverage_rank, unique_doc_count, citation_count, str(item.get("question_id") or ""))


def _gap_reason(item: dict[str, Any]) -> str:
    reasons: list[str] = []
    citations = list(item.get("citations") or [])
    unique_doc_count = len({c.doc_id for c in citations if c.doc_id})
    if unique_doc_count < 2:
        reasons.append("få uavhengige intervjuperspektiver")
    if len(citations) < 2:
        reasons.append("få konkrete utsagn eller eksempler")
    warning = str(item.get("warning") or "").strip()
    if warning and "fallback" not in warning.lower():
        reasons.append(sanitize_text_without_citations(warning))
    if not reasons:
        coverage = str(item.get("coverage") or "").lower()
        if coverage == "medium":
            reasons.append("brukbart, men fortsatt begrenset grunnlag")
        elif coverage == "low":
            reasons.append("tynt eller sprikende grunnlag")
        else:
            reasons.append("dekningen er svakere enn for de andre spørsmålene")
    return "; ".join(dict.fromkeys(reasons))


def _render_interview_gap_report(question_items: list[dict[str, Any]], plan: PlanResult, question_set_id: str) -> ChatResponse:
    citations, index_by_key = _collect_citations_registry()
    weakest = sorted(question_items, key=_gap_rank)[:3]
    lines = ["## Svakest dekning i intervjuene"]
    structured_debug: list[dict[str, Any]] = []

    if not weakest:
        lines.append("Det finnes ikke nok intervjumateriale til å vurdere dekningen robust.")
    for item in weakest:
        lines.append("")
        lines.append(f"### {item['question_id']}. {item['question']}")
        cleaned = sanitize_text_without_citations(item.get("summary") or "")
        lines.append(cleaned or "Grunnlaget er for svakt til å oppsummere dette spørsmålet robust.")
        lines.append(f"Hvorfor dette er svakt belagt: {_gap_reason(item)}.")
        refs: list[int] = []
        for citation in list(item.get("citations") or [])[:2]:
            ref = _register_citation(citation, citations, index_by_key)
            refs.append(ref)
        if refs:
            lines.append("Kilder: " + ", ".join(f"[{ref}]" for ref in refs))
        structured_debug.append(
            {
                "question_id": item["question_id"],
                "citation_count": len(item.get("citations") or []),
                "unique_doc_count": len({c.doc_id for c in list(item.get("citations") or []) if c.doc_id}),
                "coverage": item.get("coverage"),
                "effective_query": item.get("effective_query"),
            }
        )

    lines.extend(["", "## Hva som mangler"])
    for item in weakest:
        unique_doc_count = len({c.doc_id for c in list(item.get("citations") or []) if c.doc_id})
        missing_bits: list[str] = []
        if unique_doc_count < 2:
            missing_bits.append("flere uavhengige intervjuperspektiver")
        if len(list(item.get("citations") or [])) < 2:
            missing_bits.append("flere konkrete utsagn, eksempler eller erfaringer")
        if not missing_bits:
            missing_bits.append("tydeligere og mer eksplisitt dekning av spørsmålet")
        lines.append(f"- {item['question_id']}: {', '.join(dict.fromkeys(missing_bits))}.")

    lines.extend(
        [
            "",
            "## Hva dette betyr for bokarbeidet",
            "Disse spørsmålene bør enten få mer empiri eller behandles med tydeligere forbehold i teksten. "
            "Bruk dem ikke som bærende funn uten å supplere med flere intervjuer eller sterkere dokumentasjon.",
        ]
    )

    debug = {
        "query_plan": {
            **dict(plan.trace),
            "structured_item_count": len(question_items),
            "question_set_id": question_set_id,
            "structured_generation_mode": "retrieval_many_llm_one",
        },
        "structured_items": structured_debug,
    }
    return ChatResponse(answer="\n".join(lines).strip(), citations=citations, retrieval_debug=debug)


def _run_interview_gap_mode(
    *,
    message: str,
    plan: PlanResult,
    top_k: int | None,
    model_profile: str | None,
    prompt_profile_case_id: str | None,
) -> ChatResponse:
    question_set_id, question_items = _collect_question_items(
        message=message,
        plan=plan,
        top_k=top_k,
        model_profile=model_profile,
        prompt_profile_case_id=prompt_profile_case_id,
    )
    return _render_interview_gap_report(question_items, plan, question_set_id)


def _render_per_interview_summary(*, rows: list[dict[str, Any]], summaries: list[dict[str, Any]], plan: PlanResult) -> ChatResponse:
    citations, index_by_key = _collect_citations_registry()
    lines = ["## Oppsummering per intervju"]

    for row, summary in zip(rows, summaries):
        lines.append("")
        lines.append(f"### {row.get('title') or row.get('doc_id')}")
        if summary.get("error"):
            lines.append(f"Intervjuet kunne ikke oppsummeres robust: {summary['error']}")
            continue
        if summary.get("warning"):
            lines.append(f"Vurdering av grunnlag: {summary['warning']}")
        cleaned = sanitize_text_without_citations(str(summary.get("answer") or ""))
        lines.append(cleaned or "Ingen tydelig oppsummering kunne lages fra tilgjengelige utdrag.")

        refs: list[int] = []
        quote_lines: list[str] = []
        display_citations = _select_display_citations(list(summary.get("citations") or []), limit=2)
        for citation, display_excerpt in display_citations:
            ref = _register_citation(citation, citations, index_by_key)
            refs.append(ref)
            quote_lines.append(f'- [{ref}] "{display_excerpt}" ({citation.title})')
        if refs:
            lines.append("Kilder: " + ", ".join(f"[{ref}]" for ref in refs))
            lines.append("Nøkkelsitater:")
            lines.extend(quote_lines)

    debug = {
        "query_plan": {
            **dict(plan.trace),
            "structured_item_count": len(summaries),
            "document_count": len(rows),
        },
        "structured_items": [
            {
                "doc_id": row.get("doc_id"),
                "title": row.get("title"),
                "status": "error" if summary.get("error") else "ok",
                "citation_count": len(summary.get("citations") or []),
                "coverage": summary.get("coverage"),
                "effective_query": summary.get("effective_query"),
            }
            for row, summary in zip(rows, summaries)
        ],
    }
    return ChatResponse(answer="\n".join(lines).strip(), citations=citations, retrieval_debug=debug)


def _run_per_interview_mode(
    *,
    message: str,
    plan: PlanResult,
    top_k: int | None,
    model_profile: str | None,
    prompt_profile_case_id: str | None,
) -> ChatResponse:
    interview_source_types = [value for value in plan.filters.get("source_type", []) if "intervju" in value.lower()]
    rows = _list_documents(interview_source_types, limit=24)
    summaries: list[dict[str, Any]] = []

    for row in rows:
        sub_filters = dict(plan.filters)
        sub_filters["doc_id"] = [str(row.get("doc_id") or "")]
        bundle = _retrieve_structured_bundle(
            query=message,
            plan=plan,
            filters=sub_filters,
            top_k=top_k,
            model_profile=model_profile,
        )
        summaries.append(
            {
                "item_id": str(row.get("doc_id") or ""),
                "citations": list(bundle["citations"])[:2],
                "effective_query": bundle["effective_query"],
            }
        )

    structured = _summarize_structured_items(
        item_kind="interview",
        message=message,
        items=[
            {
                "item_id": summary["item_id"],
                "label": row.get("title") or row.get("doc_id"),
                "citations": summary.get("citations") or [],
            }
            for row, summary in zip(rows, summaries)
        ],
        model_profile=model_profile,
    )
    for summary in summaries:
        item = structured.get(summary["item_id"], {})
        summary["answer"] = item.get("summary")
        summary["coverage"] = item.get("coverage")
        summary["warning"] = item.get("warning")

    return _render_per_interview_summary(rows=rows, summaries=summaries, plan=plan)


def _run_multi_query_mode(
    *,
    message: str,
    plan: PlanResult,
    top_k: int | None,
    model_profile: str | None,
    prompt_profile_case_id: str | None,
) -> ChatResponse:
    requested_source_types = (
        _normalize_string_list(plan.filters.get("source_type"))
        if plan.trace.get("reason") == "explicit_source_type_filter"
        else []
    )
    query_specs, planner_debug = _plan_retrieval_queries(message, plan, model_profile)
    candidate_groups: list[list[RetrievedChunk]] = []
    query_debug: list[dict[str, Any]] = []
    effective_top_k = _effective_top_k(top_k, plan.retrieval)

    for spec in query_specs:
        local_filters = dict(plan.filters)
        local_filters["source_type"] = _source_types_for_query(plan, spec["source_strategy"], requested_source_types)
        candidates, effective_query = _retrieve_candidates(
            query=spec["query"],
            filters=local_filters,
            retrieval=plan.retrieval,
            model_profile=model_profile,
            rewrite_query=False,
            effective_top_k=effective_top_k,
        )
        candidate_groups.append(candidates)
        query_debug.append(
            {
                "label": spec["label"],
                "planned_by": spec.get("planned_by"),
                "source_strategy": spec["source_strategy"],
                "query": spec["query"],
                "effective_query": effective_query,
                "source_types": local_filters.get("source_type"),
                "candidate_count": len(candidates),
            }
        )

    merged = _merge_candidates(candidate_groups)
    router_instruction = _merge_instruction(plan.prompt_instruction, plan.answer_mode.planner_focus if plan.answer_mode else None)
    if planner_debug.get("subquery_final_focus"):
        router_instruction = _merge_instruction(router_instruction, planner_debug.get("subquery_final_focus"))
    router_instruction = _merge_instruction(router_instruction, _detail_instruction(plan))

    return _render_response(
        message=message,
        plan=plan,
        candidates=merged,
        top_k=top_k,
        model_profile=model_profile,
        prompt_profile_case_id=prompt_profile_case_id,
        router_instruction=_merge_instruction(router_instruction, _quote_instruction(message)),
        answer_contract=plan.answer_mode.answer_contract if plan.answer_mode else None,
        extra_query_plan={
            **planner_debug,
            "subqueries": query_debug,
            "effective_filters": plan.filters,
        },
    )


def answer_question(
    message: str,
    conversation_id: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    top_k: Optional[int] = None,
    model_profile: Optional[str] = None,
    prompt_profile_case_id: Optional[str] = None,
) -> ChatResponse:
    del conversation_id  # Reserved for future conversation-aware prompts.
    filters = filters or {}
    plan = plan_query(message, filters)
    answer_mode = plan.answer_mode.answer_mode if plan.answer_mode else "general"

    if answer_mode == "interview_findings_per_question":
        return _run_collective_question_mode(
            message=message,
            plan=plan,
            top_k=top_k,
            model_profile=model_profile,
            prompt_profile_case_id=prompt_profile_case_id,
        )

    if answer_mode == "interview_summary_per_interview":
        return _run_per_interview_mode(
            message=message,
            plan=plan,
            top_k=top_k,
            model_profile=model_profile,
            prompt_profile_case_id=prompt_profile_case_id,
        )

    if answer_mode == "interview_gap_analysis":
        return _run_interview_gap_mode(
            message=message,
            plan=plan,
            top_k=top_k,
            model_profile=model_profile,
            prompt_profile_case_id=prompt_profile_case_id,
        )

    if plan.answer_mode and plan.answer_mode.use_subquery_planner:
        return _run_multi_query_mode(
            message=message,
            plan=plan,
            top_k=top_k,
            model_profile=model_profile,
            prompt_profile_case_id=prompt_profile_case_id,
        )

    return _run_planned_single_pass(
        message=message,
        plan=plan,
        top_k=top_k,
        model_profile=model_profile,
        prompt_profile_case_id=prompt_profile_case_id,
        answer_contract=plan.answer_mode.answer_contract if plan.answer_mode else None,
        router_instruction=_merge_instruction(
            plan.prompt_instruction,
            plan.answer_mode.planner_focus if plan.answer_mode else None,
            _detail_instruction(plan),
        ),
        rewrite_query=plan.answer_mode.rewrite_query if plan.answer_mode else None,
    )


def answer_question_stream(
    message: str,
    conversation_id: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    top_k: Optional[int] = None,
    model_profile: Optional[str] = None,
    prompt_profile_case_id: Optional[str] = None,
) -> Iterable[bytes]:
    """SSE stream.
    Events:
      - query_plan: JSON plan for router/filter decisions
      - status: {message: "..."}
      - citations: JSON list
      - delta: {delta: "..."}
      - error: {message: "...", type?: "..."}
      - done
    """
    try:
        preview_plan = _preview_query_plan(
            message=message,
            filters=filters or {},
            prompt_profile_case_id=prompt_profile_case_id,
        )
        yield f"event: query_plan\ndata: {json.dumps(preview_plan, ensure_ascii=False)}\n\n".encode("utf-8")
        if preview_plan.get("streaming_allowed") is False:
            status_payload = json.dumps(
                {
                    "message": "Arbeider med et strukturert svar. Dette kan ta litt tid.",
                    "phase": "planning",
                },
                ensure_ascii=False,
            )
            yield f"event: status\ndata: {status_payload}\n\n".encode("utf-8")

        resp = answer_question(
            message,
            conversation_id,
            filters or {},
            top_k,
            model_profile=model_profile,
            prompt_profile_case_id=prompt_profile_case_id,
        )

        query_plan = None
        if resp.retrieval_debug and isinstance(resp.retrieval_debug, dict):
            query_plan = resp.retrieval_debug.get("query_plan")
        if query_plan is not None:
            plan_payload = json.dumps(query_plan, ensure_ascii=False)
            yield f"event: query_plan\ndata: {plan_payload}\n\n".encode("utf-8")

        citations_payload = json.dumps([c.model_dump() for c in resp.citations], ensure_ascii=False)
        yield f"event: citations\ndata: {citations_payload}\n\n".encode("utf-8")

        chunk_size = max(10, int(settings.stream_chunk_chars))
        text = resp.answer or ""
        if query_plan and query_plan.get("streaming_allowed") is False:
            chunk_size = max(len(text), 1)
        for i in range(0, len(text), chunk_size):
            piece = text[i:i + chunk_size]
            data = json.dumps({"delta": piece}, ensure_ascii=False)
            yield f"event: delta\ndata: {data}\n\n".encode("utf-8")

        yield b"event: done\ndata: {}\n\n"
        return

    except Exception as e:
        payload = json.dumps(
            {
                "message": str(e),
                "type": e.__class__.__name__,
                "hint": "If this is a 429 from OpenAI, retry after a short delay or reduce concurrent requests.",
            },
            ensure_ascii=False,
        )
        yield f"event: error\ndata: {payload}\n\n".encode("utf-8")
        yield b"event: done\ndata: {}\n\n"
