from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _NoDuplicateSafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping_no_duplicates(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"Duplicate key in YAML mapping: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_NoDuplicateSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_no_duplicates,
)


class PlannerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    docs_source_types: list[str] = Field(default_factory=list)
    prompts_source_types: list[str] = Field(default_factory=list)
    docs_keywords: list[str] = Field(default_factory=list)
    prompt_keywords: list[str] = Field(default_factory=list)
    default_domain: Literal["docs", "prompts"] = "docs"


class RetrievalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_k_vector: int = Field(default=50, ge=1, le=1000)
    top_k_lexical: int = Field(default=50, ge=1, le=1000)
    top_k_final: int = Field(default=12, ge=1, le=1000)
    max_chunks_per_doc: int = Field(default=3, ge=1, le=100)


class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_citations: int = Field(default=2, ge=0)
    min_unique_docs: int = Field(default=1, ge=0)
    min_avg_score: float = Field(default=0.0, ge=0.0)
    enforce: bool = False


class RagCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=80)
    description: str = ""
    enabled: bool = True
    planner: PlannerConfig
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)


class RagCasesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1)
    default_case: str = Field(min_length=1)
    cases: list[RagCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_cases(self):
        ids = [c.case_id for c in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate case_id in rag cases.")
        if self.default_case not in set(ids):
            raise ValueError(f"default_case '{self.default_case}' does not exist in cases.")
        return self


def _parse_yaml_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"RAG cases file not found: {path}")

    text = path.read_text(encoding="utf-8")
    data = yaml.load(text, Loader=_NoDuplicateSafeLoader)
    if data is None:
        raise ValueError(f"RAG cases file is empty: {path}")
    if not isinstance(data, dict):
        raise ValueError("RAG cases root must be a mapping.")
    return data


def load_rag_cases(path: str | Path) -> RagCasesConfig:
    p = Path(path).expanduser().resolve(strict=False)
    parsed = _parse_yaml_file(p)
    try:
        return RagCasesConfig.model_validate(parsed)
    except Exception as e:
        raise ValueError(f"Invalid rag cases YAML ({p}): {e}") from e


def case_by_id(config: RagCasesConfig, case_id: str | None) -> RagCase:
    selected_id = case_id or config.default_case
    for case in config.cases:
        if case.case_id == selected_id:
            return case
    raise ValueError(f"Unknown case_id: {selected_id}")
