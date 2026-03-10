from __future__ import annotations

import argparse
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from app.rag.ingest.cleaner import clean_text

_DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
_DATE_LINE_RE = re.compile(r"^\d{1,2}\.\s+\w+\s+\d{4},")
_DURATION_LINE_RE = re.compile(r"^\d+m(?:\s+\d+s)?$")
_TRANSCRIBER_LINE_RE = re.compile(r"startet transkripsjon$", re.IGNORECASE)
_TIMESTAMP_PREFIX_RE = re.compile(r"^\d{1,2}:\d{2}(?P<text>.*)$")
_SPEAKER_LINE_RE = re.compile(
    r"^(?P<speaker>[A-ZÆØÅ][A-Za-zÆØÅæøå .'\-]{1,80}?)\s+(?P<ts>\d{1,2}:\d{2})(?P<text>.*)$"
)
_QUESTION_LINE_RE = re.compile(r"^(?P<num>\d{1,2})\.\s+(?P<text>.+)$")
_HEADER_NOISE_RE = re.compile(
    r"(from:\s|to:\s|cc:\s|subject:\s|posthuset|kullbrygga|opptak av møte)",
    re.IGNORECASE,
)
_TITLE_SUFFIX_RE = re.compile(r"[-–]\d{8}_\d{6}[-–]Opptak av møte.*$", re.IGNORECASE)
_GENERIC_TITLE_RE = re.compile(r"(bokprosjekt|intervjusamtale|bokprosjektintervju)", re.IGNORECASE)
_NOTES_LINE_RE = re.compile(r"påls notater|renskrevet gpt", re.IGNORECASE)


def _read_docx_paragraphs(path: Path) -> list[str]:
    with ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    paragraphs: list[str] = []
    for para in root.findall(".//w:p", _DOCX_NS):
        text = "".join((node.text or "") for node in para.findall(".//w:t", _DOCX_NS)).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _read_paragraphs(path: Path) -> list[str]:
    if path.suffix.lower() == ".docx":
        return _read_docx_paragraphs(path)
    return [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]


def _normalize_title(raw: str, fallback: str) -> str:
    title = _TITLE_SUFFIX_RE.sub("", (raw or "").strip()).strip(" -_,")
    title = title.replace("+++", "").strip()
    return title or fallback


def _speaker_hint(paragraphs: list[str]) -> str | None:
    for line in paragraphs[1:12]:
        match = _SPEAKER_LINE_RE.match(line.strip())
        if match:
            return match.group("speaker").strip()
    return None


def _organization_hint(path: Path) -> str | None:
    stem = _TITLE_SUFFIX_RE.sub("", path.stem).strip()
    parts = [part.strip(" -_,") for part in stem.split(" - ") if part.strip(" -_,")]
    if len(parts) < 2:
        return None
    candidate = parts[-1]
    lowered = candidate.lower()
    if "intervju" in lowered or "rammebetingelser" in lowered or "notater" in lowered:
        return None
    return candidate


def _derived_title(path: Path, paragraphs: list[str]) -> str:
    first_line = _normalize_title(paragraphs[0], path.stem)
    speaker = _speaker_hint(paragraphs)
    org = _organization_hint(path)
    if _GENERIC_TITLE_RE.search(first_line) and speaker:
        return f"Intervju {speaker}" + (f" - {org}" if org else "")
    if first_line and speaker and first_line == speaker and org:
        return f"Intervju {speaker} - {org}"
    if first_line and not speaker and org and len(first_line.split()) >= 2 and "intervju" not in first_line.lower():
        return f"Intervju {first_line} - {org}"
    return first_line


def _normalize_speaker_line(line: str) -> str:
    match = _SPEAKER_LINE_RE.match(line)
    if match:
        text = (match.group("text") or "").strip()
        if text:
            return f"**{match.group('speaker').strip()}:** {text}"
        return ""

    match = _TIMESTAMP_PREFIX_RE.match(line)
    if match:
        text = (match.group("text") or "").strip()
        return text

    match = _QUESTION_LINE_RE.match(line)
    if match:
        return f"## Q{match.group('num')}. {match.group('text').strip()}"

    return line.strip()


def _skip_line(line: str, index: int) -> bool:
    lowered = line.strip().lower()
    if not lowered:
        return True
    if _NOTES_LINE_RE.search(lowered):
        return True
    if _DATE_LINE_RE.match(line) or _DURATION_LINE_RE.match(line):
        return True
    if _TRANSCRIBER_LINE_RE.search(lowered):
        return True
    if index <= 5 and _HEADER_NOISE_RE.search(line):
        return True
    return False


def cleaned_transcript_markdown(path: Path) -> str:
    paragraphs = _read_paragraphs(path)
    if not paragraphs:
        raise SystemExit(f"No readable content in {path}")

    title = _derived_title(path, paragraphs)
    body_lines: list[str] = []

    for idx, raw in enumerate(paragraphs[1:], start=1):
        if _skip_line(raw, idx):
            continue
        normalized = _normalize_speaker_line(raw)
        normalized = clean_text(normalized)
        if not normalized:
            continue
        body_lines.append(normalized)

    if not body_lines:
        raise SystemExit(f"No usable interview content remained after cleanup for {path}")

    lines = [f"# {title}", "", "## Renskrevet innhold", ""]
    lines.extend(body_lines)
    return clean_text("\n".join(lines)) + "\n"


def _safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^\w\- .]+", "", value, flags=re.UNICODE).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "interview"


def write_cleaned_transcripts(input_dir: Path, output_dir: Path, force: bool = False) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for source_path in sorted(input_dir.glob("*")):
        if not source_path.is_file() or source_path.suffix.lower() not in {".docx", ".md", ".txt"}:
            continue
        content = cleaned_transcript_markdown(source_path)
        title = content.splitlines()[0].removeprefix("# ").strip()
        target_path = output_dir / f"{_safe_slug(title)}.md"
        if target_path.exists() and not force:
            raise SystemExit(f"Refusing to overwrite existing file without --force: {target_path}")
        target_path.write_text(content, encoding="utf-8")
        written.append(target_path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True, help="Directory containing raw interview files (.docx/.txt/.md).")
    parser.add_argument("--output-dir", required=True, help="Directory for cleaned markdown output.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing cleaned files.")
    args = parser.parse_args()

    written = write_cleaned_transcripts(
        input_dir=Path(args.input_dir).expanduser(),
        output_dir=Path(args.output_dir).expanduser(),
        force=bool(args.force),
    )
    for path in written:
        print(path)


if __name__ == "__main__":
    main()
