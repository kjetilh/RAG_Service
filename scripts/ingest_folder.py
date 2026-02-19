from __future__ import annotations
import argparse
from pathlib import Path
import shutil
from app.rag.index.indexer import ingest_file

def _compute_dest_dirs(input_path: Path) -> tuple[Path, Path, Path]:
    """Return (root_dir, done_dir, failed_dir).

    If --path points to a directory named 'papers', we create siblings:
      ../papers_done and ../papers_failed

    Generally: <path>_done and <path>_failed next to <path>.
    """
    if input_path.is_dir():
        root_dir = input_path
        name = input_path.name
    else:
        root_dir = input_path.parent
        name = root_dir.name

    done_dir = root_dir.parent / f"{name}_done"
    failed_dir = root_dir.parent / f"{name}_failed"
    return root_dir, done_dir, failed_dir

def _move_preserve_tree(src: Path, root_dir: Path, dest_root: Path) -> Path:
    try:
        rel = src.relative_to(root_dir)
    except Exception:
        rel = Path(src.name)
    dst = dest_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    return Path(shutil.move(str(src), str(dst)))

def ingest_path(path: str, source_type: str = "unknown", author: str | None = None, year: int | None = None) -> None:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"Path not found: {p}")

    root_dir, done_dir, failed_dir = _compute_dest_dirs(p)
    done_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)

    if p.is_dir():
        files: list[Path] = []
        for ext in ["*.md","*.markdown","*.txt","*.html","*.htm","*.pdf","*.docx"]:
            files.extend(p.rglob(ext))
        files = sorted(set(files))
    else:
        files = [p]

    if not files:
        raise SystemExit("No files found to ingest.")

    for f in files:
        try:
            doc_id = ingest_file(f, source_type=source_type, author=author, year=year)
            moved_to = _move_preserve_tree(f, root_dir, done_dir)
            print(f"Ingested {moved_to} -> {doc_id}")
        except Exception as e:
            try:
                moved_to = _move_preserve_tree(f, root_dir, failed_dir)
                print(f"FAILED ingest {moved_to}: {e}")
            except Exception as move_err:
                print(f"FAILED ingest {f}: {e} (also failed to move file: {move_err})")
            continue

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--source-type", default="unknown")
    ap.add_argument("--author", default=None)
    ap.add_argument("--year", type=int, default=None)
    args = ap.parse_args()
    ingest_path(args.path, source_type=args.source_type, author=args.author, year=args.year)

if __name__ == "__main__":
    main()
