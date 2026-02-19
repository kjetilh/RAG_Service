from pathlib import Path
from app.rag.index.db import exec_sql

def main():
    schema_path = Path(__file__).resolve().parents[1] / "app" / "rag" / "index" / "schema.sql"
    exec_sql(schema_path.read_text(encoding="utf-8"))
    exec_sql("ANALYZE;")

if __name__ == "__main__":
    main()
