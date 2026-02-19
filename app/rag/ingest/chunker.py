from __future__ import annotations
from dataclasses import dataclass
import re

@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    section_path: str | None
    ordinal: int
    content: str

_heading_re = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)

def _split_by_headings(text: str) -> list[tuple[str | None, str]]:
    matches = list(_heading_re.finditer(text))
    if not matches:
        return [(None, text)]
    parts = []
    for i, m in enumerate(matches):
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        title = m.group(2).strip()
        section_text = text[m.end():end].strip()
        parts.append((title, section_text))
    return parts

def chunk_text(doc_id: str, text: str, target_words: int = 350, overlap_words: int = 40) -> list[Chunk]:
    sections = _split_by_headings(text)
    chunks: list[Chunk] = []
    ordinal = 0
    for title, body in sections:
        body = body.strip()
        if not body:
            continue
        words = body.split()
        if len(words) <= target_words:
            chunks.append(Chunk(f"{doc_id}-c{ordinal:05d}", doc_id, title, ordinal, body))
            ordinal += 1
            continue
        i = 0
        while i < len(words):
            window = words[i:i+target_words]
            if not window:
                break
            content = " ".join(window).strip()
            chunks.append(Chunk(f"{doc_id}-c{ordinal:05d}", doc_id, title, ordinal, content))
            ordinal += 1
            if i + target_words >= len(words):
                break
            i = max(0, i + target_words - overlap_words)
    return chunks
