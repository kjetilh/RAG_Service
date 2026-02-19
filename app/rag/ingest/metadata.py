from pathlib import Path
import hashlib

def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def make_doc_id(path: Path, content_hash: str) -> str:
    return f"{path.stem}-{content_hash[:10]}"
