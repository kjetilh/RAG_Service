from __future__ import annotations
from pathlib import Path

def load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")

def load_html(path: Path) -> str:
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception as e:
        raise RuntimeError("HTML loader requires extras: pip install -e '.[html]'") from e
    soup = BeautifulSoup(load_text_file(path), "lxml")
    for t in soup(["script", "style"]):
        t.decompose()
    return soup.get_text("\n")

def load_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as e:
        raise RuntimeError("PDF loader requires extras: pip install -e '.[pdf]'") from e
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)

def load_docx(path: Path) -> str:
    try:
        import docx  # type: ignore
    except Exception as e:
        raise RuntimeError("DOCX loader requires extras: pip install -e '.[docx]'") from e
    d = docx.Document(str(path))
    return "\n".join(p.text for p in d.paragraphs)

def load_any(path: Path) -> str:
    suf = path.suffix.lower()
    if suf in [".html", ".htm"]:
        return load_html(path)
    if suf == ".pdf":
        return load_pdf(path)
    if suf == ".docx":
        return load_docx(path)
    return load_text_file(path)
