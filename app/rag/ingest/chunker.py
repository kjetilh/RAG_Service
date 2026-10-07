from __future__ import annotations
from dataclasses import dataclass
import re

from app.settings import settings


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    section_path: str | None
    ordinal: int
    content: str
    # Text that is embedded and lexically indexed. None means "use content".
    index_text: str | None = None


_heading_re = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
_tag_re = re.compile(r"<[^>]+>")


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


def chunk_text_v1(doc_id: str, text: str, target_words: int = 350, overlap_words: int = 40) -> list[Chunk]:
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


def _clean_heading(heading: str) -> str:
    return _tag_re.sub("", heading).strip()


def _split_blocks(body: str) -> list[str]:
    """Split a section into paragraphs, keeping fenced code blocks whole."""
    blocks: list[str] = []
    cur: list[str] = []
    in_code = False
    for line in body.split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
            cur.append(line)
            if not in_code:
                blocks.append("\n".join(cur))
                cur = []
            continue
        if in_code:
            cur.append(line)
            continue
        if not line.strip():
            if cur:
                blocks.append("\n".join(cur))
                cur = []
            continue
        cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return blocks


def chunk_text_v2(
    doc_id: str,
    text: str,
    doc_title: str | None = None,
    target_words: int = 220,
    min_words: int = 60,
    max_words: int = 380,
) -> list[Chunk]:
    """Heading-path aware chunking.

    What it fixes, compared with v1 (measured 2026-10-08 on the HAVEN docs, where
    v1 gave chunks of 20-34 words on average, thousands of them under 20 words):

    - the heading hierarchy is tracked: section_path is "H2 > H3", not one title
    - text before the first heading is kept (v1 dropped it)
    - small neighbouring sections are merged until they reach min_words
    - long sections are split on paragraph and code-block boundaries
    - index_text = "<document title> > <heading path>\\n<body>", so a bullet list
      under "Current limits" can be found by a question that names the document
    """
    title = (doc_title or "").replace("_", " ").strip()
    matches = list(_heading_re.finditer(text))
    sections: list[tuple[list[str], str]] = []
    if matches and text[:matches[0].start()].strip():
        sections.append(([], text[:matches[0].start()].strip()))
    if not matches:
        sections.append(([], text))
    stack: list[tuple[int, str]] = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        heading = _clean_heading(m.group(2))
        stack = [(lv, t) for (lv, t) in stack if lv < level] + [(level, heading)]
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append(([t for _, t in stack], text[m.end():end].strip()))

    pieces: list[tuple[list[str], str]] = []
    for path, body in sections:
        if not body:
            if path:
                pieces.append((path, ""))
            continue
        if len(body.split()) <= max_words:
            pieces.append((path, body))
            continue
        cur: list[str] = []
        cur_words = 0
        for block in _split_blocks(body):
            block_words = len(block.split())
            if block_words > max_words:
                if cur:
                    pieces.append((path, "\n\n".join(cur)))
                    cur, cur_words = [], 0
                words = block.split()
                for j in range(0, len(words), target_words):
                    pieces.append((path, " ".join(words[j:j + target_words])))
                continue
            if cur_words + block_words > target_words and cur_words >= min_words:
                pieces.append((path, "\n\n".join(cur)))
                cur, cur_words = [], 0
            cur.append(block)
            cur_words += block_words
        if cur:
            pieces.append((path, "\n\n".join(cur)))

    def _common(a: list[str], b: list[str]) -> list[str]:
        out: list[str] = []
        for x, y in zip(a, b):
            if x != y:
                break
            out.append(x)
        return out

    # Merge small neighbours that are siblings or parent/child. A group keeps the
    # pieces it was built from; its path is their common heading prefix, and each
    # piece that sits deeper than that prefix carries its own heading as a label
    # line, so no heading text is lost by merging.
    groups: list[tuple[list[str], list[tuple[list[str], str]], int]] = []
    for path, body in pieces:
        n_words = len(body.split())
        if groups:
            g_path, g_pieces, g_words = groups[-1]
            cp = _common(g_path, path)
            related = len(cp) >= len(path) - 1 and len(cp) >= len(g_path) - 1
            if related and (g_words < min_words or n_words < min_words) and g_words + n_words <= max_words:
                groups[-1] = (cp, g_pieces + [(path, body)], g_words + n_words)
                continue
        groups.append((path, [(path, body)], n_words))

    merged: list[tuple[list[str], str, int]] = []
    for g_path, g_pieces, g_words in groups:
        if len(g_pieces) == 1:
            merged.append((g_path, g_pieces[0][1], g_words))
            continue
        parts: list[str] = []
        for p_path, p_body in g_pieces:
            label = " > ".join(p_path[len(g_path):])
            if label and p_body.strip():
                parts.append(f"{label}\n{p_body}")
            elif label:
                parts.append(label)
            elif p_body.strip():
                parts.append(p_body)
        merged.append((g_path, "\n\n".join(parts).strip(), g_words))

    chunks: list[Chunk] = []
    ordinal = 0
    for path, body, _ in merged:
        if not body.strip() and not path:
            continue
        heading_path = " > ".join(path)
        context = title + (f" > {heading_path}" if heading_path else "") if title else heading_path
        index_text = f"{context}\n{body}" if context else body
        content = body if body.strip() else heading_path
        chunks.append(Chunk(f"{doc_id}-c{ordinal:05d}", doc_id, heading_path or None, ordinal, content, index_text))
        ordinal += 1
    return chunks


def chunk_text(doc_id: str, text: str, target_words: int = 350, overlap_words: int = 40,
               doc_title: str | None = None) -> list[Chunk]:
    if str(getattr(settings, "chunker_version", "v1")).lower() == "v2":
        return chunk_text_v2(doc_id, text, doc_title=doc_title)
    return chunk_text_v1(doc_id, text, target_words=target_words, overlap_words=overlap_words)
