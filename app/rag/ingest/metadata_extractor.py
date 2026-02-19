from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import re
import json

_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")

def _first_nonempty(*vals):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return v
    return None

def _guess_language(text: str) -> Optional[str]:
    # Lightweight heuristic: Norwegian letters suggest 'no'.
    # Otherwise we return None (avoid wrong guesses).
    if not text:
        return None
    sample = text[:4000].lower()
    if sum(sample.count(ch) for ch in ["æ", "ø", "å"]) >= 3:
        return "no"
    return None

def _extract_doi(text: str) -> Optional[str]:
    if not text:
        return None
    m = _DOI_RE.search(text[:20000])
    return m.group(0) if m else None

def _year_from_content(text: str) -> Optional[int]:
    if not text:
        return None
    head = text[:12000]
    lines = head.splitlines()
    for ln in lines[:200]:
        l = ln.strip()
        if not l:
            continue
        if "©" in l or "copyright" in l.lower():
            m = _YEAR_RE.search(l)
            if m:
                return int(m.group(1))
    m = _YEAR_RE.search(head)
    return int(m.group(1)) if m else None

def _parse_filename(path: Path) -> Dict[str, Any]:
    """
    Heuristics for filenames like:
      - 2021_OECD_Mission-Oriented-Innovation-Policy-Norway.pdf
      - 2018-EC_European-Innovation-Scoreboard.pdf
      - 2024-2025_RCN_Science-and-Technology-Indicators-Norway.pdf

    Returns possibly: year, year_range, author, title
    """
    stem = path.stem
    out: Dict[str, Any] = {}

    # year range (e.g., 2024-2025_...)
    m = re.match(r"^(?P<y1>19\d{2}|20\d{2})[-_](?P<y2>19\d{2}|20\d{2})[ _-](?P<rest>.+)$", stem)
    if m:
        y1 = int(m.group("y1"))
        y2 = int(m.group("y2"))
        out["year"] = y1
        out["year_range"] = f"{y1}-{y2}"
        stem = m.group("rest")

    # single leading year
    m = re.match(r"^(?P<year>19\d{2}|20\d{2})[ _-]+(?P<rest>.+)$", stem)
    if m and "year" not in out:
        out["year"] = int(m.group("year"))
        stem = m.group("rest")

    # optional author token before underscore
    m = re.match(r"^(?P<author>[^_]{2,40})_(?P<title>.+)$", stem)
    if m:
        out["author"] = m.group("author").replace("-", " ").strip()
        out["title"] = m.group("title").replace("_", " ").replace("-", " ").strip()
    else:
        out["title"] = stem.replace("_", " ").replace("-", " ").strip()

    return out

def _pdf_metadata(path: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return out
    try:
        r = PdfReader(str(path))
        md = r.metadata or {}
        title = getattr(md, "title", None) or md.get("/Title")
        author = getattr(md, "author", None) or md.get("/Author")
        lang = md.get("/Lang")
        if title:
            out["title"] = str(title).strip()
        if author:
            out["author"] = str(author).strip()
        if lang:
            out["language"] = str(lang).strip()
    except Exception:
        return {}
    return out

def _docx_metadata(path: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        import docx  # type: ignore
    except Exception:
        return out
    try:
        d = docx.Document(str(path))
        cp = d.core_properties
        if cp.title:
            out["title"] = str(cp.title).strip()
        if cp.author:
            out["author"] = str(cp.author).strip()
        if cp.created and not out.get("year"):
            out["year"] = int(cp.created.year)
    except Exception:
        return {}
    return out

@dataclass
class ExtractedMetadata:
    title: str
    author: Optional[str] = None
    year: Optional[int] = None
    source_type: Optional[str] = None
    publisher: Optional[str] = None
    url: Optional[str] = None
    language: Optional[str] = None
    doi: Optional[str] = None
    identifiers_json: Optional[str] = None
    meta_sources_json: Optional[str] = None
    file_path: Optional[str] = None

def extract_metadata(
    path: Path,
    preview_text: str,
    source_type: Optional[str] = None,
    cli_author: Optional[str] = None,
    cli_year: Optional[int] = None,
    cli_title: Optional[str] = None,
    cli_url: Optional[str] = None,
) -> ExtractedMetadata:
    """
    Precedence:
      1) CLI values win
      2) filename heuristics
      3) embedded metadata (PDF/DOCX)
      4) content heuristics (year/doi/lang)
    """
    sources: Dict[str, str] = {}
    identifiers: Dict[str, Any] = {}

    fn = _parse_filename(path)
    pdfm = _pdf_metadata(path) if path.suffix.lower() == ".pdf" else {}
    docxm = _docx_metadata(path) if path.suffix.lower() == ".docx" else {}

    title = _first_nonempty(cli_title, pdfm.get("title"), docxm.get("title"), fn.get("title"), path.stem) or path.stem
    if cli_title: sources["title"] = "cli"
    elif pdfm.get("title"): sources["title"] = "pdf"
    elif docxm.get("title"): sources["title"] = "docx"
    elif fn.get("title"): sources["title"] = "filename"

    author = _first_nonempty(cli_author, pdfm.get("author"), docxm.get("author"), fn.get("author"), None)
    if cli_author: sources["author"] = "cli"
    elif pdfm.get("author"): sources["author"] = "pdf"
    elif docxm.get("author"): sources["author"] = "docx"
    elif fn.get("author"): sources["author"] = "filename"

    year: Optional[int] = None
    if cli_year is not None:
        year = int(cli_year)
        sources["year"] = "cli"
    else:
        if fn.get("year") is not None:
            year = int(fn["year"])
            sources["year"] = "filename"
        elif docxm.get("year") is not None:
            year = int(docxm["year"])
            sources["year"] = "docx"
        else:
            y = _year_from_content(preview_text)
            if y is not None:
                year = int(y)
                sources["year"] = "content"

    language = _first_nonempty(pdfm.get("language"), _guess_language(preview_text), None)
    if pdfm.get("language"): sources["language"] = "pdf"
    elif language: sources["language"] = "content"

    doi = _extract_doi(preview_text)
    if doi:
        identifiers["doi"] = doi
        sources["doi"] = "content"
    if fn.get("year_range"):
        identifiers["year_range"] = fn["year_range"]
        sources["year_range"] = "filename"

    # Light publisher heuristic
    publisher = None
    if author and author.isupper() and 2 <= len(author) <= 12:
        publisher = author
        sources["publisher"] = "derived"

    url = cli_url
    if url:
        sources["url"] = "cli"

    identifiers_json = json.dumps(identifiers, ensure_ascii=False) if identifiers else None
    meta_sources_json = json.dumps(sources, ensure_ascii=False) if sources else None

    return ExtractedMetadata(
        title=title,
        author=author,
        year=year,
        source_type=source_type,
        publisher=publisher,
        url=url,
        language=language,
        doi=doi,
        identifiers_json=identifiers_json,
        meta_sources_json=meta_sources_json,
        file_path=str(path),
    )
