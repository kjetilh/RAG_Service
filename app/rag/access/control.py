from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Literal

from sqlalchemy import text

from app.rag.cases.loader import case_by_id, load_rag_cases
from app.rag.cases.visibility import visible_cases
from app.rag.index.db import engine
from app.settings import settings

CaseRole = Literal["owner", "admin", "viewer"]
VALID_ROLES: tuple[str, ...] = ("owner", "admin", "viewer")
ROLE_ORDER: dict[str, int] = {"viewer": 1, "admin": 2, "owner": 3}


@dataclass(frozen=True)
class CaseMember:
    case_id: str
    user_id: str
    role: CaseRole
    assigned_by: str | None = None


def _parse_owner_ids(raw: str) -> set[str]:
    txt = (raw or "").strip()
    if not txt:
        return set()
    try:
        parsed = json.loads(txt)
    except Exception:
        return set()
    if not isinstance(parsed, list):
        return set()
    out: set[str] = set()
    for item in parsed:
        if not isinstance(item, str):
            continue
        uid = item.strip()
        if uid:
            out.add(uid)
    return out


def global_owner_user_ids() -> set[str]:
    return _parse_owner_ids(settings.cell_owner_user_ids_json)


def canonical_role(role: str) -> CaseRole:
    value = (role or "").strip().lower()
    if value not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}")
    return value  # type: ignore[return-value]


def case_exists(case_id: str) -> bool:
    cfg = load_rag_cases(settings.rag_cases_path)
    try:
        case = case_by_id(cfg, case_id)
        return bool(case.enabled)
    except Exception:
        return False


def _db_role_for_user(case_id: str, user_id: str) -> CaseRole | None:
    sql = """
    SELECT role
    FROM rag_case_access
    WHERE case_id = :case_id AND user_id = :user_id
    LIMIT 1
    """
    with engine().begin() as conn:
        row = conn.execute(text(sql), {"case_id": case_id, "user_id": user_id}).fetchone()
    if row is None:
        return None
    role = canonical_role(str(row[0]))
    return role


def resolve_case_role(case_id: str, user_id: str | None) -> CaseRole | None:
    if not user_id:
        return None
    user = user_id.strip()
    if not user:
        return None
    if user in global_owner_user_ids():
        return "owner"
    return _db_role_for_user(case_id, user)


def has_case_role(case_id: str, user_id: str | None, minimum_role: str) -> bool:
    role = resolve_case_role(case_id, user_id)
    if role is None:
        return False
    min_role = canonical_role(minimum_role)
    return ROLE_ORDER[role] >= ROLE_ORDER[min_role]


def list_case_members(case_id: str) -> list[CaseMember]:
    sql = """
    SELECT case_id, user_id, role, assigned_by
    FROM rag_case_access
    WHERE case_id = :case_id
    ORDER BY
      CASE role
        WHEN 'owner' THEN 0
        WHEN 'admin' THEN 1
        WHEN 'viewer' THEN 2
        ELSE 3
      END,
      user_id
    """
    with engine().begin() as conn:
        rows = conn.execute(text(sql), {"case_id": case_id}).mappings().all()

    members = [
        CaseMember(
            case_id=str(r["case_id"]),
            user_id=str(r["user_id"]),
            role=canonical_role(str(r["role"])),
            assigned_by=(str(r["assigned_by"]) if r.get("assigned_by") is not None else None),
        )
        for r in rows
    ]
    global_owners = sorted(global_owner_user_ids())
    existing = {m.user_id for m in members}
    for owner in global_owners:
        if owner not in existing:
            members.insert(0, CaseMember(case_id=case_id, user_id=owner, role="owner", assigned_by="env"))
    return members


def upsert_case_member(case_id: str, user_id: str, role: str, assigned_by: str | None = None) -> None:
    normalized_role = canonical_role(role)
    normalized_user_id = (user_id or "").strip()
    if not normalized_user_id:
        raise ValueError("user_id cannot be empty")

    sql = """
    INSERT INTO rag_case_access(case_id, user_id, role, assigned_by, updated_at)
    VALUES (:case_id, :user_id, :role, :assigned_by, now())
    ON CONFLICT (case_id, user_id)
    DO UPDATE SET
      role = EXCLUDED.role,
      assigned_by = EXCLUDED.assigned_by,
      updated_at = now()
    """
    with engine().begin() as conn:
        conn.execute(
            text(sql),
            {
                "case_id": case_id,
                "user_id": normalized_user_id,
                "role": normalized_role,
                "assigned_by": assigned_by,
            },
        )


def delete_case_member(case_id: str, user_id: str) -> bool:
    normalized_user_id = (user_id or "").strip()
    if not normalized_user_id:
        return False
    sql = """
    DELETE FROM rag_case_access
    WHERE case_id = :case_id AND user_id = :user_id
    """
    with engine().begin() as conn:
        res = conn.execute(text(sql), {"case_id": case_id, "user_id": normalized_user_id})
    return bool(res.rowcount and res.rowcount > 0)


def _db_roles_for_user(user_id: str, case_ids: list[str]) -> dict[str, CaseRole]:
    if not case_ids:
        return {}
    sql = """
    SELECT case_id, role
    FROM rag_case_access
    WHERE user_id = :user_id AND case_id = ANY(:case_ids)
    """
    with engine().begin() as conn:
        rows = conn.execute(text(sql), {"user_id": user_id, "case_ids": case_ids}).mappings().all()
    out: dict[str, CaseRole] = {}
    for row in rows:
        out[str(row["case_id"])] = canonical_role(str(row["role"]))
    return out


def case_list_for_user(user_id: str | None) -> list[dict]:
    cfg = load_rag_cases(settings.rag_cases_path)
    enabled = visible_cases(cfg)
    case_ids = [c.case_id for c in enabled]

    if user_id and user_id.strip() in global_owner_user_ids():
        return [
            {"case_id": c.case_id, "description": c.description, "role": "owner", "enabled": bool(c.enabled)}
            for c in enabled
        ]

    role_map = _db_roles_for_user(user_id.strip(), case_ids) if (user_id and user_id.strip()) else {}
    out: list[dict] = []
    for case in enabled:
        out.append(
            {
                "case_id": case.case_id,
                "description": case.description,
                "role": role_map.get(case.case_id),
                "enabled": bool(case.enabled),
            }
        )
    return out
