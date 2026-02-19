from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from app.settings import settings

_engine: Engine | None = None

def engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine

def exec_sql(sql: str) -> None:
    with engine().begin() as conn:
        conn.execute(text(sql))
