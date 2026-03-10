from __future__ import annotations

import argparse

from sqlalchemy import text

from app.rag.index.db import engine


def rename_source_type(old_value: str, new_value: str) -> int:
    sql = text(
        """
        UPDATE documents
        SET source_type = :new_value
        WHERE source_type = :old_value
        """
    )
    with engine().begin() as conn:
        result = conn.execute(sql, {"old_value": old_value, "new_value": new_value})
    return int(result.rowcount or 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", required=True)
    parser.add_argument("--new", required=True)
    args = parser.parse_args()

    updated = rename_source_type(args.old, args.new)
    print({"updated_rows": updated, "old": args.old, "new": args.new})


if __name__ == "__main__":
    main()
