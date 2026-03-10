from __future__ import annotations

import json
from typing import Iterable

from app.rag.cases.loader import RagCase, RagCasesConfig
from app.settings import settings


def configured_instance_case_ids() -> set[str] | None:
    raw = (settings.instance_case_ids_json or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise ValueError(f"INSTANCE_CASE_IDS_JSON is invalid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise ValueError("INSTANCE_CASE_IDS_JSON must be a JSON array of case IDs.")

    out = {
        str(item).strip()
        for item in parsed
        if isinstance(item, str) and str(item).strip()
    }
    if not out:
        raise ValueError("INSTANCE_CASE_IDS_JSON must contain at least one non-empty case ID.")
    return out


def visible_cases(
    cfg: RagCasesConfig,
    *,
    available_source_types: Iterable[str] | None = None,
) -> list[RagCase]:
    visible_ids = configured_instance_case_ids()
    source_types = {
        str(value).strip()
        for value in (available_source_types or [])
        if isinstance(value, str) and str(value).strip()
    }

    out: list[RagCase] = []
    for case in cfg.cases:
        if not case.enabled:
            continue
        if visible_ids is not None and case.case_id not in visible_ids:
            continue
        if source_types:
            case_types = set(case.planner.docs_source_types) | set(case.planner.prompts_source_types)
            if not case_types.intersection(source_types):
                continue
        out.append(case)
    return out


def visible_case_ids(
    cfg: RagCasesConfig,
    *,
    available_source_types: Iterable[str] | None = None,
) -> set[str]:
    return {case.case_id for case in visible_cases(cfg, available_source_types=available_source_types)}
