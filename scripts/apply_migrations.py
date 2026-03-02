from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from app.rag.index.db import engine


@dataclass(frozen=True)
class Migration:
    migration_id: str
    sql: str
    path: Path


def migration_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "app" / "rag" / "index" / "migrations"


def list_migration_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(
        [p for p in path.iterdir() if p.is_file() and p.suffix.lower() == ".sql"],
        key=lambda p: p.name,
    )


def load_migrations(path: Path | None = None) -> list[Migration]:
    root = path or migration_dir()
    out: list[Migration] = []
    for p in list_migration_files(root):
        sql = p.read_text(encoding="utf-8").strip()
        if not sql:
            continue
        out.append(Migration(migration_id=p.stem, sql=sql, path=p))
    return out


def _ensure_history_table(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              migration_id TEXT PRIMARY KEY,
              applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )


def _applied_migration_ids(conn) -> set[str]:
    rows = conn.execute(text("SELECT migration_id FROM schema_migrations")).fetchall()
    return {str(r[0]) for r in rows}


def apply_all_migrations(path: Path | None = None) -> list[str]:
    migrations = load_migrations(path)
    if not migrations:
        return []

    applied_now: list[str] = []
    with engine().begin() as conn:
        _ensure_history_table(conn)
        applied = _applied_migration_ids(conn)
        for migration in migrations:
            if migration.migration_id in applied:
                continue
            conn.execute(text(migration.sql))
            conn.execute(
                text("INSERT INTO schema_migrations(migration_id) VALUES (:migration_id)"),
                {"migration_id": migration.migration_id},
            )
            applied_now.append(migration.migration_id)
    return applied_now


def main() -> None:
    applied = apply_all_migrations()
    print({"applied": applied, "count": len(applied)})


if __name__ == "__main__":
    main()
