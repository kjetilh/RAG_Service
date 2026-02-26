from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.rag.index.db import engine
from app.settings import settings

DEFAULT_SYSTEM_PERSONA_PATH = "prompts/system_persona.md"
DEFAULT_ANSWER_TEMPLATE_PATH = "prompts/answer_template.md"

PromptSource = Literal["db", "env", "default"]


@dataclass
class PromptRuntimeConfig:
    system_persona_path: str | None
    answer_template_path: str | None
    version: int
    updated_by: str | None
    change_note: str | None
    updated_at: datetime | None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_prompt_path(path_value: str) -> Path:
    candidate = Path(path_value).expanduser()
    return candidate if candidate.is_absolute() else (_repo_root() / candidate)


def _normalize_optional_path(path_value: str | None) -> str | None:
    if path_value is None:
        return None
    stripped = path_value.strip()
    return stripped or None


def _runtime_config_from_mapping(row: dict) -> PromptRuntimeConfig:
    return PromptRuntimeConfig(
        system_persona_path=row.get("system_persona_path"),
        answer_template_path=row.get("answer_template_path"),
        version=int(row.get("version") or 0),
        updated_by=row.get("updated_by"),
        change_note=row.get("change_note"),
        updated_at=row.get("updated_at"),
    )


def get_runtime_config() -> PromptRuntimeConfig:
    sql = """
        SELECT system_persona_path, answer_template_path, version, updated_by, change_note, updated_at
        FROM prompt_runtime_config
        WHERE id = 1
    """
    try:
        with engine().begin() as conn:
            row = conn.execute(text(sql)).mappings().first()
    except SQLAlchemyError:
        row = None

    if not row:
        return PromptRuntimeConfig(
            system_persona_path=None,
            answer_template_path=None,
            version=0,
            updated_by=None,
            change_note=None,
            updated_at=None,
        )
    return _runtime_config_from_mapping(row)


def resolve_effective_paths(
    runtime_cfg: PromptRuntimeConfig | None = None,
) -> tuple[str, str, PromptSource, PromptSource]:
    cfg = runtime_cfg or get_runtime_config()

    env_system = (settings.system_persona_path or "").strip()
    env_answer = (settings.answer_template_path or "").strip()

    if cfg.system_persona_path:
        system_path = cfg.system_persona_path
        system_source: PromptSource = "db"
    elif env_system:
        system_path = env_system
        system_source = "env"
    else:
        system_path = DEFAULT_SYSTEM_PERSONA_PATH
        system_source = "default"

    if cfg.answer_template_path:
        answer_path = cfg.answer_template_path
        answer_source: PromptSource = "db"
    elif env_answer:
        answer_path = env_answer
        answer_source = "env"
    else:
        answer_path = DEFAULT_ANSWER_TEMPLATE_PATH
        answer_source = "default"

    return system_path, answer_path, system_source, answer_source


def upsert_runtime_config(
    *,
    system_persona_path: str | None,
    answer_template_path: str | None,
    updated_by: str | None,
    change_note: str | None,
) -> PromptRuntimeConfig:
    sql = """
        INSERT INTO prompt_runtime_config (
            id, system_persona_path, answer_template_path, version, updated_by, change_note, updated_at
        )
        VALUES (1, :system_persona_path, :answer_template_path, 1, :updated_by, :change_note, now())
        ON CONFLICT (id) DO UPDATE
        SET
            system_persona_path = EXCLUDED.system_persona_path,
            answer_template_path = EXCLUDED.answer_template_path,
            updated_by = EXCLUDED.updated_by,
            change_note = EXCLUDED.change_note,
            version = prompt_runtime_config.version + 1,
            updated_at = now()
        RETURNING system_persona_path, answer_template_path, version, updated_by, change_note, updated_at
    """
    params = {
        "system_persona_path": _normalize_optional_path(system_persona_path),
        "answer_template_path": _normalize_optional_path(answer_template_path),
        "updated_by": _normalize_optional_path(updated_by),
        "change_note": _normalize_optional_path(change_note),
    }
    with engine().begin() as conn:
        row = conn.execute(text(sql), params).mappings().one()
    return _runtime_config_from_mapping(row)
