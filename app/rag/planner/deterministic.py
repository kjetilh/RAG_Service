from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.rag.cases.loader import EvaluationConfig, case_by_id, load_rag_cases
from app.rag.retrieve.query_router import route_query, router_prompt_instruction
from app.settings import settings


@dataclass
class PlanResult:
    filters: dict[str, Any]
    retrieval: dict[str, int]
    trace: dict[str, Any]
    prompt_instruction: str | None
    case_id: str | None
    evaluation: EvaluationConfig | None


def _base_retrieval_settings() -> dict[str, int]:
    return {
        "top_k_vector": int(settings.top_k_vector),
        "top_k_lexical": int(settings.top_k_lexical),
        "top_k_final": int(settings.top_k_final),
        "max_chunks_per_doc": int(settings.max_chunks_per_doc),
    }


def _normalize_source_type(value: Any) -> list[str]:
    if isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if s:
            out.append(s)
    return out


def _match_keywords(msg: str, keywords: list[str]) -> list[str]:
    tokens = re.findall(r"\w+", msg.lower())
    token_set = set(tokens)
    matched: list[str] = []
    for raw in keywords:
        key = raw.strip().lower()
        if not key:
            continue
        if " " in key:
            if key in msg:
                matched.append(key)
            continue
        if key in token_set:
            matched.append(key)
            continue
        if len(key) >= 4 and any(t.startswith(key) for t in tokens):
            matched.append(key)
    return sorted(set(matched))


def _confidence(prompt_hits: int, docs_hits: int) -> float:
    total = prompt_hits + docs_hits
    if total <= 0:
        return 0.0
    return round(abs(prompt_hits - docs_hits) / float(total), 4)


def _domain_from_explicit_filter(
    source_types: list[str],
    docs_source_types: list[str],
    prompts_source_types: list[str],
) -> str:
    req = set(source_types)
    docs = set(docs_source_types)
    prompts = set(prompts_source_types)
    in_docs = bool(req & docs)
    in_prompts = bool(req & prompts)
    if in_docs and in_prompts:
        return "mixed"
    if in_prompts:
        return "prompts"
    if in_docs:
        return "docs"
    return "custom"


def _prompt_instruction(selected_domain: str) -> str | None:
    if selected_domain == "prompts":
        return (
            "Prioriter svar om prompts, instruksjonsdesign, maler, bruksmønster og forbedringsforslag "
            "for promptkvalitet og sporbarhet."
        )
    if selected_domain == "docs":
        return (
            "Prioriter svar om kodebruk, API-adferd, arkitektur, driftsmønster og dokumentasjonsforbedring "
            "for utviklere."
        )
    return None


def _legacy_plan(message: str, filters: dict[str, Any]) -> PlanResult:
    routed_filters, legacy = route_query(message, filters)
    retrieval = _base_retrieval_settings()
    trace = {
        "planner_version": "legacy-1",
        "planner_mode": "legacy_router",
        "router_enabled": bool(legacy.get("router_enabled")),
        "selected_case": None,
        "selected_domain": legacy.get("selected_domain"),
        "reason": legacy.get("reason"),
        "source_types_applied": legacy.get("source_types_applied"),
        "matched_prompt_keywords": legacy.get("matched_prompt_keywords", []),
        "matched_docs_keywords": legacy.get("matched_docs_keywords", []),
        "prompt_keyword_hits": int(legacy.get("prompt_keyword_hits", 0)),
        "docs_keyword_hits": int(legacy.get("docs_keyword_hits", 0)),
        "confidence": float(legacy.get("confidence", 0.0)),
        "retrieval": retrieval,
    }
    return PlanResult(
        filters=routed_filters,
        retrieval=retrieval,
        trace=trace,
        prompt_instruction=router_prompt_instruction(legacy),
        case_id=None,
        evaluation=None,
    )


def plan_query(message: str, filters: dict[str, Any] | None = None) -> PlanResult:
    raw_filters = dict(filters or {})
    if not bool(settings.next_gen_rag_enabled):
        return _legacy_plan(message, raw_filters)

    config = load_rag_cases(settings.rag_cases_path)
    requested_case = raw_filters.get("rag_case_id")
    if not isinstance(requested_case, str):
        requested_case = None
    selected_case = case_by_id(config, requested_case)
    if not selected_case.enabled:
        selected_case = case_by_id(config, config.default_case)

    planner = selected_case.planner
    retrieval = selected_case.retrieval.model_dump()
    explicit_source_types = _normalize_source_type(raw_filters.get("source_type"))
    message_lc = (message or "").lower()

    matched_docs_keywords = _match_keywords(message_lc, planner.docs_keywords)
    matched_prompt_keywords = _match_keywords(message_lc, planner.prompt_keywords)

    if explicit_source_types:
        selected_domain = _domain_from_explicit_filter(
            explicit_source_types,
            planner.docs_source_types,
            planner.prompts_source_types,
        )
        reason = "explicit_source_type_filter"
        source_types = list(explicit_source_types)
        docs_hits = 0
        prompt_hits = 0
    else:
        docs_hits = len(matched_docs_keywords)
        prompt_hits = len(matched_prompt_keywords)
        if prompt_hits > docs_hits:
            selected_domain = "prompts"
            source_types = list(planner.prompts_source_types)
            reason = "keyword_score"
        elif docs_hits > prompt_hits:
            selected_domain = "docs"
            source_types = list(planner.docs_source_types)
            reason = "keyword_score"
        else:
            selected_domain = planner.default_domain
            source_types = (
                list(planner.docs_source_types)
                if planner.default_domain == "docs"
                else list(planner.prompts_source_types)
            )
            reason = "default_domain" if (docs_hits + prompt_hits) == 0 else "keyword_tie_default_domain"

    planned_filters = dict(raw_filters)
    if source_types:
        planned_filters["source_type"] = source_types

    trace = {
        "planner_version": "ng-1",
        "planner_mode": "deterministic",
        "router_enabled": True,
        "selected_case": selected_case.case_id,
        "requested_case": requested_case,
        "selected_domain": selected_domain,
        "reason": reason,
        "source_types_applied": planned_filters.get("source_type"),
        "matched_prompt_keywords": matched_prompt_keywords,
        "matched_docs_keywords": matched_docs_keywords,
        "prompt_keyword_hits": int(prompt_hits),
        "docs_keyword_hits": int(docs_hits),
        "confidence": _confidence(prompt_hits, docs_hits),
        "retrieval": retrieval,
    }

    return PlanResult(
        filters=planned_filters,
        retrieval=retrieval,
        trace=trace,
        prompt_instruction=_prompt_instruction(selected_domain),
        case_id=selected_case.case_id,
        evaluation=selected_case.evaluation,
    )
