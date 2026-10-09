from pathlib import Path
import hashlib

from app.settings import settings


def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_doc_id(path: Path, content_hash: str) -> str:
    """Stable document id.

    Scheme v1 is "<stem>-<content hash>". Two files with the same name and the
    same content in different folders then share one row; each sync run moves
    that row to the other path and tombstones the first, forever. Scheme v2
    hashes the resolved path together with the content, so a document is
    identified by where it is and what it says.
    """
    if str(getattr(settings, "doc_id_scheme", "v1")).lower() == "v2":
        key = f"{Path(path).resolve(strict=False)}\x00{content_hash}"
        return f"{path.stem}-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:10]}"
    return f"{path.stem}-{content_hash[:10]}"
