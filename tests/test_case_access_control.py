from pathlib import Path

from app.rag.access import control
from app.settings import settings


def _write_cases(path: Path) -> None:
    path.write_text(
        """
version: 1
default_case: dimy_docs
cases:
  - case_id: dimy_docs
    description: docs
    enabled: true
    planner:
      docs_source_types: ["haven_docs"]
      prompts_source_types: ["dimy_prompts"]
      docs_keywords: []
      prompt_keywords: []
      default_domain: docs
  - case_id: innovasjon
    description: inn
    enabled: true
    planner:
      docs_source_types: ["innovasjonsledelse"]
      prompts_source_types: []
      docs_keywords: []
      prompt_keywords: []
      default_domain: docs
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_resolve_case_role_prefers_global_owner(monkeypatch):
    original = settings.cell_owner_user_ids_json
    settings.cell_owner_user_ids_json = '["kjetil-owner"]'
    try:
        monkeypatch.setattr(control, "_db_role_for_user", lambda *_: "viewer")
        role = control.resolve_case_role("dimy_docs", "kjetil-owner")
        assert role == "owner"
    finally:
        settings.cell_owner_user_ids_json = original


def test_has_case_role_uses_role_hierarchy(monkeypatch):
    monkeypatch.setattr(control, "resolve_case_role", lambda *_: "admin")
    assert control.has_case_role("dimy_docs", "u1", "viewer") is True
    assert control.has_case_role("dimy_docs", "u1", "admin") is True
    assert control.has_case_role("dimy_docs", "u1", "owner") is False


def test_case_exists_reads_rag_cases_file(tmp_path: Path):
    original = settings.rag_cases_path
    cases_path = tmp_path / "rag_cases.yml"
    _write_cases(cases_path)
    settings.rag_cases_path = str(cases_path)
    try:
        assert control.case_exists("dimy_docs") is True
        assert control.case_exists("missing_case") is False
    finally:
        settings.rag_cases_path = original


def test_case_list_for_user_resolves_owner_and_db_roles(tmp_path: Path, monkeypatch):
    original_path = settings.rag_cases_path
    original_owner_json = settings.cell_owner_user_ids_json
    original_instance_json = settings.instance_case_ids_json
    cases_path = tmp_path / "rag_cases.yml"
    _write_cases(cases_path)
    settings.rag_cases_path = str(cases_path)
    settings.cell_owner_user_ids_json = '["owner-user"]'
    try:
        owner_rows = control.case_list_for_user("owner-user")
        assert all(row["role"] == "owner" for row in owner_rows)

        monkeypatch.setattr(
            control,
            "_db_roles_for_user",
            lambda user_id, case_ids: {"dimy_docs": "viewer"} if user_id == "viewer-user" else {},
        )
        viewer_rows = control.case_list_for_user("viewer-user")
        role_map = {row["case_id"]: row["role"] for row in viewer_rows}
        assert role_map["dimy_docs"] == "viewer"
        assert role_map["innovasjon"] is None
    finally:
        settings.rag_cases_path = original_path
        settings.cell_owner_user_ids_json = original_owner_json
        settings.instance_case_ids_json = original_instance_json


def test_case_list_for_user_respects_instance_visibility(tmp_path: Path, monkeypatch):
    original_path = settings.rag_cases_path
    original_owner_json = settings.cell_owner_user_ids_json
    original_instance_json = settings.instance_case_ids_json
    cases_path = tmp_path / "rag_cases.yml"
    _write_cases(cases_path)
    settings.rag_cases_path = str(cases_path)
    settings.cell_owner_user_ids_json = '["owner-user"]'
    settings.instance_case_ids_json = '["dimy_docs"]'
    try:
        owner_rows = control.case_list_for_user("owner-user")
        assert [row["case_id"] for row in owner_rows] == ["dimy_docs"]

        monkeypatch.setattr(
            control,
            "_db_roles_for_user",
            lambda user_id, case_ids: {"dimy_docs": "viewer"} if user_id == "viewer-user" else {},
        )
        viewer_rows = control.case_list_for_user("viewer-user")
        assert [row["case_id"] for row in viewer_rows] == ["dimy_docs"]
        assert viewer_rows[0]["role"] == "viewer"
    finally:
        settings.rag_cases_path = original_path
        settings.cell_owner_user_ids_json = original_owner_json
        settings.instance_case_ids_json = original_instance_json
