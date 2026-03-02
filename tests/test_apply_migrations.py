from pathlib import Path

from scripts import apply_migrations as mig


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self):
        self.applied: set[str] = set()
        self.executed: list[tuple[str, dict | None]] = []

    def execute(self, statement, params=None):
        sql = str(statement).strip()
        self.executed.append((sql, params))
        if sql.startswith("SELECT migration_id FROM schema_migrations"):
            return _FakeResult([(x,) for x in sorted(self.applied)])
        if sql.startswith("INSERT INTO schema_migrations"):
            self.applied.add(str((params or {}).get("migration_id")))
            return _FakeResult([])
        return _FakeResult([])


class _FakeBegin:
    def __init__(self, conn: _FakeConn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self):
        self.conn = _FakeConn()

    def begin(self):
        return _FakeBegin(self.conn)


def test_list_migration_files_sorts_and_filters(tmp_path: Path):
    (tmp_path / "002_later.sql").write_text("-- later", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("-- first", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    files = mig.list_migration_files(tmp_path)
    assert [f.name for f in files] == ["001_first.sql", "002_later.sql"]


def test_load_migrations_skips_empty_sql(tmp_path: Path):
    (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "002_empty.sql").write_text(" \n\t", encoding="utf-8")
    migrations = mig.load_migrations(tmp_path)
    assert [m.migration_id for m in migrations] == ["001_first"]
    assert migrations[0].sql == "SELECT 1;"


def test_apply_all_migrations_applies_once(monkeypatch, tmp_path: Path):
    (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "002_second.sql").write_text("SELECT 2;", encoding="utf-8")
    fake_engine = _FakeEngine()
    monkeypatch.setattr(mig, "engine", lambda: fake_engine)

    first = mig.apply_all_migrations(tmp_path)
    second = mig.apply_all_migrations(tmp_path)

    assert first == ["001_first", "002_second"]
    assert second == []
    assert fake_engine.conn.applied == {"001_first", "002_second"}


def test_doc_state_migration_exists_and_contains_expected_columns():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "rag"
        / "index"
        / "migrations"
        / "0001_doc_state_versioning.sql"
    )
    sql = migration_path.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS doc_state" in sql
    assert "ADD COLUMN IF NOT EXISTS doc_version" in sql
    assert "tombstone_pending" in sql
