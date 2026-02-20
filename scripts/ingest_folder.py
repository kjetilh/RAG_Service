from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from app.rag.index.indexer import ingest_file
from app.settings import settings

SUPPORTED_EXTENSIONS = ["*.md", "*.markdown", "*.txt", "*.html", "*.htm", "*.pdf", "*.docx"]


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _compute_dest_dirs(input_path: Path, ingest_root: Path | None) -> tuple[Path, Path, Path]:
    """Return (root_dir, done_dir, failed_dir).

    Preferred layout is under ingest root:
      <ingest_root>/done/<relative-input-dir>
      <ingest_root>/failed/<relative-input-dir>

    Fallback (if input is outside ingest_root):
      <input-dir>/done
      <input-dir>/failed
    """
    if input_path.is_dir():
        root_dir = input_path
    else:
        root_dir = input_path.parent

    if ingest_root is not None and _is_within(root_dir, ingest_root):
        rel = root_dir.relative_to(ingest_root)
        done_dir = ingest_root / "done" / rel
        failed_dir = ingest_root / "failed" / rel
    else:
        done_dir = root_dir / "done"
        failed_dir = root_dir / "failed"

    return root_dir, done_dir, failed_dir


def _move_preserve_tree(src: Path, root_dir: Path, dest_root: Path) -> Path:
    try:
        rel = src.relative_to(root_dir)
    except Exception:
        rel = Path(src.name)
    dst = dest_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    return Path(shutil.move(str(src), str(dst)))


def _collect_files(path: Path, skip_roots: list[Path]) -> list[Path]:
    if not path.is_dir():
        return [path]

    files: list[Path] = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(path.rglob(ext))

    unique_files = sorted(set(files))
    return [f for f in unique_files if not any(_is_within(f, root) for root in skip_roots)]


def ingest_path(
    path: str,
    source_type: str = "unknown",
    author: str | None = None,
    year: int | None = None,
    ingest_root: str | None = None,
) -> None:
    p = Path(path).expanduser()
    if not p.exists():
        raise SystemExit(f"Path not found: {p}")

    configured_root = ingest_root or settings.ingest_root
    ingest_root_path = Path(configured_root).expanduser().resolve(strict=False) if configured_root else None

    root_dir, done_dir, failed_dir = _compute_dest_dirs(p, ingest_root_path)
    done_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)

    skip_roots: list[Path] = []
    if p.is_dir() and ingest_root_path is not None:
        skip_roots = [ingest_root_path / "done", ingest_root_path / "failed"]

    files = _collect_files(p, skip_roots)
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
    ap.add_argument("--ingest-root", default=None)
    args = ap.parse_args()
    ingest_path(
        args.path,
        source_type=args.source_type,
        author=args.author,
        year=args.year,
        ingest_root=args.ingest_root,
    )


if __name__ == "__main__":
    main()
