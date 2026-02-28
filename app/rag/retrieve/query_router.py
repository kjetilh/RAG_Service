from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from app.settings import settings


@dataclass
class QueryRouterConfig:
    enabled: bool
    docs_source_types: List[str]
    prompts_source_types: List[str]
    docs_keywords: List[str]
    prompts_keywords: List[str]


def _parse_json_string_list(raw: str, fallback: List[str]) -> List[str]:
    value = (raw or "").strip()
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
    except Exception:
        return fallback
    if not isinstance(parsed, list):
        return fallback
    cleaned = []
    for item in parsed:
        if isinstance(item, str):
            s = item.strip()
            if s:
                cleaned.append(s)
    return cleaned or fallback


def router_config_from_settings() -> QueryRouterConfig:
    docs_source_types = _parse_json_string_list(
        settings.query_router_docs_source_types_json,
        ["haven_docs", "cellprotocol_docs"],
    )
    prompts_source_types = _parse_json_string_list(
        settings.query_router_prompts_source_types_json,
        ["dimy_prompts", "prompt_docs"],
    )
    docs_keywords = _parse_json_string_list(
        settings.query_router_docs_keywords_json,
        [
            "api",
            "endpoint",
            "kode",
            "code",
            "implementasjon",
            "implementation",
            "arkitektur",
            "architecture",
            "database",
            "postgres",
            "docker",
            "deploy",
            "sync",
            "ingest",
            "feil",
            "error",
            "bug",
            "test",
        ],
    )
    prompts_keywords = _parse_json_string_list(
        settings.query_router_prompts_keywords_json,
        [
            "prompt",
            "prompts",
            "system prompt",
            "systeminstruksjon",
            "promptmal",
            "instruction",
            "instruksjon",
            "template",
            "mal",
            "agent",
            "policy",
        ],
    )
    return QueryRouterConfig(
        enabled=bool(settings.query_router_enabled),
        docs_source_types=docs_source_types,
        prompts_source_types=prompts_source_types,
        docs_keywords=[k.lower() for k in docs_keywords],
        prompts_keywords=[k.lower() for k in prompts_keywords],
    )


def _match_keywords(msg: str, keywords: List[str]) -> List[str]:
    matched: List[str] = []
    tokens = re.findall(r"\w+", msg)
    token_set = set(tokens)
    for keyword in keywords:
        k = keyword.strip().lower()
        if not k:
            continue
        if " " in k:
            if k in msg:
                matched.append(k)
            continue
        if k in token_set:
            matched.append(k)
            continue
        if len(k) >= 4 and any(token.startswith(k) for token in tokens):
            matched.append(k)
    return matched


def _confidence_from_hits(prompt_hits: int, docs_hits: int) -> float:
    total = prompt_hits + docs_hits
    if total <= 0:
        return 0.0
    return round(abs(prompt_hits - docs_hits) / float(total), 2)


def _infer_domain_from_explicit_filter(
    requested_source_types: List[str],
    cfg: QueryRouterConfig,
) -> Tuple[str, str]:
    req = set(requested_source_types)
    docs = set(cfg.docs_source_types)
    prompts = set(cfg.prompts_source_types)
    in_docs = bool(req & docs)
    in_prompts = bool(req & prompts)
    if in_docs and not in_prompts:
        return "docs", "explicit_source_type_filter"
    if in_prompts and not in_docs:
        return "prompts", "explicit_source_type_filter"
    if in_docs and in_prompts:
        return "mixed", "explicit_source_type_filter"
    return "custom", "explicit_source_type_filter"


def route_query(message: str, filters: Dict[str, Any] | None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    cfg = router_config_from_settings()
    raw_filters = dict(filters or {})

    requested_source_types = raw_filters.get("source_type")
    if isinstance(requested_source_types, tuple):
        requested_source_types = list(requested_source_types)
    if requested_source_types is not None and not isinstance(requested_source_types, list):
        requested_source_types = None

    if not cfg.enabled:
        plan = {
            "router_enabled": False,
            "selected_domain": "disabled",
            "reason": "router_disabled",
            "prompt_keyword_hits": 0,
            "docs_keyword_hits": 0,
            "source_types_applied": requested_source_types,
            "prompt_focus": None,
        }
        return raw_filters, plan

    if requested_source_types:
        domain, reason = _infer_domain_from_explicit_filter(requested_source_types, cfg)
        plan = {
            "router_enabled": True,
            "selected_domain": domain,
            "reason": reason,
            "matched_prompt_keywords": [],
            "matched_docs_keywords": [],
            "prompt_keyword_hits": 0,
            "docs_keyword_hits": 0,
            "source_types_applied": requested_source_types,
            "prompt_focus": (
                "prompt_design" if domain == "prompts" else ("technical_docs" if domain == "docs" else None)
            ),
            "confidence": 1.0,
        }
        return raw_filters, plan

    msg = (message or "").lower()
    matched_prompt = _match_keywords(msg, cfg.prompts_keywords)
    matched_docs = _match_keywords(msg, cfg.docs_keywords)
    out_filters = dict(raw_filters)
    prompt_hits = len(matched_prompt)
    docs_hits = len(matched_docs)
    if prompt_hits > docs_hits:
        out_filters["source_type"] = list(cfg.prompts_source_types)
        domain = "prompts"
        reason = "keyword_score"
        focus = "prompt_design"
    elif docs_hits > prompt_hits:
        out_filters["source_type"] = list(cfg.docs_source_types)
        domain = "docs"
        reason = "keyword_score"
        focus = "technical_docs"
    elif prompt_hits > 0:
        out_filters["source_type"] = list(cfg.docs_source_types)
        domain = "docs"
        reason = "keyword_tie_defaults_docs"
        focus = "technical_docs"
    else:
        out_filters["source_type"] = list(cfg.docs_source_types)
        domain = "docs"
        reason = "default_domain"
        focus = "technical_docs"

    plan = {
        "router_enabled": True,
        "selected_domain": domain,
        "reason": reason,
        "matched_prompt_keywords": matched_prompt,
        "matched_docs_keywords": matched_docs,
        "prompt_keyword_hits": prompt_hits,
        "docs_keyword_hits": docs_hits,
        "source_types_applied": out_filters.get("source_type"),
        "prompt_focus": focus,
        "confidence": _confidence_from_hits(prompt_hits, docs_hits),
    }
    return out_filters, plan


def router_prompt_instruction(plan: Dict[str, Any]) -> str | None:
    domain = str(plan.get("selected_domain") or "")
    if domain == "prompts":
        return (
            "Prioriter svar om prompts, instruksjonsdesign, maler, bruksmønster og forbedringsforslag "
            "for promptkvalitet og sporbarhet."
        )
    if domain == "docs":
        return (
            "Prioriter svar om kodebruk, API-adferd, arkitektur, driftsmønster og dokumentasjonsforbedring "
            "for utviklere."
        )
    return None
